"""Базовые обработчики: настройки, фон, профили, папки, ссылки, список версий.

Порт соответствующих ipcMain.handle из main.js.
Контракт модулей: handlers(ctx) -> dict[канал, функция(payload) -> результат].
"""
from __future__ import annotations

import copy
import os
import re
import secrets
import shutil
import time

from . import util
from .ctx import PUBLIC_KEYS, system_ram_gb

BG_IMAGE = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"]
BG_VIDEO = [".mp4", ".webm", ".m4v", ".ogv", ".mov"]
BG_LIMIT = {"image": 100 * 1024 ** 2, "video": 1024 ** 3}

FOLDERS = {
    "mods": "mods", "resourcepacks": "resourcepacks", "shaderpacks": "shaderpacks",
    "saves": "saves", "screenshots": "screenshots", "backups": "backups",
    "logs": "logs", "crash-reports": "crash-reports",
}
LINKS = {"tiktok": "https://www.tiktok.com/@udinaxui067"}


def parse_jvm_args(text) -> list[str]:
    """Аргументы Java: делим по пробелам (кавычки поддерживаются). Память задаётся отдельно."""
    out = []
    for m in re.finditer(r'"([^"]*)"|\'([^\']*)\'|(\S+)', str(text or "")):
        out.append(next(g for g in m.groups() if g is not None))
    for a in out:
        if not a.startswith("-"):
            raise ValueError(f"Аргумент «{a}» должен начинаться с «-»")
        if re.match(r"^-Xm[sx]", a, re.I):
            raise ValueError("Память задаётся ползунком выше, а не в аргументах (-Xmx/-Xms)")
    return out


def _dimension(v, label):
    if v is None or v == "":
        return None
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        raise ValueError(f"{label}: число от 320 до 7680")
    if n < 320 or n > 7680:
        raise ValueError(f"{label}: число от 320 до 7680")
    return int(n)


def _num(v, default):
    try:
        n = float(v)
        return n if n == n else default
    except (TypeError, ValueError):
        return default


PROFILE_COLORS = ["#5b6ee1", "#c2557a", "#3f9d78", "#c98a2b", "#8b5cc2", "#2f8fb5", "#b5533c", "#6a8f3a"]
PROFILE_GLYPHS = ["\u2605", "\u2665", "\u2694", "\u26CF", "\u2692", "\u2600", "\u263E", "\u2693", "\u2618", "\u2756", "\u25B6", "\u2726"]


def suggest_ram(total_gb: float, mods: int, loader: str = "vanilla", version: str = "") -> tuple[int, str]:
    """Подбор памяти: от версии, загрузчика и числа модов, но не больше половины оперативки (и не меньше 2 ГБ).
    Возвращает (ГБ, причина)."""
    mods = max(0, int(mods or 0))
    loader = (loader or "vanilla").lower()
    if loader == "vanilla" or mods == 0:
        want, why = 3, "чистая игра без модов"
    elif mods <= 30:
        want, why = 4, "немного модов"
    elif mods <= 80:
        want, why = 6, "средняя сборка"
    elif mods <= 150:
        want, why = 8, "большая сборка"
    else:
        want, why = 10, "очень большая сборка"
    try:
        minor = int(str(version).split(".")[1])
    except (IndexError, ValueError):
        minor = 20
    if minor <= 12 and loader != "vanilla":
        want = max(2, want - 1)  # старые версии с модами берут меньше
    limit = max(2, int(float(total_gb or 8) // 2))
    if want > limit:
        want, why = limit, "ограничено половиной оперативной памяти"
    return max(2, int(want)), why


def handlers(ctx):
    # ---------- настройки ----------
    def settings_get(_=None):
        return ctx.public_settings()

    def settings_set(patch=None):
        patch = patch or {}
        with ctx.lock:
            nxt = dict(ctx.settings)
            for k in PUBLIC_KEYS:
                if k in patch:
                    nxt[k] = patch[k]
            nxt["ram"] = min(max(_num(nxt.get("ram"), 4) or 4, 1), system_ram_gb())
            if float(nxt["ram"]).is_integer():
                nxt["ram"] = int(nxt["ram"])
            nxt["accountMode"] = "microsoft" if nxt.get("accountMode") == "microsoft" else "offline"
            nxt["glass"] = nxt.get("glass") is not False
            gs = _num(nxt.get("glassStrength"), 60)
            nxt["glassStrength"] = int(min(max(gs, 0), 100))
            nxt["lang"] = "en" if nxt.get("lang") == "en" else "ru"
            nxt["bgDim"] = int(min(max(round(_num(nxt.get("bgDim"), 0)), 0), 80))
            nxt["discordRpc"] = nxt.get("discordRpc") is True
            nxt["autoUpdate"] = nxt.get("autoUpdate") is not False
            nxt["autoBackup"] = nxt.get("autoBackup") is not False
            nxt["backupKeep"] = int(min(max(round(_num(nxt.get("backupKeep"), 5)) or 5, 1), 20))
            nxt["closeToTray"] = nxt.get("closeToTray") is True
            nxt["autoStart"] = nxt.get("autoStart") is True
            nxt["compatCheck"] = nxt.get("compatCheck") is not False
            nxt["tourDone"] = nxt.get("tourDone") is True
            nxt["autoUpdateMods"] = nxt.get("autoUpdateMods") is True
            nxt["achSound"] = nxt.get("achSound") is not False
            nxt["lastSeenVersion"] = str(nxt.get("lastSeenVersion") or "")[:20]
            nxt["tone"] = nxt.get("tone") if nxt.get("tone") in ("dark", "midnight", "forest", "sunset") else "dark"
            acc = str(nxt.get("accent") or "")
            nxt["accent"] = acc if re.fullmatch(r"#[0-9a-fA-F]{6}", acc) else ""
            nxt["discordClientId"] = str(nxt.get("discordClientId") or "").strip()[:32]
            for k in ("nickname", "curseforgeKey", "javaPath", "msClientId", "updateUrl", "rootDir"):
                nxt[k] = str(nxt.get(k) or "").strip()
            if not nxt["rootDir"]:
                nxt["rootDir"] = ctx.settings["rootDir"]
            ctx.settings.clear()
            ctx.settings.update(nxt)
            ctx.save_settings()
        try:
            os.makedirs(ctx.root, exist_ok=True)
        except OSError:
            pass
        hook = getattr(ctx, "on_settings_changed", None)  # презентер Discord, трей, автозапуск
        if callable(hook):
            try:
                hook()
            except Exception as e:  # noqa: BLE001
                ctx.diag(f"on_settings_changed: {e}")
        return ctx.public_settings()

    # ---------- свой фон ----------
    state = {"busy": False}

    def _remove_bg_file():
        old = ctx.bg_path()
        if old:
            try:
                os.remove(old)
            except OSError:
                pass

    def bg_choose(arg=None):
        given = arg.get("path") if isinstance(arg, dict) and isinstance(arg.get("path"), str) else None
        if state["busy"]:
            return {"ok": False, "error": "Файл уже копируется"}
        state["busy"] = True
        try:
            en = ctx.settings.get("lang") == "en"
            allext = [e[1:] for e in BG_IMAGE + BG_VIDEO]
            src = given or ctx.ui.open_file(
                "Choose a background image or video" if en else "Выбери картинку или видео для фона",
                [("Images and videos" if en else "Картинки и видео", allext),
                 ("Images" if en else "Картинки", [e[1:] for e in BG_IMAGE]),
                 ("Videos" if en else "Видео", [e[1:] for e in BG_VIDEO])])
            if not src:
                return {"ok": False, "canceled": True}
            ext = os.path.splitext(src)[1].lower()
            typ = "image" if ext in BG_IMAGE else "video" if ext in BG_VIDEO else None
            if not typ:
                return {"ok": False, "error": "Этот формат не поддерживается. Подходят: PNG, JPG, WEBP, GIF, BMP, AVIF, MP4, WEBM, M4V, OGV, MOV."}
            if not os.path.isfile(src):
                return {"ok": False, "error": "Это не файл"}
            if os.path.getsize(src) > BG_LIMIT[typ]:
                return {"ok": False, "error": "Файл слишком большой: картинки до 100 МБ, видео до 1 ГБ."}
            os.makedirs(ctx.bg_dir, exist_ok=True)
            name = f"bg-{int(time.time() * 1000)}{ext}"
            dest = os.path.join(ctx.bg_dir, name)
            try:
                shutil.copyfile(src, dest + ".part")
                os.replace(dest + ".part", dest)
            except OSError as e:
                try:
                    os.remove(dest + ".part")
                except OSError:
                    pass
                return {"ok": False, "error": "Не удалось скопировать файл: " + str(e)}
            _remove_bg_file()
            ctx.settings.update(bgFile=name, bgType=typ, bgName=os.path.basename(src)[:80])
            ctx.save_settings()
            return {"ok": True, "settings": ctx.public_settings()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            state["busy"] = False

    def bg_reset(_=None):
        _remove_bg_file()
        ctx.settings.update(bgFile="", bgType="", bgName="")
        ctx.save_settings()
        return {"ok": True, "settings": ctx.public_settings()}

    # ---------- профили ----------
    def profiles_list(_=None):
        return {
            "current": ctx.settings["currentProfile"],
            "profiles": [dict(p, modsCount=ctx.count_mods(p["id"])) for p in ctx.settings["profiles"]],
        }

    def profiles_create(data=None):
        try:
            return {"ok": True, "profile": ctx.create_profile(data or {})}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def profiles_select(pid=None):
        if not ctx.find_profile(pid):
            return {"ok": False, "error": "Профиль не найден"}
        ctx.settings["currentProfile"] = pid
        ctx.save_settings()
        return {"ok": True}

    def profiles_update(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("id"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        try:
            q = arg.get("patch") or {}
            nxt = {}
            if "name" in q:
                nxt["name"] = str(q["name"]).strip()[:40]
                if not nxt["name"]:
                    raise ValueError("Название не может быть пустым")
            if "ram" in q:
                if q["ram"] is None or q["ram"] == "":
                    nxt["ram"] = None
                else:
                    try:
                        n = float(q["ram"])
                    except (TypeError, ValueError):
                        raise ValueError("Память: нужно число")
                    n = min(max(n, 1), system_ram_gb())
                    nxt["ram"] = int(n) if float(n).is_integer() else n
            if "jvmArgs" in q:
                parse_jvm_args(q["jvmArgs"])
                nxt["jvmArgs"] = str(q["jvmArgs"] or "").strip()[:600]
            if "width" in q or "height" in q:
                w = _dimension(q["width"] if "width" in q else p.get("width"), "Ширина")
                h = _dimension(q["height"] if "height" in q else p.get("height"), "Высота")
                if (w is None) != (h is None):
                    raise ValueError("Укажи ширину и высоту вместе (или оставь оба поля пустыми)")
                nxt["width"], nxt["height"] = w, h
            if "fullscreen" in q:
                nxt["fullscreen"] = bool(q["fullscreen"])
            if "javaPath" in q:
                nxt["javaPath"] = str(q["javaPath"] or "").strip()[:260]
            if "color" in q:
                nxt["color"] = q["color"] if q["color"] in PROFILE_COLORS else ""
            if "glyph" in q:
                nxt["glyph"] = q["glyph"] if q["glyph"] in PROFILE_GLYPHS else ""
            if "group" in q:
                nxt["group"] = " ".join(str(q["group"] or "").split())[:24]
            p.update(nxt)
            ctx.save_settings()
            return {"ok": True, "profile": dict(p, modsCount=ctx.count_mods(p["id"]))}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def profiles_delete(arg=None):
        arg = arg or {}
        pid = arg.get("id")
        delete_files = arg.get("deleteFiles", True)
        p = ctx.find_profile(pid)
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        if ctx.launching:
            return {"ok": False, "error": "Нельзя удалять профиль, пока запускается игра"}
        try:
            if delete_files:
                shutil.rmtree(ctx.instance_dir(pid), ignore_errors=True)
            ctx.settings["profiles"] = [x for x in ctx.settings["profiles"] if x["id"] != pid]
            if ctx.settings["currentProfile"] == pid:
                ps = ctx.settings["profiles"]
                ctx.settings["currentProfile"] = ps[0]["id"] if ps else None
            ctx.save_settings()
            return {"ok": True, "current": ctx.settings["currentProfile"]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def profiles_duplicate(arg=None):
        """Копия сборки: настройки, моды, конфиги. Миры — только если withWorlds."""
        arg = arg or {}
        p = ctx.find_profile(arg.get("id"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        if ctx.launching:
            return {"ok": False, "error": "Подожди, пока запустится игра"}
        prev = ctx.settings.get("currentProfile")
        try:
            new = ctx.create_profile({"name": (str(p.get("name") or "") + " (копия)")[:40], "version": p["version"],
                                      "versionType": p.get("versionType"), "loader": p.get("loader"),
                                      "loaderVersion": p.get("loaderVersion"), "pack": copy.deepcopy(p.get("pack"))})
            for k in ("ram", "jvmArgs", "width", "height", "fullscreen", "javaPath", "color", "glyph", "group", "packFiles"):
                if k in p:
                    new[k] = copy.deepcopy(p[k])
            new["servers"] = [dict(x, id=secrets.token_hex(4)) for x in (p.get("servers") or []) if isinstance(x, dict)]
            skip = {"logs", "crash-reports", "screenshots", ".rollback", "backups"} | (set() if arg.get("withWorlds") else {"saves"})
            src, dst = ctx.instance_dir(p["id"]), ctx.instance_dir(new["id"])
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=lambda d, names: [n for n in names if n in skip and d == src])
            ctx.ensure_instance(new["id"])
            ctx.settings["currentProfile"] = prev if ctx.find_profile(prev) else new["id"]
            ctx.save_settings()
            return {"ok": True, "profile": new}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def preflight(arg=None):
        """Проверка перед запуском: место на диске, память, Java, указанная вручную. Возвращает список предупреждений."""
        p = ctx.find_profile((arg or {}).get("profileId") or ctx.settings.get("currentProfile"))
        warns = []
        try:
            free = shutil.disk_usage(ctx.root).free / 1024 ** 3
            if free < 1:
                warns.append({"level": "err", "key": "disk", "n": round(free, 1)})
            elif free < 3:
                warns.append({"level": "warn", "key": "disk", "n": round(free, 1)})
        except OSError:
            pass
        java = (p or {}).get("javaPath") or ctx.settings.get("javaPath") or ""
        if java and not os.path.isfile(java):
            warns.append({"level": "err", "key": "java", "path": java})
        total = system_ram_gb()
        ram = (p or {}).get("ram") or ctx.settings.get("ram") or 0
        if ram and total and float(ram) > total * 0.8:
            warns.append({"level": "warn", "key": "ram", "n": ram, "total": total})
        return {"ok": True, "warnings": warns}

    def files_drop(arg=None):
        """Файл, брошенный в окно: .jar -> моды, .zip -> ресурспаки (или шейдеры, если указано), остальное решает интерфейс."""
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId") or ctx.settings.get("currentProfile"))
        path = arg.get("path")
        if not p:
            return {"ok": False, "error": "Сначала создай сборку"}
        if not isinstance(path, str) or not os.path.isfile(path):
            return {"ok": False, "error": "Это не файл"}
        ext = os.path.splitext(path)[1].lower()
        kind = arg.get("kind")
        sub = "mods" if ext == ".jar" else ("shaderpacks" if kind == "shader" else "resourcepacks") if ext == ".zip" else None
        if not sub:
            return {"ok": False, "error": "Такой файл не подходит"}
        if os.path.getsize(path) > 512 * 1024 * 1024:
            return {"ok": False, "error": "Файл больше 512 МБ"}
        d = os.path.join(ctx.ensure_instance(p["id"]), sub)
        dest = os.path.join(d, os.path.basename(path))
        if os.path.exists(dest):
            return {"ok": False, "error": "Такой файл в сборке уже есть"}
        try:
            shutil.copyfile(path, dest + ".part")
            os.replace(dest + ".part", dest)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "folder": sub, "name": os.path.basename(path), "profile": p.get("name")}

    def ram_suggest(arg=None):
        want = (arg or {}).get("profileId")
        p = ctx.find_profile(want or ctx.settings.get("currentProfile"))
        if want and not p:
            return {"ok": False, "error": "Профиль не найден"}
        total = system_ram_gb()
        mods = ctx.count_mods(p["id"]) if p else 0
        gb, why = suggest_ram(total, mods, (p or {}).get("loader", "vanilla"), (p or {}).get("version", ""))
        return {"ok": True, "ram": gb, "reason": why, "mods": mods, "total": total}

    # ---------- папки, ссылки ----------
    def folder_open(arg=None):
        which = arg if isinstance(arg, str) else (arg or {}).get("which")
        pid = (arg.get("profileId") if isinstance(arg, dict) else None) or ctx.settings["currentProfile"]
        profile = ctx.find_profile(pid)
        d = ctx.root
        if which != "root" and profile:
            d = ctx.ensure_instance(profile["id"])
            if which in FOLDERS:
                d = os.path.join(d, FOLDERS[which])
        os.makedirs(d, exist_ok=True)
        ctx.ui.open_path(d)
        return {"ok": True}

    def link_open(key=None):
        url = LINKS.get(key) if isinstance(key, str) else None
        if not url:
            return {"ok": False}
        ctx.ui.open_url(url)
        return {"ok": True}

    # ---------- версии Minecraft ----------
    def versions_list(_=None):
        m = ctx.get_manifest()
        return {"latest": m["latest"],
                "versions": [{"id": v["id"], "type": v["type"], "releaseTime": v.get("releaseTime")}
                             for v in m["versions"]]}

    return {
        "settings:get": settings_get, "settings:set": settings_set,
        "bg:choose": bg_choose, "bg:reset": bg_reset,
        "profiles:list": profiles_list, "profiles:create": profiles_create,
        "profiles:select": profiles_select, "profiles:update": profiles_update,
        "profiles:delete": profiles_delete, "ram:suggest": ram_suggest,
        "profiles:duplicate": profiles_duplicate, "launch:preflight": preflight, "files:drop": files_drop,
        "folder:open": folder_open, "link:open": link_open,
        "versions:list": versions_list,
    }
