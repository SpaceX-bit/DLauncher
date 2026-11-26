"""Экспорт профиля в .mrpack (формат Modrinth, его понимают Modrinth App, Prism и другие) и импорт из .mrpack.

Моды, которые есть на Modrinth, попадают в сборку ссылками; остальные файлы кладутся внутрь архива.
Порт lib/profileio.js + lib/zipwrite.js. Обработчики: profile:export, profile:import. События: profile:progress.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import zlib

from . import modpacks, util
from .mods import MR_BASE
from .ziputil import ZipWriter, walk_files

MAX_IMPORT = 1024 * 1024 * 1024
LISTED = [
    ("mods", re.compile(r"\.jar$", re.I)),
    ("resourcepacks", re.compile(r"\.zip$", re.I)),
    ("shaderpacks", re.compile(r"\.zip$", re.I)),
]
LOADER_KEY = {"fabric": "fabric-loader", "quilt": "quilt-loader", "neoforge": "neoforge", "forge": "forge"}
FILTERS = [("Modrinth modpack", ["mrpack"])]
_lock = threading.Lock()


def safe_name(s) -> str:
    out = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", str(s or ""))
    out = re.sub(r"\s+", " ", out).strip()[:60]
    return out or "profile"


def lookup(sha1s: list[str]) -> dict:
    """Какие из файлов есть на Modrinth: sha1 -> {url, size}."""
    out: dict = {}
    if not sha1s:
        return out
    try:
        data = util.post_json(f"{MR_BASE}/version_files", {"hashes": sha1s, "algorithm": "sha1"})["data"] or {}
        for h, v in data.items():
            f = next((x for x in ((v or {}).get("files") or []) if (x.get("hashes") or {}).get("sha1") == h), None)
            if f and f.get("url") and str(f["url"]).startswith("https://cdn.modrinth.com/"):
                out[h] = {"url": f["url"], "size": f.get("size"), "filename": f.get("filename")}
    except Exception:  # noqa: BLE001
        pass  # нет сети: все файлы упакуем внутрь
    return out


def _state(ctx) -> dict:
    with _lock:
        st = getattr(ctx, "_profileio_state", None)
        if st is None:
            st = {"working": False}
            ctx._profileio_state = st
        return st


def _take(ctx) -> bool:
    st = _state(ctx)
    with _lock:
        if st["working"]:
            return False
        st["working"] = True
        return True


def _free(ctx) -> None:
    st = _state(ctx)
    with _lock:
        st["working"] = False


def export_profile(ctx, profile_id=None) -> dict:
    progress = lambda text: ctx.send("profile:progress", {"text": text})  # noqa: E731
    if _state(ctx)["working"]:
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    p = ctx.find_profile(profile_id or ctx.settings.get("currentProfile"))
    if not p:
        return {"ok": False, "error": "Профиль не найден"}
    dep_key = LOADER_KEY.get(p.get("loader"))
    if p.get("loader") != "vanilla" and (not dep_key or not p.get("loaderVersion")):
        return {"ok": False, "error": "У профиля не указана версия загрузчика"}

    path = ctx.ui.save_file(ctx.t("Экспорт профиля", "Export profile"), f"{safe_name(p.get('name'))}.mrpack", FILTERS)
    if not path:
        return {"ok": False, "canceled": True}
    dest = path if path.lower().endswith(".mrpack") else path + ".mrpack"

    if not _take(ctx):
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    base = ctx.instance_dir(p["id"])
    zw = None
    try:
        progress("Считаю контрольные суммы...")
        local = []
        for d, rx in LISTED:
            try:
                names = sorted(os.listdir(os.path.join(base, d)), key=lambda s: (s.lower(), s))
            except OSError:
                continue
            for name in names:
                absf = os.path.join(base, d, name)
                if not rx.search(name) or not os.path.isfile(absf):
                    continue
                local.append({"rel": f"{d}/{name}", "abs": absf, "sha1": util.sha1_file(absf)})

        progress("Ищу файлы на Modrinth...")
        known = lookup(list(dict.fromkeys(f["sha1"] for f in local)))
        files, bundled = [], []
        for f in local:
            k = known.get(f["sha1"])
            if not k:
                bundled.append(f)
                continue
            files.append({
                "path": f["rel"],
                "hashes": {"sha1": f["sha1"], "sha512": util.sha512_file(f["abs"])},
                "env": {"client": "required", "server": "required"},
                "downloads": [k["url"]],
                "fileSize": os.path.getsize(f["abs"]),
            })

        deps = {"minecraft": p["version"]}
        if dep_key:
            deps[dep_key] = p["loaderVersion"]
        index = {"formatVersion": 1, "game": "minecraft", "versionId": "1.0.0", "name": p.get("name"),
                 "summary": "Exported from DLauncher", "files": files, "dependencies": deps}

        progress("Собираю архив...")
        zw = ZipWriter(dest)
        zw.add_bytes("modrinth.index.json", json.dumps(index, indent=2, ensure_ascii=False))
        for f in bundled:
            zw.add_file(f"overrides/{f['rel']}", f["abs"])
        # настройки: config, options.txt, servers.dat (миры и логи не берём)
        for rel, absf in walk_files(os.path.join(base, "config")):
            zw.add_file(f"overrides/config/{rel}", absf)
        for one in ("options.txt", "servers.dat"):
            absf = os.path.join(base, one)
            if os.path.isfile(absf):
                zw.add_file(f"overrides/{one}", absf)
        zw.finish()
        zw = None
        return {"ok": True, "file": dest, "linked": len(files), "bundled": len(bundled), "size": os.path.getsize(dest)}
    except Exception as e:  # noqa: BLE001
        if zw:
            zw.abort()
        return {"ok": False, "error": str(e)}
    finally:
        _free(ctx)


def import_profile(ctx, path=None) -> dict:
    if _state(ctx)["working"]:
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    file = path if isinstance(path, str) and os.path.isfile(path) else ctx.ui.open_file(ctx.t("Импорт профиля", "Import profile"), FILTERS)
    if isinstance(file, (list, tuple)):
        file = file[0] if file else None
    if not file:
        return {"ok": False, "canceled": True}
    if not _take(ctx):
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    try:
        if not file.lower().endswith(".mrpack"):
            raise ValueError("Нужен файл .mrpack")
        if os.path.getsize(file) > MAX_IMPORT:
            raise ValueError("Файл больше 1 ГБ — такой архив не поддерживается")
        title = re.sub(r"\.mrpack$", "", os.path.basename(file), flags=re.I)
        r = modpacks.import_mrpack(ctx, file, title)
        return {"ok": True, "profile": r["profile"], "missing": r["missing"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        _free(ctx)


# ---------- код сборки: короткая строка вместо файла ----------
CODE_PREFIX = "DLC1-"
CODE_KINDS = ("mods", "resourcepacks", "shaderpacks")
MAX_CODE_FILES = 300


def make_code(meta: dict, groups: list[list[str]]) -> str:
    """groups — sha1 (hex) файлов по видам: моды, ресурспаки, шейдеры."""
    head = dict(meta, c=[len(g) for g in groups])
    raw = json.dumps(head, ensure_ascii=True, separators=(",", ":")).encode() + b"\0" + b"".join(
        bytes.fromhex(h) for g in groups for h in g)
    return CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def read_code(code: str) -> tuple[dict, list[list[str]]]:
    t = re.sub(r"\s+", "", str(code or ""))
    if not t.startswith(CODE_PREFIX):
        raise ValueError("Это не код сборки DLauncher")
    body = t[len(CODE_PREFIX):]
    try:
        d = zlib.decompressobj()
        raw = d.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)), 1024 * 1024)
        head_b, rest = raw.split(b"\0", 1)
        head = json.loads(head_b.decode())
        counts = [int(x) for x in head["c"]]
    except Exception:  # noqa: BLE001
        raise ValueError("Код повреждён или неполный — скопируй его целиком") from None
    if len(counts) != 3 or any(c < 0 for c in counts) or sum(counts) > MAX_CODE_FILES or len(rest) != 20 * sum(counts):
        raise ValueError("Код повреждён или неполный — скопируй его целиком")
    groups, pos = [], 0
    for c in counts:
        groups.append([rest[pos + 20 * i:pos + 20 * (i + 1)].hex() for i in range(c)])
        pos += 20 * c
    if not isinstance(head.get("m"), str) or not head["m"]:
        raise ValueError("В коде нет версии Minecraft")
    return head, groups


def export_code(ctx, profile_id=None) -> dict:
    p = ctx.find_profile(profile_id or ctx.settings.get("currentProfile"))
    if not p:
        return {"ok": False, "error": "Профиль не найден"}
    base = ctx.instance_dir(p["id"])
    groups: list[list[tuple[str, str]]] = []
    for d, rx in LISTED:
        found = []
        try:
            names = sorted(os.listdir(os.path.join(base, d)), key=lambda s: (s.lower(), s))
        except OSError:
            names = []
        for name in names:
            absf = os.path.join(base, d, name)
            if rx.search(name) and os.path.isfile(absf):
                found.append((name, util.sha1_file(absf)))
        groups.append(found)
    total = sum(len(g) for g in groups)
    if total == 0:
        return {"ok": False, "error": "В сборке нет модов, ресурспаков и шейдеров — делиться нечем"}
    known = lookup(list(dict.fromkeys(h for g in groups for _n, h in g)))
    if total and not known:
        return {"ok": False, "error": "Не удалось найти файлы на Modrinth (нет сети или файлы не оттуда)"}
    kept = [[h for _n, h in g if h in known] for g in groups]
    n_kept = sum(len(g) for g in kept)
    if n_kept > MAX_CODE_FILES:
        return {"ok": False, "error": f"Слишком много файлов для кода (больше {MAX_CODE_FILES}) — экспортируй в .mrpack"}
    code = make_code({"n": str(p.get("name") or "")[:40], "m": p.get("version"), "l": p.get("loader") or "vanilla",
                      "v": p.get("loaderVersion") or ""}, kept)
    return {"ok": True, "code": code, "linked": n_kept, "skipped": total - n_kept}


def index_from_code(head: dict, groups: list[list[str]], known: dict) -> tuple[dict, int]:
    """Строит modrinth.index по коду; возвращает (index, сколько файлов не нашлось на Modrinth)."""
    files, lost = [], 0
    for d, g in zip(CODE_KINDS, groups):
        for h in g:
            k = known.get(h)
            name = os.path.basename(str((k or {}).get("filename") or ""))
            if not k or not name:
                lost += 1
                continue
            files.append({"path": f"{d}/{name}", "hashes": {"sha1": h}, "downloads": [k["url"]],
                          "env": {"client": "required", "server": "required"}, "fileSize": k.get("size") or 0})
    loader = head.get("l") if head.get("l") in LOADER_KEY else "vanilla"
    deps = {"minecraft": head["m"]}
    if loader != "vanilla":
        deps[LOADER_KEY[loader]] = str(head.get("v") or "")
    return {"formatVersion": 1, "game": "minecraft", "name": str(head.get("n") or "")[:40] or "Сборка по коду",
            "files": files, "dependencies": deps}, lost


def import_code(ctx, code) -> dict:
    if _state(ctx)["working"]:
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    try:
        head, groups = read_code(code)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not _take(ctx):
        return {"ok": False, "error": "Другая операция с профилем ещё идёт"}
    try:
        ctx.send("profile:progress", {"text": "Ищу файлы по коду..."})
        known = lookup(list(dict.fromkeys(h for g in groups for h in g)))
        if sum(len(g) for g in groups) and not known:
            return {"ok": False, "error": "Не удалось получить файлы с Modrinth — проверь интернет"}
        index, lost = index_from_code(head, groups, known)
        r = modpacks.import_index(ctx, index, "Сборка по коду")
        miss = list(r["missing"]) + ([f"{lost} файл(ов) не найдено на Modrinth"] if lost else [])
        return {"ok": True, "profile": r["profile"], "missing": miss}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    finally:
        _free(ctx)


def handlers(ctx):
    return {
        "profile:export": lambda arg=None: export_profile(ctx, (arg or {}).get("profileId")),
        "profile:import": lambda arg=None: import_profile(ctx, (arg or {}).get("path") if isinstance(arg, dict) else None),
        "profile:code": lambda arg=None: export_code(ctx, (arg or {}).get("profileId")),
        "profile:code_import": lambda arg=None: import_code(ctx, (arg or {}).get("code")),
    }
