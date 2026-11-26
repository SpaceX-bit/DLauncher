# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/DLauncher.spec --noconfirm   (из корня проекта)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))


def all_modules(pkg: str) -> list[str]:
    """Все модули пакета по файлам (страницы и ядро подключаются по имени через importlib — PyInstaller сам их не видит)."""
    out = []
    base = os.path.join(ROOT, pkg)
    for dirpath, _dirs, files in os.walk(base):
        rel = os.path.relpath(dirpath, ROOT).replace(os.sep, ".")
        if "__pycache__" in rel:
            continue
        if "__init__.py" in files:
            out.append(rel)
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                out.append(rel + "." + f[:-3])
    return out


hidden = all_modules("dlauncher")
print("PyInstaller: hiddenimports =", len(hidden))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "assets"), "assets"),
        (os.path.join(ROOT, "dlauncher", "ui", "en.json"), os.path.join("dlauncher", "ui")),
        (os.path.join(ROOT, "update-config.json"), "."),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DLauncher",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DLauncher")
