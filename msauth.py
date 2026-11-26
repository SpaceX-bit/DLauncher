"""Вход через Microsoft (device code flow): Microsoft -> Xbox Live -> XSTS -> Minecraft.

Порт lib/msauth.js. Несколько аккаунтов, accounts.json в папке данных.
Секреты (refresh-токен, токен Minecraft) на Windows защищены DPAPI (CryptProtectData), на других ОС
лежат открытым текстом в файле с правами 600. Блобы Electron safeStorage прочитать нельзя —
такие аккаунты считаются «вышедшими» (нужно войти заново).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import uuid

from . import util

AUTH = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
SCOPE = "XboxLive.signin offline_access"
MAX_ACCOUNTS = 10

XSTS_ERRORS = {
    2148916233: "У этого аккаунта Microsoft нет профиля Xbox. Создай его на xbox.com и повтори вход.",
    2148916235: "Xbox Live недоступен в стране этого аккаунта.",
    2148916236: "Аккаунту нужна проверка возраста на xbox.com.",
    2148916237: "Аккаунту нужна проверка возраста на xbox.com.",
    2148916238: "Это детский аккаунт: добавь его в семейную группу Microsoft.",
}

_HOST_OK = re.compile(r"(^|\.)(microsoft\.com|microsoftonline\.com|live\.com)$")


# ---------- DPAPI (Windows) ----------
def dpapi_available() -> bool:
    return sys.platform == "win32"


def _blob(data: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf, DATA_BLOB


def dpapi_encrypt(data: bytes) -> bytes:
    import ctypes
    blob_in, keep, DATA_BLOB = _blob(data)
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                                   ctypes.byref(blob_out)):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        del keep


def dpapi_decrypt(data: bytes) -> bytes:
    import ctypes
    blob_in, keep, DATA_BLOB = _blob(data)
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0,
                                                     ctypes.byref(blob_out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        del keep


def _wait(cancel: threading.Event, seconds: float) -> None:
    """Пауза между опросами; прерывается отменой. В тестах подменяется."""
    cancel.wait(seconds)


class MsAuth:
    def __init__(self, ctx, protect=None, unprotect=None):
        self.ctx = ctx
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._busy = False
        if protect is None and dpapi_available():
            protect, unprotect = dpapi_encrypt, dpapi_decrypt
        self._protect, self._unprotect = protect, unprotect

    # ---------- хранение ----------
    @property
    def file(self) -> str:
        return os.path.join(self.ctx.user_data, "accounts.json")

    @property
    def legacy_file(self) -> str:
        return os.path.join(self.ctx.user_data, "account.json")

    def _seal(self, acc: dict) -> dict:
        out = {"id": acc["profile"]["id"], "name": acc["profile"]["name"],
               "clientToken": acc.get("clientToken"), "mcExpires": acc.get("mcExpires")}
        secret = json.dumps({"refresh": acc.get("refresh"), "mcToken": acc.get("mcToken")})
        if self._protect:
            try:
                out["enc"] = base64.b64encode(self._protect(secret.encode("utf-8"))).decode("ascii")
                return out
            except Exception:  # noqa: BLE001
                pass
        out["plain"] = secret
        return out

    def _unseal(self, rec: dict) -> dict | None:
        try:
            if rec.get("enc"):
                if not self._unprotect:
                    return None
                secret = self._unprotect(base64.b64decode(rec["enc"])).decode("utf-8")
            else:
                secret = rec.get("plain")
            s = json.loads(secret)
            return {"profile": {"id": rec["id"], "name": rec["name"]}, "clientToken": rec.get("clientToken"),
                    "mcExpires": rec.get("mcExpires"), "refresh": s.get("refresh"), "mcToken": s.get("mcToken")}
        except Exception:  # noqa: BLE001
            return None

    def read_store(self) -> dict:
        with self._lock:
            raw = util.read_json(self.file, None)
            if isinstance(raw, dict):
                accounts = [a for a in (raw.get("accounts") or [])
                            if isinstance(a, dict) and isinstance(a.get("id"), str) and isinstance(a.get("name"), str)]
                ids = [a["id"] for a in accounts]
                active = raw.get("active") if raw.get("active") in ids else (ids[0] if ids else "")
                return {"active": active, "accounts": accounts}
            old = util.read_json(self.legacy_file, None)
            if isinstance(old, dict) and isinstance(old.get("profile"), dict) and old["profile"].get("id"):
                rec = {"id": old["profile"]["id"], "name": old["profile"].get("name", ""),
                       "clientToken": old.get("clientToken"), "mcExpires": old.get("mcExpires")}
                if old.get("enc"):
                    rec["enc"] = old["enc"]
                else:
                    rec["plain"] = old.get("plain")
                store = {"active": rec["id"], "accounts": [rec]}
                self.write_store(store)
                try:
                    os.remove(self.legacy_file)
                except OSError:
                    pass
                return store
            return {"active": "", "accounts": []}

    def write_store(self, store: dict) -> None:
        with self._lock:
            os.makedirs(os.path.dirname(self.file), exist_ok=True)
            tmp = self.file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(store, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.file)

    @staticmethod
    def listing(store: dict) -> dict:
        return {"active": store["active"], "accounts": [{"id": a["id"], "name": a["name"]} for a in store["accounts"]]}

    def save_account(self, acc: dict, make_active: bool) -> dict:
        with self._lock:
            store = self.read_store()
            rec = self._seal(acc)
            for i, a in enumerate(store["accounts"]):
                if a["id"] == rec["id"]:
                    store["accounts"][i] = rec
                    break
            else:
                store["accounts"].append(rec)
            if make_active or not store["active"]:
                store["active"] = rec["id"]
            self.write_store(store)
            return store

    def load(self, acc_id: str | None = None) -> dict | None:
        store = self.read_store()
        want = acc_id or store["active"]
        for a in store["accounts"]:
            if a["id"] == want:
                return self._unseal(a)
        return None

    def _client_id(self) -> str:
        return str(self.ctx.settings.get("msClientId") or "").strip()

    # ---------- цепочка Xbox -> Minecraft ----------
    def minecraft_from_ms_token(self, ms_token: str) -> dict:
        xbl = util.post_json("https://user.auth.xboxlive.com/user/authenticate", {
            "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": f"d={ms_token}"},
            "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"})["data"]
        xsts = util.post_json("https://xsts.auth.xboxlive.com/xsts/authorize", {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl["Token"]]},
            "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}, allow_error=True)
        if not xsts["ok"]:
            code = (xsts["data"] or {}).get("XErr")
            raise RuntimeError(XSTS_ERRORS.get(code) or
                               f"Xbox отклонил вход ({xsts['status']}{', ' + str(code) if code else ''})")
        uhs = xsts["data"]["DisplayClaims"]["xui"][0]["uhs"]
        mc = util.post_json("https://api.minecraftservices.com/authentication/login_with_xbox", {
            "identityToken": f"XBL3.0 x={uhs};{xsts['data']['Token']}"}, allow_error=True)
        if not mc["ok"]:
            raise RuntimeError(
                "Minecraft отклонил вход (403). Приложение Azure с этим Client ID, скорее всего, не одобрено "
                "Mojang для Minecraft API — см. README." if mc["status"] == 403
                else f"Minecraft отклонил вход ({mc['status']})")
        try:
            profile = util.get_json("https://api.minecraftservices.com/minecraft/profile",
                                    {"Authorization": f"Bearer {mc['data']['access_token']}"})
        except util.HttpError as e:
            if e.status == 404:
                raise RuntimeError("На этом аккаунте нет Minecraft: Java Edition.")
            raise
        return {
            "mcToken": mc["data"]["access_token"],
            "mcExpires": int(time.time() * 1000) + int(float(mc["data"].get("expires_in") or 86400) * 1000),
            "profile": {"id": profile["id"], "name": profile["name"]},
        }

    # ---------- вход ----------
    def _open_external(self, url: str) -> None:
        try:
            u = urllib.parse.urlparse(url)
            if u.scheme == "https" and _HOST_OK.search(u.hostname or ""):
                self.ctx.ui.open_url(url)
        except Exception:  # noqa: BLE001
            pass

    def login(self, _=None) -> dict:
        if self._busy:
            return {"ok": False, "error": "Вход уже выполняется"}
        cid = self._client_id()
        if not cid:
            return {"ok": False, "error": "Укажи Client ID приложения Azure в Настройках (см. README)."}
        self._busy = True
        self._cancel.clear()
        try:
            dc = util.post_json(f"{AUTH}/devicecode", {"client_id": cid, "scope": SCOPE}, form=True)["data"]
            self.ctx.send("ms:code", {"code": dc["user_code"], "url": dc["verification_uri"],
                                      "expires": dc.get("expires_in")})
            self._open_external(dc["verification_uri"])
            interval = float(dc.get("interval") or 5)
            deadline = time.time() + float(dc.get("expires_in") or 900)
            tok = None
            while tok is None:
                if self._cancel.is_set():
                    return {"ok": False, "error": "Вход отменён"}
                if time.time() > deadline:
                    return {"ok": False, "error": "Время на ввод кода истекло"}
                _wait(self._cancel, interval)
                if self._cancel.is_set():
                    return {"ok": False, "error": "Вход отменён"}
                r = util.post_json(f"{AUTH}/token", {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": cid, "device_code": dc["device_code"]}, form=True, allow_error=True)
                if r["ok"]:
                    tok = r["data"]
                    break
                e = (r["data"] or {}).get("error")
                if e == "authorization_pending":
                    continue
                if e == "slow_down":
                    interval += 5
                    continue
                if e == "authorization_declined":
                    return {"ok": False, "error": "Вход отклонён"}
                if e == "expired_token":
                    return {"ok": False, "error": "Время на ввод кода истекло"}
                return {"ok": False, "error": (r["data"] or {}).get("error_description")
                        or f"Ошибка входа ({e or r['status']})"}
            mc = self.minecraft_from_ms_token(tok["access_token"])
            before = self.read_store()
            known = any(a["id"] == mc["profile"]["id"] for a in before["accounts"])
            if not known and len(before["accounts"]) >= MAX_ACCOUNTS:
                return {"ok": False, "error": f"Можно добавить не больше {MAX_ACCOUNTS} аккаунтов"}
            prev = self.load(mc["profile"]["id"])
            client_token = (prev or {}).get("clientToken") or uuid.uuid4().hex
            store = self.save_account({**mc, "refresh": tok.get("refresh_token"), "clientToken": client_token},
                                      make_active=True)
            return {"ok": True, "profile": mc["profile"], **self.listing(store)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            self._busy = False

    def cancel(self, _=None) -> dict:
        self._cancel.set()
        return {"ok": True}

    def accounts(self, _=None) -> dict:
        return self.listing(self.read_store())

    def select(self, acc_id=None) -> dict:
        with self._lock:
            store = self.read_store()
            if not isinstance(acc_id, str) or not any(a["id"] == acc_id for a in store["accounts"]):
                return {"ok": False, "error": "Аккаунт не найден"}
            store["active"] = acc_id
            self.write_store(store)
            return {"ok": True, **self.listing(store)}

    def remove(self, acc_id=None) -> dict:
        with self._lock:
            store = self.read_store()
            if not isinstance(acc_id, str) or not any(a["id"] == acc_id for a in store["accounts"]):
                return {"ok": False, "error": "Аккаунт не найден"}
            store["accounts"] = [a for a in store["accounts"] if a["id"] != acc_id]
            if store["active"] == acc_id:
                store["active"] = store["accounts"][0]["id"] if store["accounts"] else ""
            self.write_store(store)
            return {"ok": True, **self.listing(store)}

    def status(self, _=None) -> dict:
        acc = self.load()
        return ({"loggedIn": True, "name": acc["profile"]["name"], "uuid": acc["profile"]["id"]}
                if acc else {"loggedIn": False})

    def logout(self, _=None) -> dict:
        with self._lock:
            store = self.read_store()
            store["accounts"] = [a for a in store["accounts"] if a["id"] != store["active"]]
            store["active"] = store["accounts"][0]["id"] if store["accounts"] else ""
            self.write_store(store)
            return {"ok": True, **self.listing(store)}

    # ---------- данные для запуска игры ----------
    def get_launch_auth(self) -> dict:
        """Активный аккаунт; токен обновляется при необходимости. Бросает RuntimeError с понятным текстом."""
        acc = self.load()
        if not acc:
            raise RuntimeError("Войди через Microsoft в Настройках или переключись на офлайн-режим.")
        mc_token, mc_expires, profile, refresh = acc["mcToken"], acc["mcExpires"], acc["profile"], acc["refresh"]
        if not mc_token or not mc_expires or mc_expires < time.time() * 1000 + 5 * 60 * 1000:
            cid = self._client_id()
            if not cid:
                raise RuntimeError("Не указан Client ID приложения Azure (Настройки).")
            r = util.post_json(f"{AUTH}/token", {"grant_type": "refresh_token", "client_id": cid,
                                                  "refresh_token": refresh, "scope": SCOPE},
                               form=True, allow_error=True)
            if not r["ok"]:
                raise RuntimeError("Сессия Microsoft истекла — войди заново в Настройках.")
            mc = self.minecraft_from_ms_token(r["data"]["access_token"])
            mc_token, mc_expires, profile = mc["mcToken"], mc["mcExpires"], mc["profile"]
            self.save_account({**mc, "refresh": r["data"].get("refresh_token") or refresh,
                               "clientToken": acc.get("clientToken")}, make_active=False)
        return {
            "access_token": mc_token,
            "client_token": acc.get("clientToken"),
            "uuid": profile["id"],
            "name": profile["name"],
            "user_properties": "{}",
            "user_type": "msa",
            "meta": {"type": "msa", "demo": False},
        }

    get_profile_token = get_launch_auth  # для модуля скинов


def setup(ctx) -> None:
    ctx.msauth = MsAuth(ctx)


def handlers(ctx):
    m = ctx.msauth
    return {
        "ms:login": m.login, "ms:cancel": m.cancel, "ms:accounts": m.accounts, "ms:select": m.select,
        "ms:remove": m.remove, "ms:status": m.status, "ms:logout": m.logout,
    }
