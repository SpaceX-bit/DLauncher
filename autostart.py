"""Автозапуск вместе с системой (Windows: реестр HKCU\\...\\Run, Linux: ~/.config/autostart)."""
from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "DLauncher"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
    return f'"{sys.executable}" "{main}" --hidden'


def desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart", "dlauncher.desktop")


def apply(ctx) -> bool:
    want = bool(ctx.settings.get("autoStart"))
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
                if want:
                    winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
                else:
                    try:
                        winreg.DeleteValue(k, NAME)
                    except FileNotFoundError:
                        pass
            return True
        if sys.platform.startswith("linux"):
            p = desktop_path()
            if want:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"[Desktop Entry]\nType=Application\nName=DLauncher\nExec={command()}\nX-GNOME-Autostart-enabled=true\n")
            elif os.path.exists(p):
                os.remove(p)
            return True
    except Exception as e:  # noqa: BLE001
        ctx.diag(f"autostart: {e}")
    return False


def on_settings_changed(ctx):
    apply(ctx)
