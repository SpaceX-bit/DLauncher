"""Автообновление лаунчера через релизы GitHub. Скачивает установщик (…Setup….exe) и запускает его.

Адрес: settings.updateUrl или update-config.json ("repo": "ник/репозиторий"). Работает у собранной программы.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading

from . import util
from ..resources import base_dir

CHECK_EVERY_S = 3 * 60 * 60


def normalize_repo(v) -> str:
    t = str(v or "").strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", t):
        return f"https://github.com/{t}"
    return t if re.match(r"^https?://github\.com/[^/]+/[^/#?]+", t, re.I) else ""


def bundled_url(file: str | None = None) -> str:
    try:
        with open(file or os.path.join(base_dir(), "update-config.json"), "r", encoding="utf-8") as f:
            return normalize_repo(json.load(f).get("repo"))
    except (OSError, ValueError, AttributeError):
        return ""


def version_tuple(v) -> tuple:
    nums = re.findall(r"\d+", str(v or "").split("-")[0])
    return tuple(int(n) for n in nums[:4]) + (0,) * (3 - len(nums[:4]))


def is_newer(remote, local) -> bool:
    return version_tuple(remote) > version_tuple(local)


def pick_asset(release: dict):
    for a in release.get("assets") or []:
        n = str(a.get("name") or "")
        if n.lower().endswith(".exe") and "setup" in n.lower():
            return a
    return None


def handlers_and_service(ctx):
    st = {"ready": None, "busy": False}
    lock = threading.Lock()

    def status(s):
        ctx.send("update:status", s)

    def problem():
        if not ctx.is_packaged:
            return "Автообновление работает только в собранной программе (.exe), не при запуске из исходников."
        if sys.platform != "win32":
            return "Автообновление доступно только в Windows."
        if not (str(ctx.settings.get("updateUrl") or "").strip() and normalize_repo(ctx.settings.get("updateUrl"))) and not bundled_url():
            return "Адрес обновлений не задан: укажи его в Настройках (или впиши репозиторий в update-config.json перед сборкой)."
        return None

    def repo_api():
        url = normalize_repo(ctx.settings.get("updateUrl")) or bundled_url()
        m = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+)", url, re.I)
        return f"https://api.github.com/repos/{m.group(1)}/{re.sub(r'[.]git$', '', m.group(2), flags=re.I)}/releases/latest"

    def fetch(dl: dict) -> None:
        """Скачивает установщик найденной версии (прогресс — событиями update:status)."""
        dest_dir = os.path.join(ctx.user_data, "updates")
        os.makedirs(dest_dir, exist_ok=True)
        name = re.sub(r"[^\w.\-]", "_", dl["asset"]["name"])
        dest = os.path.join(dest_dir, name)
        last = {"p": -1}

        def prog(pc):
            if pc != last["p"]:
                last["p"] = pc
                status({"state": "downloading", "percent": pc})
        if not os.path.exists(dest):
            util.download(dl["asset"]["browser_download_url"], dest, prog)
        st["ready"] = dest
        status({"state": "ready", "version": dl["version"]})

    def check(arg=None):
        """Ищет новую версию. {"download": True} — сразу скачать; иначе только сообщить «доступно» и ждать update:download."""
        if st["ready"]:
            status({"state": "ready", "version": (st.get("found") or {}).get("version", "")})
            return {"ok": True}
        p = problem()
        if p:
            return {"ok": False, "error": p}
        with lock:
            if st["busy"]:
                return {"ok": True}
            st["busy"] = True
        try:
            status({"state": "checking"})
            rel = util.get_json(repo_api(), headers={"Accept": "application/vnd.github+json"})
            ver = str(rel.get("tag_name") or "").lstrip("vV")
            asset = pick_asset(rel)
            if not ver or not is_newer(ver, ctx.app_version) or not asset:
                status({"state": "none"})
                return {"ok": True}
            st["found"] = {"version": ver, "asset": asset}
            want = isinstance(arg, dict) and bool(arg.get("download"))
            status({"state": "available", "version": ver, "notes": str(rel.get("body") or "")[:2000], "ask": not want})
            if want:
                fetch(st["found"])
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            status({"state": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}
        finally:
            st["busy"] = False

    def download(_=None):
        """Кнопка «Скачать» в окне обновления: скачать найденную версию."""
        if st["ready"]:
            status({"state": "ready", "version": (st.get("found") or {}).get("version", "")})
            return {"ok": True}
        if not st.get("found"):
            return {"ok": False, "error": "Сначала проверь обновления"}
        with lock:
            if st["busy"]:
                return {"ok": True}
            st["busy"] = True
        try:
            fetch(st["found"])
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            status({"state": "error", "message": str(e)})
            return {"ok": False, "error": str(e)}
        finally:
            st["busy"] = False

    def install(_=None):
        if not st["ready"] or not os.path.exists(st["ready"]):
            return {"ok": False}
        if ctx.launching:
            return {"ok": False, "error": "Сначала закрой игру: лаунчер перезапустится для обновления."}
        try:
            subprocess.Popen([st["ready"], "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                             creationflags=util.NO_WINDOW and 0x00000008)  # DETACHED_PROCESS
        except OSError as e:
            return {"ok": False, "error": str(e)}
        ctx.send("app:quit", None)
        return {"ok": True}

    def info(_=None):
        return {"defaultUrl": bundled_url()}

    return {"update:check": check, "update:download": download, "update:install": install, "update:info": info}, check


_state = {"stop": None}


def setup(ctx):
    h, check = handlers_and_service(ctx)
    ctx._update_handlers = h
    stop = threading.Event()
    _state["stop"] = stop

    def loop():
        if stop.wait(5):
            return
        while not stop.is_set():
            try:
                if ctx.settings.get("autoUpdate", True) and not ctx.launching and ctx.is_packaged:
                    check()
            except Exception as e:  # noqa: BLE001
                ctx.diag(f"auto update: {e}")
            if stop.wait(CHECK_EVERY_S):
                return
    threading.Thread(target=loop, daemon=True, name="dl-updater").start()


def shutdown(ctx):
    if _state["stop"]:
        _state["stop"].set()


def handlers(ctx):
    return ctx._update_handlers
