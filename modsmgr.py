"""Менеджер установленных модов / ресурспаков / шейдеров профиля (Modrinth: названия, иконки, обновления).

Порт lib/modsmgr.js. Обработчики: installed:list, installed:toggle, installed:delete, installed:update.
"""
from __future__ import annotations

import os
import re
import urllib.parse

from . import rollback, util
from .mods import MR_BASE, enc

# Три вида установленного: моды, ресурспаки и шейдеры (у паков расширение .zip, отключённые — .zip.disabled)
KINDS = {
    "mod": {"dir": "mods", "re": re.compile(r"\.jar(\.disabled)?$", re.I)},
    "resourcepack": {"dir": "resourcepacks", "re": re.compile(r"\.zip(\.disabled)?$", re.I)},
    "shader": {"dir": "shaderpacks", "re": re.compile(r"\.zip(\.disabled)?$", re.I)},
}
_DISABLED = re.compile(r"\.disabled$", re.I)


def kind_of(k) -> dict:
    return KINDS[k] if isinstance(k, str) and k in KINDS else KINDS["mod"]


def _kind_name(k) -> str:
    return k if isinstance(k, str) and k in KINDS else "mod"


def is_base(f, kind) -> bool:
    """Только имя файла (без папок) с допустимым расширением."""
    return (isinstance(f, str) and f != "" and "/" not in f and "\\" not in f and "\0" not in f
            and f not in (".", "..") and kind_of(kind)["re"].search(f) is not None)


def _primary(files):
    files = files or []
    return next((f for f in files if f.get("primary")), files[0] if files else None)


def enrich(items: list[dict], dir_: str, profile: dict, kind: str) -> None:
    """Дополняет items названиями/иконками/версиями с Modrinth и признаком доступного обновления."""
    for it in items:
        it["hash"] = util.sha1_file(os.path.join(dir_, it["file"]))
    hashes = [i["hash"] for i in items]

    cur = util.post_json(f"{MR_BASE}/version_files", {"hashes": hashes, "algorithm": "sha1"})["data"] or {}
    ids: list[str] = []
    for it in items:
        v = cur.get(it["hash"])
        if v:
            it["projectId"] = v.get("project_id")
            it["versionId"] = v.get("id")
            it["version"] = v.get("version_number")
            if v.get("project_id") not in ids:
                ids.append(v.get("project_id"))

    if ids:
        projects = util.get_json(f"{MR_BASE}/projects?ids={enc(ids)}")
        by_id = {p.get("id"): p for p in projects or []}
        for it in items:
            p = by_id.get(it["projectId"])
            if p:
                it["title"] = p.get("title")
                it["icon"] = p.get("icon_url") or None

    # Доступные обновления: последняя версия под ту же игру и загрузчик
    known = [i for i in items if i["projectId"]]
    # у модов обновление подбирается под загрузчик, у ресурспаков и шейдеров — только под версию игры
    if known and (kind != "mod" or profile.get("loader") != "vanilla"):
        body = {"hashes": [i["hash"] for i in known], "algorithm": "sha1", "game_versions": [profile.get("version")]}
        if kind == "mod":
            body["loaders"] = util.loaders_for(profile.get("loader"))
        upd = util.post_json(f"{MR_BASE}/version_files/update", body, allow_error=True)["data"] or {}
        for it in known:
            v = upd.get(it["hash"]) if isinstance(upd, dict) else None
            if v and v.get("id") != it["versionId"]:
                f = _primary(v.get("files"))
                if f:
                    it["update"] = {"version": v.get("version_number"), "url": f.get("url"), "filename": f.get("filename")}


def handlers(ctx):
    def mods_dir(p, kind):
        return os.path.join(ctx.instance_dir(p["id"]), kind_of(kind)["dir"])

    def listed(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        check = arg.get("check", True)
        kind = _kind_name(arg.get("kind", "mod"))
        dir_ = mods_dir(p, kind)
        try:
            files = os.listdir(dir_)
        except OSError:
            files = []  # папки ещё нет
        rx = kind_of(kind)["re"]
        items = []
        for f in sorted(files, key=lambda s: (s.lower(), s)):
            full = os.path.join(dir_, f)
            if rx.search(f) and os.path.isfile(full):
                items.append({"file": f, "enabled": not _DISABLED.search(f), "size": os.path.getsize(full),
                              "title": None, "icon": None, "version": None, "projectId": None, "update": None})
        checked = False
        if check and items:
            try:
                enrich(items, dir_, p, kind)
                checked = True
            except Exception:  # noqa: BLE001
                pass  # нет сети — показываем просто файлы
        for it in items:
            it.pop("hash", None)
        return {"ok": True, "kind": kind, "items": items, "dir": dir_, "checked": checked,
                "profile": {"id": p["id"], "name": p.get("name"), "version": p.get("version"), "loader": p.get("loader")}}

    def toggle(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        file, kind = arg.get("file"), arg.get("kind", "mod")
        if not p or not is_base(file, kind):
            return {"ok": False, "error": "Неверный файл"}
        dir_ = mods_dir(p, kind)
        nxt = _DISABLED.sub("", file) if _DISABLED.search(file) else file + ".disabled"
        try:
            if not os.path.exists(os.path.join(dir_, file)):
                return {"ok": False, "error": "Файл не найден"}
            os.replace(os.path.join(dir_, file), os.path.join(dir_, nxt))
            return {"ok": True, "file": nxt, "enabled": not _DISABLED.search(nxt)}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def delete(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        file, kind = arg.get("file"), arg.get("kind", "mod")
        if not p or not is_base(file, kind):
            return {"ok": False, "error": "Неверный файл"}
        try:
            try:
                os.remove(os.path.join(mods_dir(p, kind), file))
            except FileNotFoundError:
                pass
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    # Обновление одного мода: скачиваем новый файл рядом, старый удаляем
    def update(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        file, url, filename, kind = arg.get("file"), arg.get("url"), arg.get("filename"), arg.get("kind", "mod")
        if not p or not is_base(file, kind) or not is_base(filename, kind):
            return {"ok": False, "error": "Неверный файл"}
        host = ""
        try:
            u = urllib.parse.urlparse(url)
            if u.scheme == "https":
                host = u.hostname or ""
        except Exception:  # noqa: BLE001
            pass
        if not re.search(r"(^|\.)modrinth\.com$", host):
            return {"ok": False, "error": "Недопустимый адрес загрузки"}
        dir_ = mods_dir(p, kind)
        was_disabled = bool(_DISABLED.search(file))
        target = _DISABLED.sub("", filename) + ".disabled" if was_disabled else filename
        use_rb = kind_of(kind)["dir"] == "mods"  # откат только для модов
        sub = kind_of(kind)["dir"]
        try:
            if use_rb and not arg.get("_keep"):
                rollback.reset(ctx, p["id"])  # новый набор отката
            kept = None
            if use_rb and os.path.isfile(os.path.join(dir_, target)):
                kept = rollback.stash(ctx, p["id"], f"{sub}/{target}", move=True)  # тот же файл будет перезаписан
            try:
                util.download(url, os.path.join(dir_, target))
            except Exception:
                rollback.undo_last(ctx, p["id"], kept)
                raise
            if use_rb:
                rollback.added(ctx, p["id"], f"{sub}/{target}")
            if target != file:
                if use_rb:
                    rollback.stash(ctx, p["id"], f"{sub}/{file}", move=True)
                else:
                    try:
                        os.remove(os.path.join(dir_, file))
                    except FileNotFoundError:
                        pass
            return {"ok": True, "file": target}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # Автообновление: обновляет все моды профиля, у которых есть новая версия (на ту же версию игры и загрузчик)
    def autoupdate(arg=None):
        arg = arg or {}
        r = listed({"profileId": arg.get("profileId"), "check": True, "kind": "mod"})
        if not r.get("ok"):
            return r
        if not r.get("checked"):
            return {"ok": True, "updated": 0, "failed": 0, "names": [], "offline": True}
        names, failed = [], 0
        if any(it.get("update") and it.get("file") for it in r["items"]):
            rollback.reset(ctx, arg.get("profileId"))  # один набор отката на всё автообновление
        for it in r["items"]:
            up = it.get("update")
            if not up or not it.get("file"):
                continue
            one = update({"profileId": arg.get("profileId"), "file": it["file"], "url": up.get("url"),
                          "filename": up.get("filename"), "kind": "mod", "_keep": True})
            if one.get("ok"):
                names.append(it.get("title") or it["file"])
            else:
                failed += 1
        return {"ok": True, "updated": len(names), "failed": failed, "names": names}

    def rb_info(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        return {"ok": True, "count": rollback.count(ctx, p["id"]), "names": rollback.names(ctx, p["id"])[:30]}

    def rb_do(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        return rollback.restore(ctx, p["id"])

    return {"installed:rollback_info": rb_info, "installed:rollback": rb_do, "installed:list": listed, "installed:toggle": toggle, "installed:delete": delete,
            "installed:update": update, "installed:autoupdate": autoupdate}
