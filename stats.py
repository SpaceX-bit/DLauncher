"""Статистика: сколько времени и сколько раз играли в каждом профиле (userData/stats.json). Порт lib/stats.js."""
from __future__ import annotations

import os
import threading
import time

from . import util

MIN_SESSION_MS = 5000          # запуски короче 5 секунд в игровое время не считаем
MAX_SESSION_MS = 7 * 24 * 3600 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


class Stats:
    def __init__(self, ctx, now=_now_ms):
        self.ctx = ctx
        self.now = now
        self._data: dict | None = None
        self._session: dict | None = None  # {'id', 'start'}
        self._lock = threading.RLock()

    @property
    def file(self) -> str:
        return os.path.join(self.ctx.user_data, "stats.json")

    def load(self) -> dict:
        with self._lock:
            if self._data is not None:
                return self._data
            data = {"profiles": {}}
            raw = util.read_json(self.file, None)
            if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
                for pid, v in raw["profiles"].items():
                    if isinstance(v, dict) and isinstance(v.get("ms"), (int, float)) \
                            and isinstance(v.get("launches"), (int, float)):
                        try:
                            last = float(v.get("last") or 0)
                        except (TypeError, ValueError):
                            last = 0
                        data["profiles"][pid] = {"ms": max(0, v["ms"]), "launches": max(0, int(v["launches"])),
                                                 "last": last}
            self._data = data
            return data

    def _save(self) -> None:
        try:
            util.write_json(self.file, self._data, indent=None)
        except Exception:  # noqa: BLE001 — статистика не должна ломать игру
            pass

    def _entry(self, pid: str) -> dict:
        d = self.load()
        if pid not in d["profiles"]:
            d["profiles"][pid] = {"ms": 0, "launches": 0, "last": 0}
        return d["profiles"][pid]

    def begin(self, profile_id) -> None:
        """Игра запустилась."""
        if not profile_id:
            return
        with self._lock:
            if self._session:
                self.end()
            e = self._entry(profile_id)
            e["launches"] += 1
            e["last"] = self.now()
            self._session = {"id": profile_id, "start": self.now()}
            self._save()

    def end(self) -> None:
        """Игра закрылась (или лаунчер закрывается)."""
        with self._lock:
            if not self._session:
                return
            dur = min(max(0, self.now() - self._session["start"]), MAX_SESSION_MS)
            e = self._entry(self._session["id"])
            if dur >= MIN_SESSION_MS:
                e["ms"] += dur
            e["last"] = self.now()
            self._session = None
            self._save()
        ach = getattr(self.ctx, "achievements", None)
        if ach is not None:
            ach.check_stats()

    def summary(self) -> dict:
        with self._lock:
            d = self.load()
            s = self._session
            live = min(max(0, self.now() - s["start"]), MAX_SESSION_MS) if s else 0
            names = {p["id"]: p.get("name") for p in (self.ctx.settings.get("profiles") or [])}
            items = []
            total_ms = total_launches = 0
            for pid, v in d["profiles"].items():
                ms = v["ms"] + (live if s and s["id"] == pid else 0)
                total_ms += ms
                total_launches += v["launches"]
                if pid in names:
                    items.append({"id": pid, "name": names[pid], "ms": ms, "launches": v["launches"], "last": v["last"]})
            items.sort(key=lambda x: -x["ms"])
            return {
                "total": {"ms": total_ms, "launches": total_launches},
                "items": items,
                "top": items[0]["id"] if items and items[0]["ms"] > 0 else None,
                "playing": s["id"] if s else None,
            }


def setup(ctx) -> None:
    ctx.stats = Stats(ctx)


def shutdown(ctx) -> None:
    s = getattr(ctx, "stats", None)
    if s is not None:
        s.end()


def handlers(ctx):
    def stats_get(_=None):
        st = getattr(ctx, "stats", None) or Stats(ctx)
        return {"ok": True, **st.summary()}

    return {"stats:get": stats_get}
