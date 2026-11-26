"""Общие мелочи страниц «Играть» и «Профили» (форматирование, переход между страницами)."""
from __future__ import annotations

import datetime

from .. import i18n

NAMES = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt"}
TYPE_LABEL = {"release": "релиз", "snapshot": "снапшот", "old_beta": "бета", "old_alpha": "альфа"}

i18n.register({
    "меньше минуты": "less than a minute",
    "{h} ч {m} мин": "{h} h {m} min",
    "{m} мин": "{m} min",
    "На сервер: {host}": "To server: {host}",
    "Зайти на {host}:{port}": "Join {host}:{port}",
    "Выбран": "Selected",
    "Нет профилей": "No profiles",
})


def loader_name(loader: str) -> str:
    return NAMES.get(loader, loader or "")


def profile_label(p: dict) -> str:
    return f"{p.get('name', '')} · {p.get('version', '')} · {loader_name(p.get('loader', 'vanilla'))}"


def to_datetime(t) -> datetime.datetime | None:
    """Принимает миллисекунды (число) или строку ISO."""
    if t in (None, "", 0):
        return None
    try:
        if isinstance(t, (int, float)):
            return datetime.datetime.fromtimestamp(float(t) / 1000.0)
        s = str(t).strip()
        if s.isdigit():
            return datetime.datetime.fromtimestamp(float(s) / 1000.0)
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        return None


def fmt_date(app, t) -> str:
    d = to_datetime(t)
    if d is None:
        return "—"
    return d.strftime("%m/%d/%Y") if app.lang == "en" else d.strftime("%d.%m.%Y")


def fmt_dur(app, ms) -> str:
    m = int(ms or 0) // 60000
    if m < 1:
        return app.t("меньше минуты")
    h = m // 60
    return app.t("{h} ч {m} мин", h=h, m=m % 60) if h else app.t("{m} мин", m=m)


def get_page(app, key: str):
    """Страница главного окна по ключу (или None, если окна нет — например, в тестах)."""
    w = getattr(app, "window", None)
    pages = getattr(w, "pages", None) if w is not None else None
    return pages.get(key) if isinstance(pages, dict) else None


def select_profile(app, pid: str, then=None) -> None:
    """profiles:select -> обновить кеш профилей -> then()."""
    def ok(r):
        if isinstance(r, dict) and r.get("ok") is False:
            app.toast(r.get("error") or "Профиль не найден", "err")
            return
        app.current_id = pid
        app.refresh_profiles(then)
    app.call("profiles:select", pid, ok, lambda m: app.toast(m, "err"))
