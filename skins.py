"""Скины и плащи аккаунта Microsoft. Порт lib/skins.js.
Картинки отдаём локальными путями (кеш user_data/skin-cache) вместо data:-адресов."""
from __future__ import annotations

import json
import os
import re
import secrets
import struct
import urllib.parse

from . import util

API = "https://api.minecraftservices.com/minecraft/profile"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_SKIN = 100 * 1024
MAX_CAPE = 300 * 1024


def png_size(buf: bytes):
    if not isinstance(buf, (bytes, bytearray)) or len(buf) < 24 or bytes(buf[:8]) != PNG_SIG:
        return None
    w, h = struct.unpack(">II", bytes(buf[16:24]))
    return {"width": w, "height": h}


class _Soft(Exception):
    soft = True


def handlers(ctx):
    state = {"pending": None}
    cache_dir = os.path.join(ctx.user_data, "skin-cache")

    def req(url, method="GET", headers=None, body=None):
        """-> (status, bytes). Ошибки HTTP не бросают исключение."""
        try:
            st, _h, data = util.request(url, method, headers, body, timeout=15, retries=0)
            return st, data
        except util.HttpError as e:
            return e.status, e.data or b""

    def authed():
        if ctx.settings.get("accountMode") != "microsoft":
            raise _Soft("Скины можно менять только у аккаунта Microsoft: включи режим Microsoft в Настройках.")
        a = ctx.msauth.get_launch_auth()
        return {"Authorization": f"Bearer {a['access_token']}"}

    def explain(status):
        if status in (401, 403):
            return "Сессия Microsoft истекла: войди заново в Настройках."
        if status == 429:
            return "Слишком много запросов. Подожди минуту и попробуй снова."
        if status == 400:
            return "Mojang не принял файл: нужен PNG 64×64 (или 64×32)."
        return f"Ошибка сервера Mojang ({status})."

    def fetch_texture(url, limit):
        try:
            u = urllib.parse.urlparse(re.sub(r"^http://", "https://", str(url), flags=re.I))
        except ValueError:
            return None
        if u.scheme != "https" or u.hostname != "textures.minecraft.net":
            return None
        st, data = req(u.geturl())
        if st != 200 or len(data) > limit or not png_size(data):
            return None
        return data

    def save_image(data: bytes, prefix: str):
        os.makedirs(cache_dir, exist_ok=True)
        p = os.path.join(cache_dir, f"{prefix}-{util.sha1_bytes(data)[:16]}.png")
        if not os.path.exists(p):
            with open(p, "wb") as f:
                f.write(data)
        return p

    def current():
        headers = authed()
        st, data = req(API, headers=headers)
        if st != 200:
            raise RuntimeError(explain(st))
        j = json.loads(data.decode("utf-8"))
        skins = j.get("skins") or []
        skin = next((s for s in skins if s.get("state") == "ACTIVE"), None) or (skins[0] if skins else None)
        skin_image = None
        if skin and skin.get("url"):
            try:
                b = fetch_texture(skin["url"], MAX_SKIN)
                if b:
                    skin_image = save_image(b, "skin")
            except Exception:  # noqa: BLE001
                pass
        capes = []
        for c in j.get("capes") or []:
            image = None
            try:
                b = fetch_texture(c["url"], MAX_CAPE) if c.get("url") else None
                if b:
                    image = save_image(b, "cape")
            except Exception:  # noqa: BLE001
                pass
            capes.append({"id": str(c.get("id")), "name": str(c.get("alias") or "Cape")[:40],
                          "active": c.get("state") == "ACTIVE", "image": image})
        return {"ok": True, "name": j.get("name"), "uuid": j.get("id"), "skin": skin_image,
                "variant": "slim" if skin and str(skin.get("variant")).upper() == "SLIM" else "classic", "capes": capes}

    def fail(e):
        return {"ok": False, "error": str(e), "soft": bool(getattr(e, "soft", False))}

    def s_get(_=None):
        try:
            return current()
        except Exception as e:  # noqa: BLE001
            return fail(e)

    def s_choose(_=None):
        try:
            en = ctx.settings.get("lang") == "en"
            f = ctx.ui.open_file("Choose a skin file (PNG 64×64)" if en else "Выбери файл скина (PNG 64×64)", [("PNG", ["png"])])
            if not f:
                return {"ok": False, "canceled": True}
            if os.path.getsize(f) > MAX_SKIN:
                return {"ok": False, "error": "Файл слишком большой для скина (больше 100 КБ)."}
            with open(f, "rb") as fh:
                buf = fh.read()
            size = png_size(buf)
            if not size:
                return {"ok": False, "error": "Это не PNG-картинка."}
            if not (size["width"] == 64 and size["height"] in (64, 32)):
                return {"ok": False, "error": f"Размер скина должен быть 64×64 (или 64×32), а у файла {size['width']}×{size['height']}."}
            state["pending"] = {"buf": buf, "name": os.path.basename(f)[:60]}
            return {"ok": True, "name": state["pending"]["name"], "image": save_image(buf, "pending"), "legacy": size["height"] == 32}
        except Exception as e:  # noqa: BLE001
            return fail(e)

    def s_apply(arg=None):
        try:
            pend = state["pending"]
            if not pend:
                return {"ok": False, "error": "Сначала выбери файл скина."}
            headers = authed()
            variant = "slim" if (arg or {}).get("variant") == "slim" else "classic"
            boundary = "----dl" + secrets.token_hex(12)
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"variant\"\r\n\r\n{variant}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"skin.png\"\r\n"
                    f"Content-Type: image/png\r\n\r\n").encode() + pend["buf"] + f"\r\n--{boundary}--\r\n".encode()
            st, _ = req(f"{API}/skins", "POST", {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}, body)
            if st not in (200, 204):
                return {"ok": False, "error": explain(st)}
            state["pending"] = None
            return current()
        except Exception as e:  # noqa: BLE001
            return fail(e)

    def s_reset(_=None):
        try:
            st, _ = req(f"{API}/skins/active", "DELETE", authed())
            if st not in (200, 204):
                return {"ok": False, "error": explain(st)}
            return current()
        except Exception as e:  # noqa: BLE001
            return fail(e)

    def s_cape(arg=None):
        try:
            headers = authed()
            cid = (arg or {}).get("id")
            if cid:
                if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", str(cid)):
                    return {"ok": False, "error": "Неверный плащ."}
                st, _ = req(f"{API}/capes/active", "PUT", {**headers, "Content-Type": "application/json"},
                            json.dumps({"capeId": str(cid)}).encode())
            else:
                st, _ = req(f"{API}/capes/active", "DELETE", headers)
            if st not in (200, 204):
                return {"ok": False, "error": explain(st)}
            return current()
        except Exception as e:  # noqa: BLE001
            return fail(e)

    def s_discard(_=None):
        state["pending"] = None
        return {"ok": True}

    return {"skins:get": s_get, "skins:choose": s_choose, "skins:apply": s_apply, "skins:reset": s_reset,
            "skins:cape": s_cape, "skins:discard": s_discard}
