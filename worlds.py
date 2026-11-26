"""Миры профиля и резервные копии (zip): список, копия, восстановление, автокопия. Порт lib/worlds.js."""
from __future__ import annotations

import datetime
import os
import re
import shutil
import threading
import zipfile

from . import util
from .nbt import read_nbt_file

RESTORE_LIMIT = int(1.5 * 1024 ** 3)
_BACKUP_RE = re.compile(r"^.+__\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.zip$")


def stamp(d: datetime.datetime | None = None) -> str:
    return (d or datetime.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")


def safe_name(s) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(s))[:80] or "world"


def is_base(f) -> bool:
    return isinstance(f, str) and bool(f) and os.path.basename(f) == f and f not in (".", "..")


def read_level(world_dir: str) -> dict:
    try:
        data = (read_nbt_file(os.path.join(world_dir, "level.dat")).get("Data")) or {}
        ver = (data.get("Version") or {}).get("Name") if isinstance(data.get("Version"), dict) else ""
        name = data.get("LevelName")
        return {
            "name": name.strip()[:60] if isinstance(name, str) and name.strip() else "",
            "lastPlayed": int(data.get("LastPlayed") or 0),
            "version": (ver if isinstance(ver, str) else "")[:30],
        }
    except Exception:  # noqa: BLE001
        return {"name": "", "lastPlayed": 0, "version": ""}


def dir_size(path: str) -> int:
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


class Worlds:
    def __init__(self, ctx):
        self.ctx = ctx
        self.working = False
        self._lock = threading.Lock()

    def is_busy(self) -> bool:
        return bool(self.ctx.launching)

    def progress(self, text: str) -> None:
        self.ctx.send("worlds:progress", {"text": text})

    def profile_of(self, pid):
        return self.ctx.find_profile(pid or self.ctx.settings.get("currentProfile"))

    def saves_dir(self, p):
        return os.path.join(self.ctx.instance_dir(p["id"]), "saves")

    def backups_dir(self, p):
        return os.path.join(self.ctx.instance_dir(p["id"]), "backups")

    def backup_files(self, p) -> list[dict]:
        try:
            names = os.listdir(self.backups_dir(p))
        except OSError:
            return []
        out = []
        for f in names:
            if not _BACKUP_RE.match(f):
                continue
            st = os.stat(os.path.join(self.backups_dir(p), f))
            out.append({"file": f, "world": f[:f.rindex("__")], "size": st.st_size, "time": st.st_mtime * 1000})
        out.sort(key=lambda b: -b["time"])
        return out

    def list(self, profile_id=None):
        p = self.profile_of(profile_id)
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        backups = self.backup_files(p)
        worlds = []
        try:
            dirs = [d for d in os.listdir(self.saves_dir(p)) if os.path.isdir(os.path.join(self.saves_dir(p), d))]
        except OSError:
            dirs = []
        for name in dirs:
            d = os.path.join(self.saves_dir(p), name)
            lvl = os.path.join(d, "level.dat")
            if not os.path.exists(lvl):
                continue
            lv = read_level(d)
            try:
                mtime = os.stat(lvl).st_mtime * 1000
            except OSError:
                mtime = 0
            mine = [b for b in backups if b["world"] == safe_name(name)]
            worlds.append({"folder": name, "name": lv["name"] or name, "version": lv["version"],
                           "lastPlayed": lv["lastPlayed"] or mtime, "size": dir_size(d), "backups": len(mine),
                           "lastBackup": mine[0]["time"] if mine else 0})
        worlds.sort(key=lambda w: -w["lastPlayed"])
        return {"ok": True, "worlds": worlds, "backups": backups, "profile": {"id": p["id"], "name": p["name"]},
                "running": self.is_busy()}

    def make_backup(self, p, folder: str, keep: int = 0) -> dict:
        if not is_base(folder):
            raise ValueError("Неверное имя мира")
        d = os.path.join(self.saves_dir(p), folder)
        if not os.path.exists(os.path.join(d, "level.dat")):
            raise ValueError("Мир не найден")
        os.makedirs(self.backups_dir(p), exist_ok=True)
        dest = os.path.join(self.backups_dir(p), f"{safe_name(folder)}__{stamp()}.zip")
        tmp = dest + ".part"
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for root, _dirs, files in os.walk(d):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, d).replace(os.sep, "/")
                        if rel == "session.lock":
                            continue
                        try:
                            z.write(full, f"{folder}/{rel}")
                        except OSError:
                            pass  # файл занят игрой
            os.replace(tmp, dest)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        if keep and keep > 0:
            mine = [b for b in self.backup_files(p) if b["world"] == safe_name(folder)]
            for old in mine[keep:]:
                try:
                    os.remove(os.path.join(self.backups_dir(p), old["file"]))
                except OSError:
                    pass
        return {"file": os.path.basename(dest), "size": os.path.getsize(dest)}

    def backup(self, profile_id, folder):
        p = self.profile_of(profile_id)
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        with self._lock:
            if self.working:
                return {"ok": False, "error": "Копия уже создаётся"}
            self.working = True
        try:
            self.progress(f"Копирую мир «{folder}»...")
            r = self.make_backup(p, folder, 0)
            return {"ok": True, **r, "warning": "Игра запущена: копия может оказаться неполной." if self.is_busy() else ""}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        finally:
            self.working = False

    def _free_folder(self, p, base):
        name = f"{base} (restored)"
        i = 2
        while os.path.exists(os.path.join(self.saves_dir(p), name)):
            name = f"{base} (restored {i})"
            i += 1
        return name

    def restore(self, profile_id, file):
        p = self.profile_of(profile_id)
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        if not is_base(file) or not str(file).lower().endswith(".zip"):
            return {"ok": False, "error": "Неверный файл копии"}
        if self.is_busy():
            return {"ok": False, "error": "Закрой игру перед восстановлением мира"}
        with self._lock:
            if self.working:
                return {"ok": False, "error": "Другая операция ещё выполняется"}
            self.working = True
        src = os.path.join(self.backups_dir(p), file)
        dest = None
        try:
            if not os.path.exists(src):
                return {"ok": False, "error": "Копия не найдена"}
            if os.path.getsize(src) > RESTORE_LIMIT:
                return {"ok": False, "error": "Копия слишком большая для восстановления в лаунчере. Распакуй zip вручную в папку saves."}
            self.progress("Восстанавливаю мир...")
            with zipfile.ZipFile(src) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
                tops = {n.split("/")[0] for n in names}
                if len(tops) != 1:
                    raise ValueError("В копии должна быть ровно одна папка мира")
                top = next(iter(tops))
                if not is_base(top) or f"{top}/level.dat" not in names:
                    raise ValueError("Это не копия мира Minecraft")
                dest = os.path.join(self.saves_dir(p), self._free_folder(p, top))
                os.makedirs(dest, exist_ok=True)
                for n in names:
                    target = util.safe_join(dest, n[len(top) + 1:])
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(n) as s, open(target, "wb") as o:
                        shutil.copyfileobj(s, o)
            return {"ok": True, "folder": os.path.basename(dest)}
        except Exception as e:  # noqa: BLE001
            if dest:
                shutil.rmtree(dest, ignore_errors=True)
            return {"ok": False, "error": str(e)}
        finally:
            self.working = False

    def remove_backup(self, profile_id, file):
        p = self.profile_of(profile_id)
        if not p or not is_base(file) or not str(file).lower().endswith(".zip"):
            return {"ok": False, "error": "Неверный файл копии"}
        try:
            try:
                os.remove(os.path.join(self.backups_dir(p), file))
            except FileNotFoundError:
                pass
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def auto_backup(self, profile, keep: int = 5, max_bytes: int = RESTORE_LIMIT) -> dict:
        out = {"made": [], "skipped": [], "failed": []}
        if not profile:
            return out
        with self._lock:
            if self.working:
                return out
            self.working = True
        try:
            backups = self.backup_files(profile)
            try:
                dirs = [d for d in os.listdir(self.saves_dir(profile)) if os.path.isdir(os.path.join(self.saves_dir(profile), d))]
            except OSError:
                return out
            for name in dirs:
                d = os.path.join(self.saves_dir(profile), name)
                try:
                    mtime = os.stat(os.path.join(d, "level.dat")).st_mtime * 1000
                except OSError:
                    continue
                last = next((b for b in backups if b["world"] == safe_name(name)), None)
                if last and last["time"] >= mtime:
                    continue
                if dir_size(d) > max_bytes:
                    out["skipped"].append(name)
                    continue
                try:
                    self.progress(f"Резервная копия мира «{name}»...")
                    self.make_backup(profile, name, keep)
                    out["made"].append(name)
                except Exception as e:  # noqa: BLE001
                    out["failed"].append({"world": name, "error": str(e)})
        finally:
            self.working = False
        return out


def setup(ctx):
    ctx.worlds = Worlds(ctx)


def handlers(ctx):
    w = ctx.worlds
    g = lambda a, k: (a or {}).get(k)  # noqa: E731
    return {
        "worlds:list": lambda a=None: w.list(g(a, "profileId")),
        "worlds:backup": lambda a=None: w.backup(g(a, "profileId"), g(a, "folder")),
        "worlds:restore": lambda a=None: w.restore(g(a, "profileId"), g(a, "file")),
        "worlds:remove-backup": lambda a=None: w.remove_backup(g(a, "profileId"), g(a, "file")),
    }
