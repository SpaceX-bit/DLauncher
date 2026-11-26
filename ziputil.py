"""Чтение ZIP (.mrpack, сборки CurseForge, jar): порт lib/zip.js на стандартном zipfile."""
from __future__ import annotations

import io
import os
import shutil
import time
import zipfile
from typing import Union

from . import util


class Entry:
    __slots__ = ("name", "info")

    def __init__(self, name: str, info: zipfile.ZipInfo):
        self.name = name
        self.info = info

    @property
    def size(self) -> int:
        return self.info.file_size

    def __repr__(self) -> str:  # pragma: no cover
        return f"Entry({self.name!r})"


class ZipReader:
    """file — путь к архиву или bytes (например, вложенный jar внутри мода)."""

    def __init__(self, file: Union[str, bytes, bytearray, os.PathLike]):
        src = io.BytesIO(bytes(file)) if isinstance(file, (bytes, bytearray)) else str(file)
        try:
            self._zip = zipfile.ZipFile(src)
        except zipfile.BadZipFile:
            raise ValueError("Это не ZIP-архив") from None
        self.entries: list[Entry] = [Entry(i.filename.replace("\\", "/"), i) for i in self._zip.infolist()]

    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def find(self, name: str) -> Entry | None:
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def read(self, entry: Union[Entry, str]) -> bytes:
        e = self.find(entry) if isinstance(entry, str) else entry
        if e is None:
            raise KeyError(entry)
        if e.info.flag_bits & 1:
            raise ValueError("Архив зашифрован")
        try:
            return self._zip.read(e.info)
        except NotImplementedError:
            raise ValueError("Неподдерживаемый способ сжатия в ZIP") from None
        except zipfile.BadZipFile:
            raise ValueError("Повреждённый ZIP") from None

    def read_text(self, name: str) -> str | None:
        e = self.find(name)
        if e is None:
            return None
        return self.read(e).decode("utf-8", "replace").lstrip("﻿")

    def _extract_to(self, e: Entry, dest: str) -> None:
        """Потоковая распаковка одного файла (большие файлы не грузятся в память целиком)."""
        if e.info.flag_bits & 1:
            raise ValueError("Архив зашифрован")
        try:
            with self._zip.open(e.info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
        except NotImplementedError:
            raise ValueError("Неподдерживаемый способ сжатия в ZIP") from None
        except zipfile.BadZipFile:
            raise ValueError("Повреждённый ZIP") from None

    def extract_prefix(self, prefix: str, dest_dir: str) -> int:
        """Распаковывает всё из папки prefix (например "overrides/") в dest_dir. Выход за папку -> ValueError."""
        n = 0
        for e in self.entries:
            if not e.name.startswith(prefix) or e.name.endswith("/"):
                continue
            rel = e.name[len(prefix):]
            if not rel:
                continue
            dest = util.safe_join(dest_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            self._extract_to(e, dest)
            n += 1
        return n

    def close(self) -> None:
        self._zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def read_zip(file) -> ZipReader:
    return ZipReader(file)


# ---------- запись ----------
def walk_files(root: str, filt=None, rel: str = ""):
    """Обход папки без перехода по символическим ссылкам. Генерирует (rel, abs), порядок по имени.

    filt(rel, is_dir) -> False пропускает файл или папку."""
    try:
        with os.scandir(os.path.join(root, rel) if rel else root) as it:
            items = sorted(it, key=lambda d: d.name.lower())
    except OSError:
        return
    for d in items:
        if d.is_symlink():
            continue
        r = f"{rel}/{d.name}" if rel else d.name
        is_dir = d.is_dir(follow_symlinks=False)
        if filt is not None and not filt(r, is_dir):
            continue
        if is_dir:
            yield from walk_files(root, filt, r)
        elif d.is_file(follow_symlinks=False):
            yield r, os.path.join(root, r)


class ZipWriter:
    """Запись ZIP с проверкой имён (без «..», без повторов). При ошибке abort() удаляет недописанный файл."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._zip = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        self._names: set[str] = set()

    def _name(self, name: str) -> str:
        n = str(name).replace("\\", "/").lstrip("/")
        if not n or ".." in n.split("/"):
            raise ValueError(f"Недопустимое имя в архиве: {name}")
        if n in self._names:
            raise ValueError(f"Повторяющееся имя в архиве: {n}")
        self._names.add(n)
        return n

    def add_bytes(self, name: str, data, mtime: float | None = None) -> None:
        n = self._name(name)
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        info = zipfile.ZipInfo(n, _dos_time(mtime))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        self._zip.writestr(info, raw)

    def add_file(self, name: str, src: str) -> None:
        n = self._name(name)
        self._zip.write(src, n, compress_type=zipfile.ZIP_DEFLATED)

    def finish(self) -> None:
        self._zip.close()

    def abort(self) -> None:
        try:
            self._zip.close()
        except Exception:
            pass
        try:
            os.remove(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et:
            self.abort()
        else:
            self.finish()


def _dos_time(mtime: float | None):
    t = time.localtime(mtime if mtime else time.time())
    return (max(t.tm_year, 1980), t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
