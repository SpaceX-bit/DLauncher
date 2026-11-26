"""Установка сборок (модпаков) с Modrinth (.mrpack) и CurseForge как отдельных профилей.

Порт lib/modpacks.js. Обработчики: pack:versions, pack:install. Публично: import_mrpack(ctx, file, title),
allowed_url(url). События: pack:progress {text, done, total}.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse

from . import util
from .mods import CF_BASE, MR_BASE, NEED_KEY, ok_cf_number, ok_project_id
from .ziputil import ZipReader

CF_DIRS = {12: "resourcepacks", 6552: "shaderpacks"}  # остальное — mods
# Спецификация .mrpack разрешает скачивание только с этих серверов (файл мог прислать кто угодно)
MRPACK_HOSTS = ["cdn.modrinth.com", "github.com", "raw.githubusercontent.com", "gitlab.com"]

_state_lock = threading.Lock()


def allowed_url(u) -> bool:
    try:
        x = urllib.parse.urlparse(str(u))
        return x.scheme == "https" and (x.hostname or "") in MRPACK_HOSTS
    except Exception:  # noqa: BLE001
        return False


def _chunk(arr: list, n: int) -> list[list]:
    return [arr[i:i + n] for i in range(0, len(arr), n)]


def _primary(files):
    files = files or []
    return next((f for f in files if f.get("primary")), files[0] if files else None)


def _busy(ctx) -> dict:
    """Общий замок на установку сборки (две сборки одновременно не ставим)."""
    with _state_lock:
        st = getattr(ctx, "_pack_state", None)
        if st is None:
            st = {"busy": False}
            ctx._pack_state = st
        return st


def _acquire(ctx) -> bool:
    st = _busy(ctx)
    with _state_lock:
        if st["busy"]:
            return False
        st["busy"] = True
        return True


def _release(ctx) -> None:
    st = _busy(ctx)
    with _state_lock:
        st["busy"] = False


def _progress(ctx, text, done=0, total=0) -> None:
    ctx.send("pack:progress", {"text": text, "done": done, "total": total})


def packs_cache(ctx) -> str:
    return os.path.join(ctx.settings["rootDir"], "cache", "packs")


def _pool_run(items, worker, limit=4):
    """Параллельный запуск; исключения не должны вылетать из worker (их ловит сам worker)."""
    util.pool(items, limit, worker)


# ---------- Modrinth (.mrpack) ----------
def install_modrinth_pack(ctx, id_, title, version_id=None) -> dict:
    _progress(ctx, "Получаю версию сборки...")
    if version_id:
        ver = util.get_json(f"{MR_BASE}/version/{urllib.parse.quote(str(version_id), safe='')}")
        if not ver or ver.get("project_id") != id_:
            raise ValueError("Эта версия не относится к выбранной сборке")
    else:
        versions = util.get_json(f"{MR_BASE}/project/{urllib.parse.quote(str(id_), safe='')}/version")
        if not versions:
            raise ValueError("У сборки нет доступных версий")
        ver = next((v for v in versions if v.get("version_type") == "release"), versions[0])
    f = _primary(ver.get("files"))
    if not f:
        raise ValueError("У этой версии сборки нет файла")

    archive = os.path.join(packs_cache(ctx), f"{id_}-{ver['id']}.mrpack")
    _progress(ctx, "Скачиваю сборку...")
    util.download(f["url"], archive, lambda p: _progress(ctx, f"Скачиваю сборку: {p}%", p, 100))
    return install_mrpack_from_archive(
        ctx, archive, {"source": "modrinth", "id": id_, "version": ver.get("version_number"), "versionId": ver.get("id")}, title)


def parse_index(index_text) -> tuple[dict, str, str, str]:
    """modrinth.index.json -> (index, minecraft, loader, loaderVersion)."""
    if not index_text:
        raise ValueError("В архиве нет modrinth.index.json — это не сборка Modrinth")
    try:
        index = json.loads(index_text)
        if not isinstance(index, dict):
            raise ValueError
    except ValueError:
        raise ValueError("Файл modrinth.index.json повреждён") from None
    deps = index.get("dependencies") or {}
    mc = deps.get("minecraft")
    if not mc:
        raise ValueError("В сборке не указана версия Minecraft")
    loader, loader_version = "vanilla", ""
    if deps.get("fabric-loader"):
        loader, loader_version = "fabric", deps["fabric-loader"]
    elif deps.get("quilt-loader"):
        loader, loader_version = "quilt", deps["quilt-loader"]
    elif deps.get("neoforge"):
        loader, loader_version = "neoforge", deps["neoforge"]
    elif deps.get("forge"):
        loader, loader_version = "forge", deps["forge"]
    return index, str(mc), loader, str(loader_version)


def download_index_files(ctx, index: dict, dir_: str) -> tuple[list[str], list[str]]:
    """Скачивает файлы из index["files"] в dir_. Возвращает (скачанные пути, ошибки)."""
    files = [f for f in (index.get("files") or [])
             if isinstance(f, dict) and not ((f.get("env") or {}).get("client") == "unsupported")]
    counter = {"done": 0}
    failed: list[str] = []
    got: list[str] = []
    lock = threading.Lock()

    def one(f, _i):
        ok, last_err, dest = False, "", None
        downloads = [u for u in (f.get("downloads") or []) if allowed_url(u)]
        try:
            dest = util.safe_join(dir_, f.get("path"))
        except Exception as e:  # noqa: BLE001
            last_err = str(e)  # файл вне папки профиля — не качаем
        if dest and not downloads:
            last_err = "недопустимый адрес загрузки"
        for url in (downloads if dest else []):
            try:
                util.download(url, dest)
                want = (f.get("hashes") or {}).get("sha1")
                if want and util.sha1_file(dest) != want:
                    os.remove(dest)
                    raise ValueError("не совпала контрольная сумма")
                ok = True
                break
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
        with lock:
            if ok:
                got.append(str(f.get("path")).replace("\\", "/"))
            else:
                name = os.path.basename(str(f.get("path") or "").replace("\\", "/"))
                failed.append(f"{name}{' (' + last_err + ')' if last_err else ''}")
            counter["done"] += 1
            n = counter["done"]
        _progress(ctx, f"Скачиваю файлы сборки: {n}/{len(files)}", n, len(files))

    _pool_run(files, one)
    return got, failed


def install_from_index(ctx, index: dict, pack_meta: dict, title, zip_=None) -> dict:
    """Создаёт профиль по готовому index (из .mrpack или из кода сборки). zip_ — архив с папкой overrides, если он есть."""
    _idx, mc, loader, loader_version = parse_index(json.dumps(index))
    profile = ctx.create_profile({
        "name": index.get("name") or title or "Сборка", "version": mc, "loader": loader,
        "loaderVersion": loader_version, "pack": pack_meta,
    })
    dir_ = ctx.instance_dir(profile["id"])
    got, failed = download_index_files(ctx, index, dir_)
    if zip_ is not None:
        _progress(ctx, "Копирую настройки сборки...")
        zip_.extract_prefix("overrides/", dir_)
        zip_.extract_prefix("client-overrides/", dir_)
    profile["packFiles"] = got
    ctx.save_settings()
    return {"profile": profile, "missing": failed}


def install_mrpack_from_archive(ctx, archive: str, pack_meta: dict, title) -> dict:
    """Установка из готового файла .mrpack (скачанного или выбранного пользователем)."""
    with ZipReader(archive) as zip_:
        index, _mc, _l, _lv = parse_index(zip_.read_text("modrinth.index.json"))
        return install_from_index(ctx, index, pack_meta, title, zip_)


def update_pack(ctx, profile: dict, version: dict) -> dict:
    """Обновляет сборку на месте до версии version (Modrinth). Миры и свои настройки не трогает.
    Файлы старой версии откладываются — их можно вернуть кнопкой «Откатить»."""
    from . import rollback
    pid = profile["id"]
    old = profile.get("packFiles")
    if not isinstance(old, list) or not old:
        raise ValueError("Эту сборку поставила старая версия лаунчера — перед обновлением переустанови её один раз")
    f = _primary(version.get("files"))
    if not f:
        raise ValueError("У этой версии сборки нет файла")
    pack = profile.get("pack") or {}
    archive = os.path.join(packs_cache(ctx), f"{pack.get('id')}-{version['id']}.mrpack")
    _progress(ctx, "Скачиваю обновление сборки...")
    util.download(f["url"], archive, lambda p: _progress(ctx, f"Скачиваю обновление: {p}%", p, 100))
    dir_ = ctx.instance_dir(pid)
    with ZipReader(archive) as zip_:
        index, mc, loader, lv = parse_index(zip_.read_text("modrinth.index.json"))
        new_paths = {str(x.get("path")).replace("\\", "/") for x in (index.get("files") or []) if isinstance(x, dict)}
        rollback.reset(ctx, pid)
        for rel in old:  # файлы, которых в новой версии уже нет, и те, что заменятся
            if isinstance(rel, str):
                rollback.stash(ctx, pid, rel, move=True)
        keep = {}
        for one in ("options.txt", "servers.dat"):  # свои настройки игрока не затираем
            fp = os.path.join(dir_, one)
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    keep[fp] = fh.read()
        got, failed = download_index_files(ctx, index, dir_)
        _progress(ctx, "Копирую настройки сборки...")
        zip_.extract_prefix("overrides/", dir_)
        zip_.extract_prefix("client-overrides/", dir_)
        for fp, data in keep.items():
            with open(fp, "wb") as fh:
                fh.write(data)
    for rel in got:
        rollback.added(ctx, pid, rel)
    with ctx.lock:
        profile.update({"version": mc, "loader": loader, "loaderVersion": lv, "packFiles": got,
                        "pack": {**pack, "version": version.get("version_number"), "versionId": version.get("id")}})
        ctx.save_settings()
    return {"missing": failed, "version": version.get("version_number"), "removed": len(set(old) - new_paths)}


# ---------- CurseForge ----------
def install_curseforge_pack(ctx, id_, title, file_id=None) -> dict:
    key = ctx.settings.get("curseforgeKey")
    if not key:
        raise ValueError(NEED_KEY)
    headers = {"x-api-key": key, "Accept": "application/json"}

    _progress(ctx, "Получаю версию сборки...")
    if file_id:
        one = util.get_json(f"{CF_BASE}/mods/{id_}/files/{file_id}", headers)
        f = one and one.get("data")
        if not f:
            raise ValueError("Эта версия сборки не найдена на CurseForge")
    else:
        lst = util.get_json(f"{CF_BASE}/mods/{id_}/files?pageSize=10", headers)
        if not lst.get("data"):
            raise ValueError("У сборки нет доступных файлов")
        f = next((x for x in lst["data"] if x.get("releaseType") == 1), lst["data"][0])

    archive = os.path.join(packs_cache(ctx), f"cf-{id_}-{f['id']}.zip")
    url = f.get("downloadUrl") or f"https://www.curseforge.com/api/v1/mods/{id_}/files/{f['id']}/download"
    _progress(ctx, "Скачиваю сборку...")
    util.download(url, archive, lambda p: _progress(ctx, f"Скачиваю сборку: {p}%", p, 100))

    with ZipReader(archive) as zip_:
        text = zip_.read_text("manifest.json")
        if not text:
            raise ValueError("В архиве нет manifest.json — это не сборка CurseForge")
        try:
            manifest = json.loads(text)
            if not isinstance(manifest, dict):
                raise ValueError
        except ValueError:
            raise ValueError("Файл manifest.json повреждён") from None
        mcinfo = manifest.get("minecraft") or {}
        mc = mcinfo.get("version")
        if not mc:
            raise ValueError("В сборке не указана версия Minecraft")

        mls = mcinfo.get("modLoaders") or []
        first = next((m for m in mls if m.get("primary")), mls[0] if mls else {})
        ml = first.get("id") or ""
        cut = ml.find("-")
        loader = ml[:cut].lower() if cut > 0 else "vanilla"
        loader_version = ml[cut + 1:] if cut > 0 else ""

        profile = ctx.create_profile({
            "name": manifest.get("name") or title or "Сборка", "version": mc,
            "loader": loader if loader in ("fabric", "forge", "neoforge", "quilt") else "vanilla",
            "loaderVersion": loader_version,
            "pack": {"source": "curseforge", "id": id_, "version": manifest.get("version") or str(f["id"])},
        })
        dir_ = ctx.instance_dir(profile["id"])

        entries = [e for e in (manifest.get("files") or []) if e.get("required") is not False]
        _progress(ctx, "Получаю список файлов...")
        file_info: dict = {}
        for part in _chunk([e.get("fileID") for e in entries], 100):
            r = util.post_json(f"{CF_BASE}/mods/files", {"fileIds": part}, headers)
            for x in ((r.get("data") or {}).get("data") or []):
                file_info[x.get("id")] = x
        class_of: dict = {}
        pids = list(dict.fromkeys(e.get("projectID") for e in entries))
        for part in _chunk(pids, 50):
            try:
                r = util.post_json(f"{CF_BASE}/mods", {"modIds": part}, headers)
                for m in ((r.get("data") or {}).get("data") or []):
                    class_of[m.get("id")] = m.get("classId")
            except Exception:  # noqa: BLE001
                pass  # без классов всё пойдёт в mods

        counter = {"done": 0}
        failed: list[str] = []
        lock = threading.Lock()

        def one(e, _i):
            info = file_info.get(e.get("fileID"))
            name = info.get("fileName") if info else f"{e.get('projectID')}-{e.get('fileID')}"
            try:
                if not info:
                    raise ValueError("файл не найден на CurseForge")
                sub = CF_DIRS.get(class_of.get(e.get("projectID")), "mods")
                dl = info.get("downloadUrl") or \
                    f"https://www.curseforge.com/api/v1/mods/{e.get('projectID')}/files/{e.get('fileID')}/download"
                util.download(dl, util.safe_join(dir_, f"{sub}/{info.get('fileName')}"))
            except Exception as err:  # noqa: BLE001
                msg = re.sub(r" — https?://\S+", "", str(err))
                with lock:
                    failed.append(f"{name} ({msg})")
            with lock:
                counter["done"] += 1
                n = counter["done"]
            _progress(ctx, f"Скачиваю файлы сборки: {n}/{len(entries)}", n, len(entries))

        _pool_run(entries, one)

        _progress(ctx, "Копирую настройки сборки...")
        ov = str(manifest.get("overrides") or "overrides").rstrip("/")
        zip_.extract_prefix(f"{ov}/", dir_)
    return {"profile": profile, "missing": failed}


def import_mrpack(ctx, file: str, title=None) -> dict:
    """Установка профиля из локального .mrpack. Возвращает {profile, missing}; ошибки — исключением."""
    if not _acquire(ctx):
        raise RuntimeError("Другая сборка уже устанавливается")
    try:
        r = install_mrpack_from_archive(ctx, file, {"source": "file", "id": "", "version": ""}, title)
        _progress(ctx, "Готово", 1, 1)
        return r
    finally:
        _release(ctx)


def import_index(ctx, index: dict, title=None) -> dict:
    """Установка профиля по готовому index (код сборки)."""
    if not _acquire(ctx):
        raise RuntimeError("Другая сборка уже устанавливается")
    try:
        r = install_from_index(ctx, index, {"source": "code", "id": "", "version": ""}, title)
        _progress(ctx, "Готово", 1, 1)
        return r
    finally:
        _release(ctx)


# ---------- обработчики ----------
def handlers(ctx):
    def versions(arg=None):
        arg = arg or {}
        source, id_ = arg.get("source"), arg.get("id")
        try:
            if source == "curseforge":
                if not ok_cf_number(id_):
                    return {"ok": False, "error": "Неверная сборка"}
                key = ctx.settings.get("curseforgeKey")
                if not key:
                    return {"ok": False, "error": NEED_KEY}
                r = util.get_json(f"{CF_BASE}/mods/{int(float(id_))}/files?pageSize=50",
                                  {"x-api-key": key, "Accept": "application/json"})
                items = []
                for f in r.get("data") or []:
                    gv = f.get("gameVersions") or []
                    rt = f.get("releaseType")
                    items.append({
                        "id": str(f.get("id")), "name": f.get("displayName") or f.get("fileName"),
                        "mc": ", ".join([g for g in gv if re.match(r"^\d", str(g))][:3]),
                        "loaders": [str(g).lower() for g in gv if re.fullmatch(r"fabric|forge|neoforge|quilt", str(g), re.I)],
                        "type": "release" if rt == 1 else "beta" if rt == 2 else "alpha",
                        "date": f.get("fileDate"), "downloads": f.get("downloadCount"),
                    })
                return {"ok": True, "items": items}
            if not ok_project_id(id_):
                return {"ok": False, "error": "Неверная сборка"}
            lst = util.get_json(f"{MR_BASE}/project/{urllib.parse.quote(id_, safe='')}/version")
            return {"ok": True, "items": [{
                "id": v.get("id"), "name": v.get("name") or v.get("version_number"), "number": v.get("version_number"),
                "mc": ", ".join((v.get("game_versions") or [])[-3:]), "loaders": v.get("loaders") or [],
                "type": v.get("version_type") or "release", "date": v.get("date_published"),
                "downloads": v.get("downloads"),
            } for v in lst[:80]]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def install(arg=None):
        arg = arg or {}
        source, id_, title, version_id = arg.get("source"), arg.get("id"), arg.get("title"), arg.get("versionId")
        cf = source == "curseforge"
        bad = (not ok_cf_number(id_) or (version_id and not ok_cf_number(version_id))) if cf \
            else (not ok_project_id(id_) or (version_id and not ok_project_id(version_id)))
        if bad:
            return {"ok": False, "error": "Неверная сборка"}
        if cf:
            id_ = int(float(id_))
            version_id = int(float(version_id)) if version_id else None
        if not _acquire(ctx):
            return {"ok": False, "error": "Другая сборка уже устанавливается"}
        try:
            r = install_curseforge_pack(ctx, id_, title, version_id) if cf \
                else install_modrinth_pack(ctx, id_, title, version_id)
            _progress(ctx, "Готово", 1, 1)
            return {"ok": True, "profile": r["profile"], "missing": r["missing"]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            _release(ctx)

    def newer(profile):
        """Самая свежая версия сборки на Modrinth, если она новее установленной."""
        pack = profile.get("pack") or {}
        if pack.get("source") != "modrinth" or not ok_project_id(pack.get("id")):
            return None
        lst = util.get_json(f"{MR_BASE}/project/{urllib.parse.quote(pack['id'], safe='')}/version")
        rel = [v for v in lst if v.get("version_type") == "release"] or lst
        cur_id, cur_num = pack.get("versionId"), pack.get("version")
        pos = next((i for i, v in enumerate(lst) if v.get("id") == cur_id or (not cur_id and v.get("version_number") == cur_num)), None)
        if pos is None or not rel:
            return None
        top = rel[0]
        if top.get("id") == lst[pos].get("id"):
            return None
        if lst.index(top) >= pos:  # самая свежая «релизная» не новее установленной
            return None
        return top

    def updates(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        try:
            v = newer(p)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if not v:
            return {"ok": True, "available": False}
        return {"ok": True, "available": True, "version": v.get("version_number"), "name": v.get("name"),
                "canUpdate": bool(p.get("packFiles"))}

    def update(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        if not _acquire(ctx):
            return {"ok": False, "error": "Другая сборка уже устанавливается"}
        try:
            v = newer(p)
            if not v:
                return {"ok": True, "updated": False}
            r = update_pack(ctx, p, v)
            _progress(ctx, "Готово", 1, 1)
            return {"ok": True, "updated": True, "version": r["version"], "missing": r["missing"]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            _release(ctx)

    return {"pack:versions": versions, "pack:install": install, "pack:updates": updates, "pack:update": update}
