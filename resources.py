"""Пути к ресурсам (картинки, иконка) — и из исходников, и из PyInstaller-сборки."""
import os
import sys


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset(name: str) -> str:
    return os.path.join(base_dir(), "assets", name)
