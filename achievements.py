"""Вкладка «Достижения»: все значки, полученные ярче, неполученные серые, секретные скрыты до получения."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ..achievements_ui import fmt_when, tile_pixmap
from ..widgets import VScroll, label


def sort_items(items: list[dict]) -> list[dict]:
    """Сначала полученные (новые выше), потом неполученные в обычном порядке, секретные неполученные в конце."""
    got = sorted((i for i in items if i.get("unlocked")), key=lambda i: i["unlocked"], reverse=True)
    todo = [i for i in items if not i.get("unlocked") and not i.get("hidden")]
    secret = [i for i in items if not i.get("unlocked") and i.get("hidden")]
    return got + todo + secret


def progress_text(item: dict) -> str:
    p = item.get("progress")
    if not p or item.get("unlocked"):
        return ""
    cur, goal, unit = p
    fmt = lambda v: str(int(v)) if float(v).is_integer() else str(v)  # noqa: E731
    return f"{fmt(cur)} / {fmt(goal)}" + (f" {unit}" if unit else "")


class AchievementsPage(QWidget):
    COLS = 2

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.items: list[dict] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label(app, "Достижения", "h2"))
        head.addStretch(1)
        self.count = QLabel("")
        self.count.setProperty("kind", "accent")
        head.addWidget(self.count)
        root.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        root.addWidget(self.bar)
        self.scroll = VScroll()
        root.addWidget(self.scroll, 1)
        app.event.connect(self._on_event)

    def _on_event(self, ch: str, payload) -> None:
        if ch == "achievement:unlocked":
            self.load()

    def on_show(self) -> None:
        self.load()

    def load(self) -> None:
        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                self.render(r.get("items") or [])
        self.app.call("achievements:list", None, ok, lambda m: self.app.toast(m, "err"))

    def retranslate(self) -> None:
        self.render(self.items)

    def render(self, items: list[dict]) -> None:
        self.items = items
        t = self.app.t
        done = sum(1 for i in items if i.get("unlocked"))
        self.count.setText(f"{t('Получено достижений')}: {done} / {len(items)}")
        self.bar.setRange(0, max(1, len(items)))
        self.bar.setValue(done)
        self.scroll.clear()
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for n, it in enumerate(sort_items(items)):
            grid.addWidget(self._card(it), n // self.COLS, n % self.COLS)
        for c in range(self.COLS):
            grid.setColumnStretch(c, 1)
        self.scroll.lay.addWidget(host)
        self.scroll.lay.addStretch(1)

    def _card(self, it: dict) -> QWidget:
        t = self.app.t
        got = bool(it.get("unlocked"))
        secret = bool(it.get("hidden")) and not got
        card = QFrame()
        card.setProperty("kind", "buildsel" if got else "build")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        badge = QLabel()
        badge.setFixedSize(66, 66)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(tile_pixmap(self.app.ctx, it.get("id", ""), got, 66, known=not secret))
        row.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("???" if secret else t(it.get("title", "")))
        title.setProperty("kind", "h3")
        col.addWidget(title)
        desc = QLabel(t("Секретное достижение") if secret else t(it.get("desc", "")))
        desc.setWordWrap(True)
        desc.setProperty("kind", "muted")
        col.addWidget(desc)
        if got:
            when = QLabel(f"{t('Получено')}: {fmt_when(it['unlocked'])}")
            when.setProperty("kind", "ok")
            col.addWidget(when)
        elif it.get("progress"):
            cur, goal, _unit = it["progress"]
            pb = QProgressBar()
            pb.setTextVisible(False)
            pb.setRange(0, 1000)
            pb.setValue(int(1000 * float(cur) / float(goal)) if goal else 0)
            col.addWidget(pb)
            pt = QLabel(progress_text(it))
            pt.setProperty("kind", "muted")
            col.addWidget(pt)
        col.addStretch(1)
        row.addLayout(col, 1)
        return card

    def selftest(self) -> None:
        sample = [
            {"id": "first_profile", "glyph": "★", "color": "#e0b84a", "title": "Первая сборка", "desc": "Создай свой первый профиль", "hidden": False, "unlocked": 1700000000000},
            {"id": "modder", "glyph": "⚒", "color": "#b5533c", "title": "Коллекционер", "desc": "Установи 10 модов", "hidden": False, "unlocked": None, "progress": [3, 10, ""]},
            {"id": "hour", "glyph": "⌛", "color": "#2f8fb5", "title": "Час в игре", "desc": "Наиграй 1 час", "hidden": False, "unlocked": None, "progress": [0.5, 1.0, "ч"]},
            {"id": "secret", "glyph": "✶", "color": "#e0b84a", "title": "Нашёл секрет", "desc": "Найди пасхалку в лаунчере", "hidden": True, "unlocked": None},
        ]
        self.render(sample)
