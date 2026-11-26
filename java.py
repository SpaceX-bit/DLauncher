"""Java: нужная версия для Minecraft и автоматическая загрузка (Eclipse Temurin / Adoptium).

Порт requiredJava / findJavaBin / ensureJava из main.js. Распаковка — стандартные zipfile/tarfile.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tarfile
import zipfile

from . import util


def required_java(ctx, version: str) -> int:
    """Мажорная версия Java для версии игры: 8, 17, 21 или выше. При сбоях — 17."""
    try:
        local = util.read_json(os.path.join(ctx.root, "versions", version, version + ".json"), None) \
            if version else None
        meta = local if isinstance(local, dict) else None
        if meta is None:
            entry = next((v for v in ctx.get_manifest()["versions"] if v["id"] == version), None)
            if not entry:
                return 17
            meta = util.get_json(entry["url"])
        major = int(((meta.get("javaVersion") or {}).get("majorVersion")) or 8)
        if major <= 8:
            return 8
        if major <= 17:
            return 17  # 16 у Adoptium уже нет, 17 подходит
        if major <= 21:
            return 21
        return major
    except Exception:  # noqa: BLE001
        return 17


def _exe() -> str:
    return "java.exe" if sys.platform == "win32" else "java"


def find_java_bin(directory: str, depth: int = 0) -> str | None:
    """Ищет .../bin/java(.exe) внутри распакованного JRE."""
    if depth > 6 or not os.path.isdir(directory):
        return None
    exe = _exe()
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return None
    if os.path.basename(directory) == "bin" and any(e.is_file() and e.name == exe for e in entries):
        return os.path.join(directory, exe)
    for e in entries:
        if e.is_dir(follow_symlinks=False):
            found = find_java_bin(e.path, depth + 1)
            if found:
                return found
    return None


def _adoptium_target() -> tuple[str, str]:
    os_name = {"win32": "windows", "linux": "linux", "darwin": "mac"}.get(sys.platform)
    m = (platform.machine() or "").lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "aarch64", "aarch64": "aarch64",
            "x86": "x86", "i386": "x86", "i686": "x86"}.get(m)
    if not os_name or not arch:
        raise RuntimeError("Эта система не поддерживается для автоматической загрузки Java")
    return os_name, arch


def extract_archive(archive: str, dest: str) -> None:
    """zip или tar.gz -> папка; пути проверяются (без выхода за пределы), права на запуск сохраняются."""
    os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = util.safe_join(dest, info.filename)
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                mode = (info.external_attr >> 16) & 0o777
                if mode and sys.platform != "win32":
                    os.chmod(target, mode | 0o600)
        return
    with tarfile.open(archive, "r:*") as tf:
        for m in tf.getmembers():
            target = util.safe_join(dest, m.name)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = tf.extractfile(m)
                with open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                if sys.platform != "win32":
                    os.chmod(target, (m.mode & 0o777) | 0o600)
            elif m.issym() or m.islnk():
                if os.path.isabs(m.linkname) or ".." in m.linkname.replace("\\", "/").split("/"):
                    continue  # безопасность: такие ссылки не создаём
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if m.issym():
                        os.symlink(m.linkname, target)
                except OSError:
                    pass


def ensure_java(ctx, major: int) -> str:
    """Путь к java из <root>/runtime/java<major>; при отсутствии скачивает JRE с Adoptium."""
    runtime = os.path.join(ctx.root, "runtime")
    d = os.path.join(runtime, f"java{major}")
    existing = find_java_bin(d)
    if existing:
        return existing

    os_name, arch = _adoptium_target()
    url = f"https://api.adoptium.net/v3/binary/latest/{major}/ga/{os_name}/{arch}/jre/hotspot/normal/eclipse"
    archive = os.path.join(runtime, f"java{major}." + ("zip" if os_name == "windows" else "tar.gz"))

    ctx.send("game:status", f"Скачивание Java {major}...")
    util.download(url, archive, lambda p: ctx.send("game:progress", {"task": p, "total": 100, "type": "java",
                                                                    "label": f"Java {major}"}), timeout=120)
    ctx.send("game:status", f"Распаковка Java {major}...")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    try:
        extract_archive(archive, d)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError("Не удалось распаковать Java: " + str(e)) from None
    finally:
        try:
            os.remove(archive)
        except OSError:
            pass
    bin_ = find_java_bin(d)
    if not bin_:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError("Java скачана, но java не найдена в архиве")
    if sys.platform != "win32":
        os.chmod(bin_, 0o755)
    return bin_
