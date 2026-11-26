"""Откат изменений в профиле: перед заменой файла (обновление мода, обновление сборки) старая копия откладывается
в <профиль>/.rollback, а в журнал пишется, что сделано. «Откатить» возвращает всё как было. Хранится один последний набор."""
from __future__ import annotations

import os
import shutil
import threading

from . import util

_lock = threading.RLock()


def _base(ctx, pid: str) -> str:
    return os.path.join(ctx.instance_dir(pid), ".rollback")


def _log_path(ctx, pid: str) -> str:
    return os.path.join(_base(ctx, pid), "log.json")


def _load(ctx, pid: str) -> list[dict]:
    data = util.read_json(_log_path(ctx, pid), [])
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("rel"), str)] if isinstance(data, list) else []


def _save(ctx, pid: str, log: list[dict]) -> None:
    os.makedirs(_base(ctx, pid), exist_ok=True)
    util.write_json(_log_path(ctx, pid), log, indent=None)


def reset(ctx, pid: str) -> None:
    """Начать новый набор: старые отложенные файлы удаляются."""
    with _lock:
        shutil.rmtree(_base(ctx, pid), ignore_errors=True)


def stash(ctx, pid: str, rel: str, move: bool = True) -> dict | None:
    """Откладывает файл rel (если он есть). move=False — копия (файл останется на месте)."""
    inst = ctx.instance_dir(pid)
    src = util.safe_join(inst, rel)
    if not os.path.isfile(src):
        return None
    with _lock:
        log = _load(ctx, pid)
        name = f"{len(log):04d}_{os.path.basename(src)}"
        dst = os.path.join(_base(ctx, pid), "files", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        (shutil.move if move else shutil.copy2)(src, dst)
        entry = {"rel": rel.replace("\\", "/"), "stash": name}
        log.append(entry)
        _save(ctx, pid, log)
        return entry


def added(ctx, pid: str, rel: str) -> None:
    """Запоминает, что в профиль добавлен новый файл (при откате он будет удалён)."""
    with _lock:
        log = _load(ctx, pid)
        log.append({"rel": rel.replace("\\", "/"), "stash": None})
        _save(ctx, pid, log)


def undo_last(ctx, pid: str, entry: dict | None) -> None:
    """Возвращает один отложенный файл на место (если замена не удалась)."""
    if not entry:
        return
    with _lock:
        log = [e for e in _load(ctx, pid) if e != entry]
        _put_back(ctx, pid, entry)
        _save(ctx, pid, log)


def _put_back(ctx, pid: str, e: dict) -> None:
    inst = ctx.instance_dir(pid)
    dst = util.safe_join(inst, e["rel"])
    if e.get("stash"):
        src = os.path.join(_base(ctx, pid), "files", os.path.basename(str(e["stash"])))
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
    elif os.path.isfile(dst):
        os.remove(dst)


def count(ctx, pid: str) -> int:
    with _lock:
        return len(_load(ctx, pid))


def names(ctx, pid: str) -> list[str]:
    with _lock:
        return [os.path.basename(e["rel"]) for e in _load(ctx, pid) if e.get("stash")]


def restore(ctx, pid: str) -> dict:
    """Откатывает весь набор. Возвращает {ok, restored, removed}."""
    with _lock:
        log = _load(ctx, pid)
        if not log:
            return {"ok": False, "error": "Откатывать нечего"}
        restored = removed = 0
        for e in reversed(log):
            try:
                _put_back(ctx, pid, e)
                if e.get("stash"):
                    restored += 1
                else:
                    removed += 1
            except (OSError, ValueError):
                continue
        shutil.rmtree(_base(ctx, pid), ignore_errors=True)
        return {"ok": True, "restored": restored, "removed": removed}
