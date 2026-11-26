"""Импорт сборок из других лаунчеров: Prism/PolyMC/MultiMC, CurseForge, Modrinth App, официальный, Legacy/TLauncher.
Порт lib/importer.js."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import threading

from . import util

COPY_ITEMS = ["mods", "resourcepacks", "shaderpacks", "config", "defaultconfigs", "kubejs", "scripts",
              "options.txt", "optionsshaders.txt", "servers.dat"]
WORLDS = "saves"
MC = r"(\d+\.\d+(?:\.\d+)?(?:-(?:pre|rc)\d+)?|\d{2}w\d{2}[a-z])"
LEGACY_DIRS = [".tlauncher", ".legacylauncher", ".legacy-launcher"]


def id_of(d: str) -> str:
    return hashlib.sha1(os.path.abspath(d).lower().encode("utf-8")).hexdigest()[:10]


def is_dir(p) -> bool:
    return os.path.isdir(p)


def subdirs(p) -> list[str]:
    try:
        return sorted(e.name for e in os.scandir(p) if e.is_dir())
    except OSError:
        return []


def ini_get(file, key):
    try:
        with open(file, "r", encoding="utf-8", errors="replace") as f:
            m = re.search(rf"^{key}\s*=\s*(.*)$", f.read(), re.I | re.M)
        return m.group(1).strip() if m else None
    except OSError:
        return None


def count_files(d, rx) -> int:
    try:
        return sum(1 for f in os.listdir(d) if re.search(rx, f, re.I))
    except OSError:
        return 0


def game_dir_of(d):
    for n in ("minecraft", ".minecraft"):
        p = os.path.join(d, n)
        if is_dir(p):
            return p
    return d


def entry(launcher, name, version, loader, loader_version, game_dir):
    return {
        "id": id_of(game_dir), "launcher": launcher, "name": str(name or os.path.basename(game_dir))[:40],
        "version": version, "loader": loader, "loaderVersion": loader_version or "", "gameDir": game_dir,
        "modsCount": count_files(os.path.join(game_dir, "mods"), r"\.jar(\.disabled)?$"),
        "worldsCount": len(subdirs(os.path.join(game_dir, WORLDS))),
    }


def parse_version_id(vid: str):
    m = re.match(rf"^fabric-loader-(.+)-{MC}$", vid)
    if m:
        return {"loader": "fabric", "loaderVersion": m.group(1), "version": m.group(2)}
    m = re.match(rf"^quilt-loader-(.+)-{MC}$", vid)
    if m:
        return {"loader": "quilt", "loaderVersion": m.group(1), "version": m.group(2)}
    m = re.match(rf"^{MC}-forge-?(.+)$", vid)
    if m:
        return {"loader": "forge", "loaderVersion": re.sub(rf"^{re.escape(m.group(1))}-", "", m.group(2)), "version": m.group(1)}
    m = re.match(r"^neoforge-(\d+)\.(\d+)\.[\w.\-]+$", vid)
    if m:
        return {"loader": "neoforge", "loaderVersion": vid[len("neoforge-"):],
                "version": f"1.{m.group(1)}{'' if m.group(2) == '0' else '.' + m.group(2)}"}
    if re.match(rf"^{MC}$", vid):
        return {"loader": "vanilla", "loaderVersion": "", "version": vid}
    m = re.match(rf"^{MC}-OptiFine", vid, re.I)
    if m:
        return {"loader": "vanilla", "loaderVersion": "", "version": m.group(1)}
    return None


def scan_mmc(label, data_dir, cfg_name, out):
    if not is_dir(data_dir):
        return
    inst = os.path.join(data_dir, "instances")
    custom = ini_get(os.path.join(data_dir, cfg_name), "InstanceDir")
    if custom:
        inst = custom if os.path.isabs(custom) else os.path.join(data_dir, custom)
    for name in subdirs(inst):
        d = os.path.join(inst, name)
        pack = util.read_json(os.path.join(d, "mmc-pack.json"))
        if not pack:
            continue
        c = {x.get("uid"): x.get("version") for x in pack.get("components") or []}
        if not c.get("net.minecraft"):
            continue
        loader, lv = "vanilla", ""
        if c.get("net.fabricmc.fabric-loader"):
            loader, lv = "fabric", c["net.fabricmc.fabric-loader"]
        elif c.get("org.quiltmc.quilt-loader"):
            loader, lv = "quilt", c["org.quiltmc.quilt-loader"]
        elif c.get("net.neoforged"):
            loader, lv = "neoforge", c["net.neoforged"]
        elif c.get("net.minecraftforge"):
            loader, lv = "forge", c["net.minecraftforge"]
        out.append(entry(label, ini_get(os.path.join(d, "instance.cfg"), "name") or name,
                         c["net.minecraft"], loader, lv, game_dir_of(d)))


def scan_curseforge(roots, out):
    for root in roots:
        for name in subdirs(root):
            d = os.path.join(root, name)
            j = util.read_json(os.path.join(d, "minecraftinstance.json"))
            if not isinstance(j, dict):
                continue
            bl = j.get("baseModLoader") or {}
            version = j.get("gameVersion") or bl.get("minecraftVersion")
            if not version:
                continue
            loader, lv = "vanilla", ""
            m = re.match(r"^(forge|fabric|quilt|neoforge)-(.+)$", str(bl.get("name") or ""), re.I)
            if m:
                loader = m.group(1).lower()
                lv = m.group(2)[:-(len(version) + 1)] if m.group(2).endswith("-" + version) else m.group(2)
            out.append(entry("CurseForge", j.get("name") or name, version, loader, lv, d))


def scan_modrinth(profiles_dir, out, skipped):
    for name in subdirs(profiles_dir):
        d = os.path.join(profiles_dir, name)
        meta = (util.read_json(os.path.join(d, "profile.json")) or {}).get("metadata")
        if isinstance(meta, dict) and meta.get("game_version"):
            l = str(meta.get("loader") or "vanilla").lower()
            loader = l if l in ("fabric", "forge", "quilt", "neoforge") else "vanilla"
            lvv = meta.get("loader_version")
            lv = (lvv.get("id") if isinstance(lvv, dict) else lvv) or ""
            out.append(entry("Modrinth App", meta.get("name") or name, meta["game_version"], loader,
                             lv if isinstance(lv, str) else "", d))
        elif count_files(os.path.join(d, "mods"), r"\.jar") or subdirs(os.path.join(d, WORLDS)):
            skipped.append({"launcher": "Modrinth App", "name": name, "reason": "не удалось определить версию игры"})


def scan_official(d, out, label):
    vdir = os.path.join(d, "versions")
    if not is_dir(vdir):
        return
    found = []
    for vid in subdirs(vdir):
        try:
            at = os.stat(os.path.join(vdir, vid, f"{vid}.json")).st_mtime * 1000
        except OSError:
            continue
        p = parse_version_id(vid)
        if p:
            found.append({**p, "id": vid, "at": at})
    if not found:
        return
    found.sort(key=lambda x: -x["at"])
    best = found[0]
    e = entry(label, f"Minecraft {best['version']}", best["version"], best["loader"], best["loaderVersion"], d)
    e["options"] = [{k: f[k] for k in ("id", "version", "loader", "loaderVersion")} for f in found[:40]]
    e["defaultOption"] = best["id"]
    if e["modsCount"] or e["worldsCount"]:
        out.append(e)


def find_properties_game_dirs(root, depth=0, acc=None):
    acc = [] if acc is None else acc
    if depth > 3 or not is_dir(root):
        return acc
    try:
        entries = list(os.scandir(root))
    except OSError:
        return acc
    for e in entries:
        if e.is_dir():
            find_properties_game_dirs(e.path, depth + 1, acc)
        elif e.name.lower().endswith(".properties"):
            v = ini_get(e.path, r"minecraft\.gamedir")
            if v and is_dir(v):
                acc.append(v)
    return acc


def scan_legacy(appdata, home, out):
    bases = [b for b in (appdata, home) if b]
    markers = [p for p in (os.path.join(b, n) for b in bases for n in LEGACY_DIRS) if is_dir(p)]
    label = "Legacy Launcher / TLauncher"
    dirs: list[str] = []
    for m in markers:
        for d in find_properties_game_dirs(m):
            if d not in dirs:
                dirs.append(d)
    for b in bases:
        mc = os.path.join(b, ".minecraft")
        has_tl = any(os.path.exists(os.path.join(mc, f)) for f in ("TlauncherProfiles.json", "tlauncher_profiles.json"))
        if is_dir(mc) and (has_tl or markers) and mc not in dirs:
            dirs.append(mc)
    for d in dirs:
        scan_official(d, out, label)


def scan(env=None, home=None):
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    out, skipped = [], []
    appdata, local = env.get("APPDATA"), env.get("LOCALAPPDATA")
    profile = env.get("USERPROFILE") or home
    share = os.path.join(home, ".local", "share")
    mac = os.path.join(home, "Library", "Application Support")
    for base in [b for b in (appdata, local, share, mac) if b]:
        scan_mmc("Prism Launcher", os.path.join(base, "PrismLauncher"), "prismlauncher.cfg", out)
        scan_mmc("PolyMC", os.path.join(base, "PolyMC"), "polymc.cfg", out)
        scan_mmc("MultiMC", os.path.join(base, "MultiMC"), "multimc.cfg", out)
    scan_mmc("MultiMC", os.path.join(profile, "MultiMC"), "multimc.cfg", out)
    scan_curseforge([os.path.join(profile, "curseforge", "minecraft", "Instances"),
                     os.path.join(profile, "Documents", "curseforge", "minecraft", "Instances")], out)
    for base in [b for b in (appdata, share, mac) if b]:
        scan_modrinth(os.path.join(base, "ModrinthApp", "profiles"), out, skipped)
        scan_modrinth(os.path.join(base, "com.modrinth.theseus", "profiles"), out, skipped)
    scan_legacy(appdata, home, out)
    for d in [appdata and os.path.join(appdata, ".minecraft"), os.path.join(home, ".minecraft"), os.path.join(mac, "minecraft")]:
        if d:
            scan_official(d, out, "Официальный лаунчер")
    seen, uniq = set(), []
    for c in out:
        if c["id"] not in seen:
            seen.add(c["id"])
            uniq.append(c)
    return {"candidates": uniq, "skipped": skipped}


def public_view(c, imported):
    return {"id": c["id"], "launcher": c["launcher"], "name": c["name"], "version": c["version"], "loader": c["loader"],
            "loaderVersion": c["loaderVersion"], "modsCount": c["modsCount"], "worldsCount": c["worldsCount"],
            "imported": imported, "options": c.get("options"), "defaultOption": c.get("defaultOption")}


def handlers(ctx, env=None, home=None):
    lock = threading.Lock()
    state = {"busy": False}

    def imported_ids():
        if not isinstance(ctx.settings.get("imported"), list):
            ctx.settings["imported"] = []
        return ctx.settings["imported"]

    def scan_h(arg=None):
        auto = bool((arg or {}).get("auto"))
        try:
            r = scan(env, home)
            done = set(imported_ids())
            lst = [public_view(c, c["id"] in done) for c in r["candidates"]]
            if auto:
                lst = [c for c in lst if not c["imported"]]
            return {"ok": True, "candidates": lst, "skipped": [] if auto else r["skipped"],
                    "asked": bool(ctx.settings.get("importAsked"))}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "candidates": [], "skipped": [], "asked": True}

    def dismiss(_=None):
        ctx.settings["importAsked"] = True
        ctx.save_settings()
        return {"ok": True}

    def run(arg=None):
        arg = arg or {}
        ids = arg.get("ids") or []
        with_worlds = arg.get("withWorlds", True)
        choices = arg.get("choices") or {}
        with lock:
            if state["busy"]:
                return {"ok": False, "error": "Импорт уже выполняется"}
            state["busy"] = True

        def progress(text, done, total):
            ctx.send("import:progress", {"text": text, "done": done, "total": total})
        results = []
        try:
            by_id = {c["id"]: c for c in scan(env, home)["candidates"]}
            previous = ctx.settings.get("currentProfile")
            for n, cid in enumerate(ids, 1):
                c = dict(by_id[cid]) if cid in by_id else None
                if not c:
                    results.append({"id": cid, "ok": False, "error": "Сборка больше не найдена"})
                    continue
                opt = next((o for o in (c.get("options") or []) if o["id"] == choices.get(cid)), None)
                if opt:
                    c.update(version=opt["version"], loader=opt["loader"], loaderVersion=opt["loaderVersion"],
                             name=f"Minecraft {opt['version']}")
                try:
                    progress(f"Создаю профиль «{c['name']}» ({n}/{len(ids)})", n - 1, len(ids))
                    profile = ctx.create_profile({"name": c["name"], "version": c["version"], "loader": c["loader"],
                                                  "loaderVersion": c["loaderVersion"]})
                    dest = ctx.instance_dir(profile["id"])
                    items = COPY_ITEMS + [WORLDS] if with_worlds else COPY_ITEMS
                    for item in items:
                        src = os.path.join(c["gameDir"], item)
                        if not os.path.exists(src):
                            continue
                        progress(f"«{c['name']}»: копирую {item}", n - 1, len(ids))
                        tgt = os.path.join(dest, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, tgt, dirs_exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(tgt), exist_ok=True)
                            shutil.copy2(src, tgt)
                    try:
                        f = os.path.join(dest, "servers.dat")
                        if os.path.exists(f):
                            from .servers import read_servers_dat
                            stored = ctx.find_profile(profile["id"])
                            if stored is not None:
                                stored["servers"] = [{"id": secrets.token_hex(4), "name": s["name"], "host": s["host"],
                                                      "port": s["port"], "favorite": False}
                                                     for s in read_servers_dat(f)[:30]]
                    except Exception:  # noqa: BLE001
                        pass
                    imported_ids().append(cid)
                    ctx.save_settings()
                    results.append({"id": cid, "ok": True, "profile": {"id": profile["id"], "name": profile["name"]}})
                except Exception as e:  # noqa: BLE001
                    results.append({"id": cid, "ok": False, "error": str(e)})
            if previous and ctx.find_profile(previous):
                ctx.settings["currentProfile"] = previous
            ctx.save_settings()
            progress("Готово", len(ids), len(ids))
            return {"ok": True, "results": results}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "results": results}
        finally:
            state["busy"] = False

    return {"import:scan": scan_h, "import:dismiss": dismiss, "import:run": run}
