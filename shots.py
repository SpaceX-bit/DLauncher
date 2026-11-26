"""Галерея скриншотов профиля. Порт lib/shots.js. Вместо file:// адресов отдаём локальные пути (поле path)."""
from __future__ import annotations

import os
import re

IMG = re.compile(r"\.(png|jpe?g)$", re.I)
LIMIT = 400


def _is_base(f) -> bool:
    return isinstance(f, str) and bool(f) and os.path.basename(f) == f and bool(IMG.search(f))


def handlers(ctx):
    def profile_of(pid):
        return ctx.find_profile(pid or ctx.settings.get("currentProfile"))

    def dir_of(p):
        return os.path.join(ctx.instance_dir(p["id"]), "screenshots")

    def s_list(arg=None):
        p = profile_of((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        d = dir_of(p)
        items = []
        try:
            for name in os.listdir(d):
                full = os.path.join(d, name)
                if os.path.isfile(full) and IMG.search(name):
                    st = os.stat(full)
                    items.append({"file": name, "path": full, "url": full, "size": st.st_size, "time": st.st_mtime * 1000})
        except OSError:
            pass
        items.sort(key=lambda x: -x["time"])
        return {"ok": True, "total": len(items), "items": items[:LIMIT], "profile": {"id": p["id"], "name": p["name"]}}

    def resolve(arg):
        arg = arg or {}
        p = profile_of(arg.get("profileId"))
        if not p or not _is_base(arg.get("file")):
            return None
        full = os.path.join(dir_of(p), arg["file"])
        return full if os.path.exists(full) else None

    def s_open(arg=None):
        full = resolve(arg)
        if not full:
            return {"ok": False, "error": "Файл не найден"}
        ctx.ui.open_path(full)
        return {"ok": True}

    def s_copy(arg=None):
        full = resolve(arg)
        if not full:
            return {"ok": False, "error": "Файл не найден"}
        try:
            ctx.ui.set_clipboard_image(full)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def s_delete(arg=None):
        full = resolve(arg)
        if not full:
            return {"ok": False, "error": "Файл не найден"}
        try:
            os.remove(full)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    return {"shots:list": s_list, "shots:open": s_open, "shots:copy": s_copy, "shots:delete": s_delete}
