"""Достижения: значки за дела в лаунчере (первая сборка, первый мод, часы игры…).

Хранятся в achievements.json рядом с настройками. Выдаются автоматически: Api.call после каждого вызова канала
зовёт observe(), статистика игры зовёт check_stats(). При получении уходит событие achievement:unlocked
(интерфейс показывает всплывающее поздравление, как в Steam). Каналы: achievements:list, achievements:grant.
"""
from __future__ import annotations

import threading
import time

from . import util

# (id, значок, цвет, название, описание, секретное)
DEFS = [
    ("first_profile", "▦", "#5b6ee1", "Первая сборка", "Создай свой первый профиль", False),
    ("first_launch", "▶", "#3ddc97", "Поехали!", "Запусти игру из лаунчера", False),
    ("first_mod", "✦", "#c98a2b", "Первый мод", "Установи мод из каталога", False),
    ("modder", "⚒", "#b5533c", "Коллекционер", "Установи 10 модов", False),
    ("pack", "❖", "#8b5cc2", "Готовая сборка", "Установи сборку из каталога", False),
    ("resourcepack", "✿", "#2f8fb5", "Новый стиль", "Установи ресурспак", False),
    ("shader", "☀", "#e0b84a", "Красота!", "Установи шейдеры", False),
    ("optimize", "⚡", "#6a8f3a", "Оптимизатор", "Установи мод для оптимизации", False),
    ("export", "✉", "#c2557a", "Поделиться", "Экспортируй сборку в .mrpack", False),
    ("import", "⇩", "#2f8fb5", "Переезд", "Импортируй сборку или профиль из другого лаунчера", False),
    ("backup", "⛨", "#5b6ee1", "Страховка", "Сделай резервную копию мира", False),
    ("server", "☖", "#3f9d78", "Сетевой игрок", "Добавь сервер в список", False),
    ("skin", "☺", "#c98a2b", "Новый облик", "Примени скин", False),
    ("microsoft", "✔", "#3ddc97", "Лицензионный", "Войди через аккаунт Microsoft", False),
    ("compat", "☑", "#8b5cc2", "Проверено", "Проверь моды на совместимость", False),
    ("fresh", "↻", "#2f8fb5", "Всегда свежие", "Обнови моды до новых версий", False),
    ("background", "◐", "#c2557a", "Свой стиль", "Поставь свой фон лаунчера", False),
    ("builds_5", "▤", "#8b5cc2", "Коллекция", "Создай 5 сборок", False),
    ("clone", "❏", "#2f8fb5", "Близнецы", "Сделай копию сборки", False),
    ("undo", "↶", "#c98a2b", "Машина времени", "Откати моды после обновления", False),
    ("code", "⌘", "#3f9d78", "Код в кармане", "Получи код сборки, чтобы поделиться", False),
    ("drop", "⇲", "#c2557a", "Ловкость рук", "Перетащи файл в окно лаунчера", False),
    ("accent", "◉", "#5b6ee1", "Свой цвет", "Выбери цвет лаунчера", False),
    ("tour", "★", "#e0b84a", "Прилежный ученик", "Дослушай тему обучения до конца", False),
    ("launches_10", "♥", "#c2557a", "Завсегдатай", "Запусти игру 10 раз", False),
    ("hour", "⌛", "#2f8fb5", "Час в игре", "Наиграй 1 час", False),
    ("ten_hours", "♛", "#c98a2b", "Заядлый игрок", "Наиграй 10 часов", False),
    ("night", "☾", "#5b6ee1", "Ночная смена", "Запусти игру глубокой ночью", True),
    ("secret", "✶", "#e0b84a", "Нашёл секрет", "Найди пасхалку в лаунчере", True),
]
ORDER = [d[0] for d in DEFS]
BY_ID = {d[0]: d for d in DEFS}
UI_GRANTABLE = {"tour", "secret", "background", "accent"}  # их выдаёт интерфейс (то, чего ядро не видит)
COUNT_GOALS = {"modder": ("modsInstalled", 10), "launches_10": ("launches", 10)}
HOUR_GOALS = {"hour": 1.0, "ten_hours": 10.0}


def info(aid: str, unlocked=None) -> dict:
    _id, glyph, color, title, desc, hidden = BY_ID[aid]
    return {"id": aid, "glyph": glyph, "color": color, "title": title, "desc": desc, "hidden": hidden, "unlocked": unlocked}


class Achievements:
    def __init__(self, ctx):
        self.ctx = ctx
        self._lock = threading.RLock()
        self._data: dict | None = None

    @property
    def file(self) -> str:
        import os
        return os.path.join(self.ctx.user_data, "achievements.json")

    def load(self) -> dict:
        with self._lock:
            if self._data is None:
                raw = util.read_json(self.file, None)
                data = {"unlocked": {}, "counters": {}}
                if isinstance(raw, dict):
                    for k, v in (raw.get("unlocked") or {}).items():
                        if k in BY_ID and isinstance(v, (int, float)):
                            data["unlocked"][k] = int(v)
                    for k, v in (raw.get("counters") or {}).items():
                        if isinstance(v, (int, float)):
                            data["counters"][str(k)] = int(v)
                self._data = data
            return self._data

    def _save(self) -> None:
        try:
            util.write_json(self.file, self._data, indent=None)
        except Exception:  # noqa: BLE001 — достижения не должны ломать лаунчер
            pass

    def has(self, aid: str) -> bool:
        return aid in self.load()["unlocked"]

    def grant(self, aid: str) -> bool:
        """Выдаёт достижение один раз; True — только что получено."""
        if aid not in BY_ID:
            return False
        with self._lock:
            d = self.load()
            if aid in d["unlocked"]:
                return False
            d["unlocked"][aid] = int(time.time() * 1000)
            self._save()
        try:
            self.ctx.send("achievement:unlocked", info(aid, d["unlocked"][aid]))
        except Exception:  # noqa: BLE001
            pass
        return True

    def bump(self, counter: str, n: int = 1) -> int:
        with self._lock:
            d = self.load()
            d["counters"][counter] = d["counters"].get(counter, 0) + max(0, int(n))
            self._save()
            return d["counters"][counter]

    # ----- статистика игры
    def _totals(self) -> tuple[int, float]:
        st = getattr(self.ctx, "stats", None)
        if st is None:
            return 0, 0.0
        t = (st.summary() or {}).get("total") or {}
        return int(t.get("launches") or 0), float(t.get("ms") or 0) / 3_600_000

    def check_stats(self) -> None:
        try:
            launches, hours = self._totals()
            if launches >= 1:
                self.grant("first_launch")
            if launches >= COUNT_GOALS["launches_10"][1]:
                self.grant("launches_10")
            for aid, goal in HOUR_GOALS.items():
                if hours >= goal:
                    self.grant(aid)
        except Exception as e:  # noqa: BLE001
            self.ctx.diag(f"achievements.check_stats: {e}")

    def listing(self) -> dict:
        d = self.load()
        launches, hours = self._totals()
        items = []
        for aid in ORDER:
            it = info(aid, d["unlocked"].get(aid))
            if aid in COUNT_GOALS:
                key, goal = COUNT_GOALS[aid]
                cur = launches if key == "launches" else d["counters"].get(key, 0)
                it["progress"] = [min(cur, goal), goal, ""]
            elif aid in HOUR_GOALS:
                it["progress"] = [round(min(hours, HOUR_GOALS[aid]), 1), HOUR_GOALS[aid], "ч"]
            items.append(it)
        return {"ok": True, "items": items, "done": len(d["unlocked"]), "total": len(ORDER)}


def observe(ctx, channel: str, arg, res) -> None:
    """Вызывается после каждого вызова канала: решает, не выдать ли достижение."""
    a = getattr(ctx, "achievements", None)
    if a is None or not isinstance(res, dict) or res.get("ok") is not True:
        return
    arg = arg if isinstance(arg, dict) else {}
    g = a.grant
    if channel == "profiles:create":
        g("first_profile")
    elif channel == "profiles:duplicate":
        g("clone")
    elif channel == "installed:rollback":
        g("undo")
    elif channel == "profile:code":
        g("code")
    elif channel == "files:drop":
        g("drop")
    elif channel == "game:launch":
        a.check_stats()
        if time.localtime().tm_hour < 5:
            g("night")
    elif channel == "mods:install":
        kind = arg.get("kind") or "mod"
        if kind == "resourcepack":
            g("resourcepack")
        elif kind == "shader":
            g("shader")
        else:
            g("first_mod")
            if a.bump("modsInstalled", 1 + int(res.get("extra") or 0)) >= COUNT_GOALS["modder"][1]:
                g("modder")
    elif channel == "opt:install":
        g("optimize")
    elif channel == "pack:install":
        g("pack")
    elif channel == "profile:export":
        g("export")
    elif channel in ("profile:import", "import:run", "profile:code_import"):
        g("import")
    elif channel == "worlds:backup":
        g("backup")
    elif channel in ("servers:add", "servers:import"):
        g("server")
    elif channel == "skins:apply":
        g("skin")
    elif channel == "ms:login":
        g("microsoft")
    elif channel == "compat:check":
        g("compat")
    elif channel in ("installed:update", "installed:autoupdate"):
        if channel == "installed:update" or int(res.get("updated") or 0) > 0:
            g("fresh")
    elif channel == "bg:choose":
        g("background")
    if len(ctx.settings.get("profiles") or []) >= 5:
        g("builds_5")


def setup(ctx) -> None:
    ctx.achievements = Achievements(ctx)


def handlers(ctx):
    def listing(_=None):
        return ctx.achievements.listing()

    def grant(arg=None):
        aid = (arg or {}).get("id")
        if aid not in UI_GRANTABLE:
            return {"ok": False, "error": "Нельзя выдать это достижение"}
        return {"ok": True, "new": ctx.achievements.grant(aid)}

    return {"achievements:list": listing, "achievements:grant": grant}
