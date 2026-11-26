"""Общие помощники: HTTP, скачивание, хеши, безопасные пути, пул потоков.

Только стандартная библиотека. Порт lib/util.js.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable

UA = "DLauncher/1.0 (personal project)"
TIMEOUT = 30

# Не показывать чёрное окно консоли при запуске java/tar на Windows
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


# Подмена адресов для тестов: util.set_rewrite(lambda url: url.replace('https://api.modrinth.com', 'http://127.0.0.1:1234'))
_rewrite = None


def set_rewrite(fn) -> None:
    global _rewrite
    _rewrite = fn


def _rw(url: str) -> str:
    return _rewrite(url) if _rewrite else url


class HttpError(Exception):
    def __init__(self, status: int, url: str, data: Any = None, reason: str = ""):
        super().__init__(f"{status} {reason} — {url}".replace("  ", " "))
        self.status = status
        self.url = url
        self.data = data


def _opener(url: str):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def request(url: str, method: str = "GET", headers: dict | None = None,
            body: bytes | None = None, timeout: float = TIMEOUT, retries: int = 2):
    """Возвращает (status, headers, bytes). Ошибочный статус -> HttpError."""
    url = _rw(url)
    h = {"User-Agent": UA}
    h.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with _opener(url).open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            data = b""
            try:
                data = e.read()
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504) and attempt < retries and method == "GET":
                time.sleep(0.6 * (attempt + 1))
                last = HttpError(e.code, url, data, e.reason or "")
                continue
            raise HttpError(e.code, url, data, e.reason or "")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            if attempt < retries and method == "GET":
                time.sleep(0.6 * (attempt + 1))
                continue
            raise
    raise last  # pragma: no cover


def get_json(url: str, headers: dict | None = None, timeout: float = TIMEOUT):
    _, _, data = request(url, headers=headers, timeout=timeout)
    return json.loads(data.decode("utf-8"))


def get_text(url: str, headers: dict | None = None, timeout: float = TIMEOUT) -> str:
    _, _, data = request(url, headers=headers, timeout=timeout)
    return data.decode("utf-8", "replace")


def get_bytes(url: str, headers: dict | None = None, timeout: float = TIMEOUT) -> bytes:
    return request(url, headers=headers, timeout=timeout)[2]


def post_json(url: str, body: Any, headers: dict | None = None, form: bool = False,
              allow_error: bool = False, timeout: float = TIMEOUT) -> dict:
    """POST. JSON по умолчанию или form (form=True). Возвращает {status, ok, data}."""
    h = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded" if form else "application/json",
    }
    h.update(headers or {})
    raw = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode("utf-8")
    try:
        status, _, data = request(url, "POST", h, raw, timeout, retries=0)
        ok = True
    except HttpError as e:
        if not allow_error:
            raise
        status, data, ok = e.status, e.data or b"", False
    parsed = None
    try:
        parsed = json.loads(data.decode("utf-8")) if data else None
    except Exception:
        parsed = None
    return {"status": status, "ok": ok, "data": parsed}


def download(url: str, dest: str, on_progress: Callable[[int], None] | None = None,
             headers: dict | None = None, timeout: float = 60) -> None:
    """Скачивание потоком во временный .part, затем переименование. on_progress(0..100)."""
    url = _rw(url)
    h = {"User-Agent": UA}
    h.update(headers or {})
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    tmp = dest + ".part"
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=h)
            with _opener(url).open(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                last = -1
                with open(tmp, "wb") as out:
                    while True:
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        got += len(chunk)
                        if on_progress and total:
                            p = got * 100 // total
                            if p != last:
                                last = p
                                on_progress(p)
            os.replace(tmp, dest)
            return
        except urllib.error.HTTPError as e:
            _rm(tmp)
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1 + attempt)
                last_err = e
                continue
            raise HttpError(e.code, url, None, e.reason or "") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            _rm(tmp)
            last_err = e
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            raise
    if last_err:
        raise last_err


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def run(cmd: str, args: list[str], timeout: float | None = None, cwd: str | None = None) -> str:
    """Запуск программы, возвращает stdout; при ненулевом коде — RuntimeError(stderr)."""
    p = subprocess.run([cmd, *args], capture_output=True, timeout=timeout, cwd=cwd,
                       creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or b"").decode("utf-8", "replace").strip()
                           or f"exit code {p.returncode}")
    return p.stdout.decode("utf-8", "replace")


def sha1_bytes(buf: bytes) -> str:
    return hashlib.sha1(buf).hexdigest()


def sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha512_file(path: str) -> str:
    h = hashlib.sha512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_join(base: str, rel: str) -> str:
    """Путь внутри base; запрещает выход за пределы папки (../ и абсолютные пути)."""
    root = os.path.abspath(base)
    full = os.path.abspath(os.path.join(root, str(rel).replace("\\", "/")))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError(f"Небезопасный путь: {rel}")
    return full


def pool(items: Iterable, limit: int, worker: Callable[[Any, int], Any]) -> list:
    """Выполняет worker(item, index) для всех items, не больше limit одновременно."""
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(limit, len(items)))) as ex:
        futs = [ex.submit(worker, it, i) for i, it in enumerate(items)]
        return [f.result() for f in futs]


def loaders_for(loader: str) -> list[str]:
    return ["quilt", "fabric"] if loader == "quilt" else [loader]


def slug(s: Any, limit: int = 24) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")[:limit]
    return out or "profile"


def write_json(path: str, data: Any, indent: int | None = 2) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default
