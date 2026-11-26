"""Общий контекст лаунчера (аналог объекта ctx в main.js).

Содержит настройки, профили, пути, события и мост к интерфейсу (диалоги, браузер).
Все модули core получают один экземпляр Ctx и не знают про Qt.
"""
from __future__ import annotations

import datetime
import os
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from typing import Any, Callable

from .. import __version__
from . import util

MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
SUBDIRS = ["mods", "resourcepacks", "shaderpacks", "saves"]
LOADERS = ["vanilla", "fabric", "forge", "neoforge", "quilt"]

PUBLIC_KEYS = [
    "nickname", "ram", "rootDir", "curseforgeKey", "javaPath", "accountMode", "msClientId",
    "updateUrl", "autoUpdate", "glass", "glassStrength", "lang", "discordRpc", "discordClientId",
    "bgDim", "autoBackup", "backupKeep", "closeToTray", "autoStart", "compatCheck", "tourDone", "autoUpdateMods", "achSound", "lastSeenVersion", "tone", "accent",
]


def default_user_data() -> str:
    env = os.environ.get("DLAUNCHER_DATA")
    if env:
        return env
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(base, "DLauncher")  # тот же путь, что у Electron-версии (productName)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "DLauncher")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "DLauncher")


def defaults() -> dict:
    return {
        "nickname": "Player",
        "ram": 4,
        "achSound": True,
        "lastSeenVersion": "",
        "tone": "dark",
        "accent": "",
        "rootDir": os.path.join(os.path.expanduser("~"), ".dlauncher"),
        "curseforgeKey": "",
        "javaPath": "",
        "accountMode": "offline",       # offline | microsoft
        "msClientId": "",
        "updateUrl": "",
        "autoUpdate": True,
        "glass": True,
        "glassStrength": 60,
        "lang": "ru",                   # ru | en
        "bgFile": "",
        "bgType": "",
        "bgName": "",
        "bgDim": 0,
        "discordRpc": False,
        "discordClientId": "",
        "autoBackup": True,
        "backupKeep": 5,
        "closeToTray": False,
        "autoStart": False,
        "compatCheck": True,
        "profiles": [],
        "currentProfile": None,
    }


def system_ram_gb() -> int:
    total = 0
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            total = ms.ullTotalPhys
        else:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:
        total = 0
    return max(2, int(total // 1024 ** 3)) if total else 8


class UiBridge:
    """Мост к интерфейсу. По умолчанию «без головы»; Qt-интерфейс подменяет методы.

    Методы диалогов вызываются из рабочих потоков, интерфейс обязан сам перейти в поток Qt.
    filters: список (название, [расширения без точки]).
    """

    def open_file(self, title: str = "", filters: list | None = None, multiple: bool = False):
        return None  # путь (str), список путей (multiple=True) или None

    def save_file(self, title: str = "", default_name: str = "", filters: list | None = None):
        return None  # путь или None

    def open_dir(self, title: str = ""):
        return None

    def open_path(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def set_clipboard_text(self, text: str) -> None:
        pass

    def set_clipboard_image(self, path: str) -> None:
        pass


class Ctx:
    def __init__(self, user_data: str | None = None):
        self.user_data = user_data or default_user_data()
        os.makedirs(self.user_data, exist_ok=True)
        self.app_version = __version__
        self.lock = threading.RLock()
        self.settings: dict = defaults()
        self.ui = UiBridge()
        self.launching = False
        self.is_packaged = bool(getattr(sys, "frozen", False))
        self._listeners: dict[str, list[Callable]] = {}
        self._manifest: dict | None = None
        self._manifest_lock = threading.Lock()
        # Сервисы подключает api.py (ctx.msauth, ctx.worlds, ctx.stats, ctx.presence, ctx.gamelog, ctx.servers …)
        self.load_settings()

    # ---------- события ----------
    def on(self, channel: str, fn: Callable[[Any], None]) -> None:
        """on('*', fn) получает (channel, payload) для всех событий; иначе fn(payload)."""
        self._listeners.setdefault(channel, []).append(fn)

    def send(self, channel: str, payload: Any = None) -> None:
        """Событие для интерфейса (game:status, game:progress, …). Безопасно из любого потока."""
        for fn in list(self._listeners.get(channel, [])):
            try:
                fn(payload)
            except Exception:
                pass
        for fn in list(self._listeners.get("*", [])):
            try:
                fn(channel, payload)
            except Exception:
                pass

    # ---------- настройки ----------
    @property
    def settings_file(self) -> str:
        return os.path.join(self.user_data, "settings.json")

    def load_settings(self) -> None:
        data = util.read_json(self.settings_file, None)
        s = defaults()
        if isinstance(data, dict):
            s.update(data)
        if not isinstance(s.get("profiles"), list):
            s["profiles"] = []
        s["profiles"] = [p for p in s["profiles"] if isinstance(p, dict) and p.get("id")]
        ids = [p["id"] for p in s["profiles"]]
        if s.get("currentProfile") not in ids:
            s["currentProfile"] = ids[0] if ids else None
        self.settings = s

    def save_settings(self) -> None:
        with self.lock:
            util.write_json(self.settings_file, self.settings)

    # kept for symmetry with the JS ctx.saveSettings
    saveSettings = save_settings

    @property
    def root(self) -> str:
        return self.settings["rootDir"]

    def public_settings(self) -> dict:
        s = {k: v for k, v in self.settings.items() if k not in ("profiles", "bgFile")}
        bp = self.bg_path()
        has = bool(bp and os.path.exists(bp))
        s["bgUrl"] = bp if has else ""
        s["bgType"] = self.settings.get("bgType") if has else ""
        s["systemRamGb"] = system_ram_gb()
        s["appVersion"] = self.app_version
        return s

    # ---------- свой фон ----------
    @property
    def bg_dir(self) -> str:
        return os.path.join(self.user_data, "backgrounds")

    def bg_path(self) -> str | None:
        import re
        f = self.settings.get("bgFile") or ""
        return os.path.join(self.bg_dir, f) if re.fullmatch(r"bg-\d+\.[a-z0-9]+", f) else None

    # ---------- профили ----------
    def find_profile(self, pid: str | None) -> dict | None:
        for p in self.settings["profiles"]:
            if p.get("id") == pid:
                return p
        return None

    def instance_dir(self, pid: str) -> str:
        return os.path.join(self.root, "instances", pid)

    def ensure_instance(self, pid: str) -> str:
        d = self.instance_dir(pid)
        for sub in SUBDIRS:
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        return d

    def count_mods(self, pid: str) -> int:
        try:
            return sum(1 for f in os.listdir(os.path.join(self.instance_dir(pid), "mods"))
                       if f.lower().endswith(".jar"))
        except OSError:
            return 0

    def get_manifest(self) -> dict:
        with self._manifest_lock:
            if self._manifest is None:
                self._manifest = util.get_json(MANIFEST_URL)
            return self._manifest

    def version_type_of(self, version: str) -> str:
        try:
            for v in self.get_manifest()["versions"]:
                if v["id"] == version:
                    return v["type"]
            return "release"
        except Exception:
            return "release"

    def create_profile(self, data: dict) -> dict:
        data = data or {}
        version = str(data.get("version") or "").strip()
        if not version:
            raise ValueError("Не выбрана версия Minecraft")
        loader = data.get("loader") if data.get("loader") in LOADERS else "vanilla"
        name = str(data.get("name") or "").strip()[:40] or f"Minecraft {version}"
        profile = {
            "id": f"{util.slug(name)}-{secrets.token_hex(3)}",
            "name": name,
            "version": version,
            "versionType": data.get("versionType") or self.version_type_of(version),
            "loader": loader,
            "loaderVersion": "" if loader == "vanilla" else str(data.get("loaderVersion") or ""),
            "pack": data.get("pack") or None,
            "ram": None,
            "jvmArgs": "",
            "width": None,
            "height": None,
            "fullscreen": False,
            "javaPath": "",
            "servers": [],
            "lastServer": None,
            "lastPlayed": None,
            "createdAt": int(datetime.datetime.now().timestamp() * 1000),
        }
        with self.lock:
            self.settings["profiles"].append(profile)
            self.settings["currentProfile"] = profile["id"]
            self.save_settings()
        self.ensure_instance(profile["id"])
        return profile

    # ---------- журнал неполадок (userData/launcher.log) ----------
    def diag(self, text: str) -> None:
        try:
            f = os.path.join(self.user_data, "launcher.log")
            old = ""
            try:
                if os.path.getsize(f) < 200000:
                    with open(f, "r", encoding="utf-8", errors="replace") as fh:
                        old = fh.read()
            except OSError:
                pass
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(f"{old}{stamp} v{self.app_version} {sys.platform} python {sys.version.split()[0]}: {text}\n")
        except Exception:
            pass

    def t(self, ru: str, en: str) -> str:
        """Короткий выбор строки для сообщений ядра по языку интерфейса."""
        return en if self.settings.get("lang") == "en" else ru


def rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
