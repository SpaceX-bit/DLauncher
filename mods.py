"""Моды / ресурспаки / шейдеры: поиск, версии, установка (Modrinth + CurseForge), иконки, оптимизация.

Порт main.js (блок «Моды…»). Обработчики: mods:search, mods:versions, mods:install, icon:get, opt:list, opt:install.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse

from . import util

CF_LOADER = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
CF_CLASS = {"mod": 6, "resourcepack": 12, "shader": 6552, "modpack": 4471}
KIND_DIR = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
CF_BASE = "https://api.curseforge.com/v1"
MR_BASE = "https://api.modrinth.com/v2"
NEED_KEY = "Для CurseForge нужен API-ключ: вставь его в Настройках (console.curseforge.com)."
NEED_PROFILE = "Сначала создай профиль (вкладка «Профили»)."


class NoVersion(Exception):
    code = "NO_VERSION"


def enc(x) -> str:
    return urllib.parse.quote(json.dumps(x, separators=(",", ":"), ensure_ascii=False), safe="")


def q(s) -> str:
    return urllib.parse.quote(str(s), safe="")


def ok_project_id(x) -> bool:
    return isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", x) is not None


def ok_cf_number(x) -> bool:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == int(f) and 0 < f < 1e10


def mc_summary(lst: list) -> str:
    return ", ".join(lst) if len(lst) <= 3 else f"{lst[0]} … {lst[-1]}"


def _safe_name(name: str) -> str:
    base = os.path.basename(str(name).replace("\\", "/"))
    if not base or base in (".", ".."):
        raise ValueError("Недопустимое имя файла")
    return base


def _primary(files):
    files = files or []
    return next((f for f in files if f.get("primary")), files[0] if files else None)


# ---------- установка ----------
def install_modrinth(id_or_slug, mc, loaders, dir_, seen=None, pinned=None) -> list[str]:
    """Скачивает проект Modrinth и его обязательные зависимости. pinned — уже выбранная версия самого мода."""
    seen = set() if seen is None else seen
    if id_or_slug in seen:
        return []
    seen.add(id_or_slug)
    v = pinned
    if not v:
        url = f"{MR_BASE}/project/{q(id_or_slug)}/version?game_versions={enc([mc])}"
        if loaders:
            url += f"&loaders={enc(loaders)}"
        versions = util.get_json(url)
        if not versions:
            raise NoVersion(f"Нет версии для {mc}")
        v = next((x for x in versions if x.get("version_type") == "release"), versions[0])
    f = _primary(v.get("files"))
    if not f:
        raise ValueError("У этой версии нет файла")
    fname = _safe_name(f["filename"])
    dest = os.path.join(dir_, fname)
    if not os.path.exists(dest):
        util.download(f["url"], dest)
    done = [fname]
    for d in v.get("dependencies") or []:
        if d.get("dependency_type") == "required" and d.get("project_id"):
            try:
                done.extend(install_modrinth(d["project_id"], mc, loaders, dir_, seen))
            except Exception:  # noqa: BLE001
                pass  # зависимость не нашлась — пропускаем
    return done


def cf_headers(ctx) -> dict:
    return {"x-api-key": ctx.settings.get("curseforgeKey", ""), "Accept": "application/json"}


def install_curseforge(ctx, mod_id, mc, loader, dir_, seen=None, file_id=None) -> list[str]:
    seen = set() if seen is None else seen
    if mod_id in seen:
        return []
    seen.add(mod_id)
    if file_id:
        one = util.get_json(f"{CF_BASE}/mods/{mod_id}/files/{file_id}", cf_headers(ctx))
        f = one and one.get("data")
        if not f:
            raise ValueError("Эта версия не найдена на CurseForge")
    else:
        qs = f"gameVersion={q(mc)}&pageSize=10"
        lt = CF_LOADER.get("fabric" if loader == "quilt" else loader)
        if lt:
            qs += f"&modLoaderType={lt}"
        res = util.get_json(f"{CF_BASE}/mods/{mod_id}/files?{qs}", cf_headers(ctx))
        if not res.get("data"):
            raise NoVersion(f"Нет файла для {mc}")
        f = next((x for x in res["data"] if x.get("releaseType") == 1), res["data"][0])
    fname = _safe_name(f["fileName"])
    dest = os.path.join(dir_, fname)
    if not os.path.exists(dest):
        dl = f.get("downloadUrl") or f"https://www.curseforge.com/api/v1/mods/{mod_id}/files/{f['id']}/download"
        util.download(dl, dest)
    done = [fname]
    for d in f.get("dependencies") or []:
        if d.get("relationType") == 3:
            try:
                done.extend(install_curseforge(ctx, d["modId"], mc, loader, dir_, seen))
            except Exception:  # noqa: BLE001
                pass
    return done


def cf_find_mod(ctx, name, slug_name, mc, loader):
    """Ищет мод на CurseForge по названию (только точное совпадение, чтобы не поставить чужое)."""
    lt = CF_LOADER.get("fabric" if loader == "quilt" else loader)
    url = (f"{CF_BASE}/mods/search?gameId=432&classId=6&pageSize=10&sortField=2&sortOrder=desc"
           f"&searchFilter={q(name)}&gameVersion={q(mc)}")
    if lt:
        url += f"&modLoaderType={lt}"
    data = util.get_json(url, cf_headers(ctx))

    def norm(s):
        return re.sub(r"[^a-z0-9]", "", str(s or "").lower())
    for m in data.get("data") or []:
        if norm(m.get("name")) == norm(name) or norm(m.get("slug")) == norm(slug_name):
            return m
    return None


# ---------- иконки ----------
ICON_HOSTS = [re.compile(r"(^|\.)modrinth\.com$"), re.compile(r"(^|\.)forgecdn\.net$"), re.compile(r"(^|\.)curseforge\.com$")]
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
        "image/svg+xml": ".svg", "image/avif": ".avif", "image/bmp": ".bmp"}


def _fetch_icon(url: str):
    status, headers, body = util.request(url, timeout=8, retries=0)
    ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "image/png")
    ctype = ctype.split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        raise ValueError("не картинка")
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("слишком большая")
    return ctype, body


def icon_get(ctx, url):
    """Возвращает путь к локальному файлу иконки (кэш user_data/icon-cache) или None."""
    try:
        u = urllib.parse.urlparse(url)
        if u.scheme != "https" or not any(r.search(u.hostname or "") for r in ICON_HOSTS):
            return None
        cache = os.path.join(ctx.user_data, "icon-cache")
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        if os.path.isdir(cache):
            for name in os.listdir(cache):
                if name.startswith(key + ".") and not name.endswith(".part"):
                    return os.path.join(cache, name)
        for route in (url, f"https://wsrv.nl/?url={q(url)}&w=128&h=128&fit=cover"):
            try:
                ctype, body = _fetch_icon(route)
                os.makedirs(cache, exist_ok=True)
                path = os.path.join(cache, key + _EXT.get(ctype, ".img"))
                with open(path + ".part", "wb") as f:
                    f.write(body)
                os.replace(path + ".part", path)
                return path
            except Exception:  # noqa: BLE001
                continue
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------- оптимизация ----------
OPT_FABRIC = [
    ("sodium", "Sodium", "Новый движок отрисовки — главный буст FPS"),
    ("lithium", "Lithium", "Оптимизация игровой логики и сервера"),
    ("ferrite-core", "FerriteCore", "Меньше потребление памяти"),
    ("entityculling", "Entity Culling", "Не рисует мобов, которых не видно"),
    ("immediatelyfast", "ImmediatelyFast", "Быстрее интерфейс и текст"),
    ("modernfix", "ModernFix", "Быстрый запуск и меньше памяти"),
    ("krypton", "Krypton", "Оптимизация сети"),
    ("dynamic-fps", "Dynamic FPS", "Снижает нагрузку, когда окно не в фокусе"),
    ("sodium-extra", "Sodium Extra", "Доп. настройки Sodium: облака, анимации, частицы"),
    ("moreculling", "More Culling", "Ещё больше отсечения невидимых объектов"),
    ("scalablelux", "ScalableLux", "Быстрое освещение мира"),
    ("noisium", "Noisium", "Быстрее генерация новых территорий"),
    ("memoryleakfix", "Memory Leak Fix", "Исправляет утечки памяти"),
]
OPT_FORGE = [
    ("embeddium", "Embeddium", "Движок отрисовки (аналог Sodium) — буст FPS"),
    ("ferrite-core", "FerriteCore", "Меньше потребление памяти"),
    ("modernfix", "ModernFix", "Быстрый запуск и меньше памяти"),
    ("entityculling", "Entity Culling", "Не рисует мобов, которых не видно"),
    ("immediatelyfast", "ImmediatelyFast", "Быстрее интерфейс и текст"),
    ("dynamic-fps", "Dynamic FPS", "Снижает нагрузку, когда окно не в фокусе"),
    ("moreculling", "More Culling", "Ещё больше отсечения невидимых объектов"),
    ("memoryleakfix", "Memory Leak Fix", "Исправляет утечки памяти"),
]


def opt_list(loader):
    if loader in ("forge", "neoforge"):
        return OPT_FORGE
    if loader in ("fabric", "quilt"):
        return OPT_FABRIC
    return []


# ---------- обработчики ----------
def handlers(ctx):
    def profile_of(pid):
        return ctx.find_profile(pid or ctx.settings.get("currentProfile"))

    def search(arg=None):
        arg = arg or {}
        source, query, mc, loader = arg.get("source"), arg.get("query"), arg.get("mc"), arg.get("loader")
        kind = arg.get("kind") or "mod"
        try:
            offset = int(float(arg.get("offset") or 0))
        except (TypeError, ValueError):
            offset = 0
        try:
            if source == "modrinth":
                facets = [[f"project_type:{kind}"]]
                if mc:
                    facets.append([f"versions:{mc}"])
                if kind == "mod" and loader and loader != "vanilla":
                    facets.append([f"categories:{loader}"])
                url = (f"{MR_BASE}/search?limit=40&offset={offset}&index={'relevance' if query else 'downloads'}"
                       f"&query={q(query or '')}&facets={enc(facets)}")
                data = util.get_json(url)
                return {"ok": True, "total": data.get("total_hits"),
                        "items": [{"id": h.get("project_id"), "title": h.get("title"), "description": h.get("description"),
                                   "icon": h.get("icon_url"), "downloads": h.get("downloads"), "author": h.get("author")}
                                  for h in data.get("hits", [])]}
            if not ctx.settings.get("curseforgeKey"):
                return {"ok": False, "error": NEED_KEY}
            url = (f"{CF_BASE}/mods/search?gameId=432&classId={CF_CLASS.get(kind, 6)}&pageSize=40&index={offset}"
                   f"&sortField={2 if query else 6}&sortOrder=desc&searchFilter={q(query or '')}")
            if mc:
                url += f"&gameVersion={q(mc)}"
            if kind == "mod" and CF_LOADER.get(loader):
                url += f"&modLoaderType={CF_LOADER[loader]}"
            data = util.get_json(url, cf_headers(ctx))
            items = []
            for m in data.get("data", []):
                authors = m.get("authors") or []
                items.append({"id": m.get("id"), "title": m.get("name"), "description": m.get("summary"),
                              "icon": (m.get("logo") or {}).get("thumbnailUrl"), "downloads": m.get("downloadCount"),
                              "author": authors[0].get("name") if authors else None})
            return {"ok": True, "total": (data.get("pagination") or {}).get("totalCount"), "items": items}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def versions(arg=None):
        arg = arg or {}
        source, id_, kind = arg.get("source"), arg.get("id"), arg.get("kind") or "mod"
        try:
            profile = profile_of(arg.get("profileId"))
            if not profile:
                return {"ok": False, "error": NEED_PROFILE}
            mc, loader = profile["version"], profile["loader"]
            need_loader = kind == "mod" and loader != "vanilla"
            info = {"version": mc, "loader": loader}
            if source == "modrinth":
                if not ok_project_id(id_):
                    return {"ok": False, "error": "Неверный мод"}
                want = util.loaders_for(loader)
                lst = util.get_json(f"{MR_BASE}/project/{q(id_)}/version")
                items = []
                for v in lst[:150]:
                    gv, ld = v.get("game_versions") or [], v.get("loaders") or []
                    items.append({"id": v.get("id"), "name": v.get("name") or v.get("version_number"),
                                  "number": v.get("version_number"), "mc": mc_summary(gv), "loaders": ld,
                                  "type": v.get("version_type") or "release", "date": v.get("date_published"),
                                  "fit": mc in gv and (not need_loader or any(l in want for l in ld))})
                return {"ok": True, "profile": info, "items": items}
            if not ctx.settings.get("curseforgeKey"):
                return {"ok": False, "error": NEED_KEY}
            if not ok_cf_number(id_):
                return {"ok": False, "error": "Неверный мод"}
            res = util.get_json(f"{CF_BASE}/mods/{int(float(id_))}/files?pageSize=50", cf_headers(ctx))
            want_cf = ["quilt", "fabric"] if loader == "quilt" else [loader]
            items = []
            for f in res.get("data") or []:
                gv = f.get("gameVersions") or []
                low = [str(g).lower() for g in gv]
                mcs = [g for g in gv if re.match(r"^\d", str(g))]
                rt = f.get("releaseType")
                items.append({"id": str(f.get("id")), "name": f.get("displayName") or f.get("fileName"),
                              "mc": mc_summary(mcs),
                              "loaders": [g for g in low if re.fullmatch(r"fabric|forge|neoforge|quilt", g)],
                              "type": "release" if rt == 1 else "beta" if rt == 2 else "alpha",
                              "date": f.get("fileDate"),
                              "fit": mc in gv and (not need_loader or any(l in low for l in want_cf))})
            return {"ok": True, "profile": info, "items": items}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def install(arg=None):
        arg = arg or {}
        source, id_, kind, version_id = arg.get("source"), arg.get("id"), arg.get("kind") or "mod", arg.get("versionId")
        try:
            profile = profile_of(arg.get("profileId"))
            if not profile:
                return {"ok": False, "error": NEED_PROFILE}
            mc, loader = profile["version"], profile["loader"]
            if version_id:
                good = (ok_project_id(version_id) and ok_project_id(id_)) if source == "modrinth" \
                    else (ok_cf_number(version_id) and ok_cf_number(id_))
                if not good:
                    return {"ok": False, "error": "Неверная версия"}
            if kind == "mod" and loader == "vanilla":
                return {"ok": False, "error": "В профиле выбран Vanilla — моды ставятся только на Fabric, Forge, NeoForge или Quilt. Создай профиль с загрузчиком."}
            d = os.path.join(ctx.ensure_instance(profile["id"]), KIND_DIR.get(kind, "mods"))
            os.makedirs(d, exist_ok=True)
            if source == "modrinth":
                pinned = None
                if version_id:
                    pinned = util.get_json(f"{MR_BASE}/version/{q(version_id)}")
                    if not pinned or pinned.get("project_id") != id_:
                        return {"ok": False, "error": "Эта версия не относится к выбранному моду"}
                files = install_modrinth(id_, mc, util.loaders_for(loader) if kind == "mod" else None, d, set(), pinned)
                return {"ok": True, "filename": files[0], "extra": len(files) - 1}
            if not ctx.settings.get("curseforgeKey"):
                return {"ok": False, "error": NEED_KEY}
            files = install_curseforge(ctx, id_, mc, loader if kind == "mod" else None, d, set(), version_id or None)
            return {"ok": True, "filename": files[0], "extra": len(files) - 1}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def icon(url=None):
        return icon_get(ctx, url) if isinstance(url, str) else None

    def opt_list_h(loader=None):
        return [{"slug": s, "name": n, "desc": d} for s, n, d in opt_list(loader)]

    def opt_install(arg=None):
        arg = arg or {}
        profile = profile_of(arg.get("profileId"))
        if not profile:
            return {"ok": False, "error": NEED_PROFILE}
        mc, loader = profile["version"], profile["loader"]
        lst = opt_list(loader)
        if not lst:
            return {"ok": False, "error": "Для Vanilla оптимизация модами недоступна — создай профиль с Fabric, Forge, NeoForge или Quilt."}
        d = os.path.join(ctx.ensure_instance(profile["id"]), "mods")
        seen_mr, seen_cf = set(), set()
        stats = {"installed": 0, "skipped": 0, "failed": 0, "needKey": 0, "bySource": {"modrinth": 0, "curseforge": 0}}
        key = ctx.settings.get("curseforgeKey")
        for slug_name, name, _desc in lst:
            ctx.send("opt:progress", {"slug": slug_name, "status": "loading"})
            source = file = mr_err = cf_err = None
            try:
                files = install_modrinth(slug_name, mc, util.loaders_for(loader), d, seen_mr)
                source, file = "Modrinth", files[0] if files else None
            except Exception as e:  # noqa: BLE001
                mr_err = e
            if not source and key:
                try:
                    m = cf_find_mod(ctx, name, slug_name, mc, loader)
                    if not m:
                        raise NoVersion("не найден на CurseForge")
                    files = install_curseforge(ctx, m["id"], mc, loader, d, seen_cf)
                    source, file = "CurseForge", files[0] if files else None
                except Exception as e:  # noqa: BLE001
                    cf_err = e
            if source:
                stats["installed"] += 1
                stats["bySource"]["modrinth" if source == "Modrinth" else "curseforge"] += 1
                ctx.send("opt:progress", {"slug": slug_name, "status": "ok", "detail": file, "source": source})
                continue
            if not key:
                stats["needKey"] += 1
            real = next((e for e in (mr_err, cf_err) if e is not None and getattr(e, "code", None) != "NO_VERSION"), None)
            if real is not None:
                stats["failed"] += 1
                ctx.send("opt:progress", {"slug": slug_name, "status": "fail", "detail": str(real)})
            else:
                stats["skipped"] += 1
                ctx.send("opt:progress", {"slug": slug_name, "status": "skip", "detail": f"Нет версии для {mc}"})
        return {"ok": True, **stats}

    return {"mods:search": search, "mods:versions": versions, "mods:install": install, "icon:get": icon,
            "opt:list": opt_list_h, "opt:install": opt_install}
