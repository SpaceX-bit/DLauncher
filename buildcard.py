"""Карточка сборки (профиля) для списков: цветная плитка с буквами, название, версия, моды, время игры."""
from __future__ import annotations

import time
import zlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout

from . import i18n
from .pages._profile_util import fmt_date, loader_name

i18n.register({
    "Выбрать": "Select",
    "Играть": "Play",
    "Выбрана": "Selected",
    "модов: {n}": "mods: {n}",
    "Не запускалась": "Never played",
    "Ещё": "More",
    "онлайн": "online",
    "офлайн": "offline",
    "Без группы": "No group",
})

TILE_COLORS = ["#5b6ee1", "#c2557a", "#3f9d78", "#c98a2b", "#8b5cc2", "#2f8fb5", "#b5533c", "#6a8f3a"]


def initials(name: str) -> str:
    """Две буквы для плитки: первые буквы слов или первые два символа."""
    words = [w for w in str(name or "").replace("_", " ").replace("-", " ").split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    s = words[0] if words else "?"
    return s[:2].upper()


def tile_color(name: str) -> str:
    return TILE_COLORS[zlib.crc32(str(name or "").encode("utf-8")) % len(TILE_COLORS)]


def tile_look(profile: dict) -> tuple[str, str]:
    """(цвет, текст плитки): свои цвет и значок сборки, иначе по названию."""
    color = profile.get("color")
    if not (isinstance(color, str) and len(color) == 7 and color.startswith("#")):
        color = tile_color(profile.get("name"))
    glyph = profile.get("glyph")
    return color, (glyph if isinstance(glyph, str) and glyph else initials(profile.get("name")))


_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
STATUS_TTL = 60.0


def status_text(app, r: dict) -> tuple[str, bool]:
    """Строка для карточки: «Название · онлайн · 42 ms · 5/100» и признак «онлайн»."""
    srv = r.get("server") or {}
    name = srv.get("name") or srv.get("host") or ""
    if r.get("online"):
        pl = r.get("players") or {}
        extra = f" · {pl.get('online', 0)}/{pl.get('max', 0)}" if pl else ""
        return f"{name} · {app.t('онлайн')} · {r.get('latency')} ms{extra}", True
    return f"{name} · {app.t('офлайн')}", False


class BuildCard(QFrame):
    """Клик по карточке — выбрать; кнопка справа — выбрать или (если уже выбрана) играть."""
    chosen = Signal(str)
    play = Signal(str)

    def __init__(self, app, profile: dict, selected: bool = False, compact: bool = False, actions=None):
        super().__init__()
        self.app = app
        self.pid = profile["id"]
        self.profile = profile
        self.selected = selected
        self.setProperty("kind", "buildsel" if selected else "build")
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(12)
        color, text = tile_look(profile)
        tile = QLabel(text)
        tile.setAlignment(Qt.AlignCenter)
        size = 40 if compact else 48
        tile.setFixedSize(size, size)
        tile.setStyleSheet(f"background: {color}; color: #fff; border-radius: 10px;"
                           "font-weight: 800; font-size: 15px; border: none;")
        row.addWidget(tile)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = QLabel(str(profile.get("name") or ""))
        name.setStyleSheet("font-weight: 700; font-size: 14px; background: transparent; border: none;")
        col.addWidget(name)
        ver = QLabel(f"{profile.get('version', '')} · {loader_name(profile.get('loader', 'vanilla'))}")
        ver.setProperty("kind", "muted")
        col.addWidget(ver)
        last = fmt_date(app, profile.get("lastPlayed")) if profile.get("lastPlayed") else app.t("Не запускалась")
        meta = QLabel(f"{app.t('модов: {n}', n=profile.get('modsCount', 0))} · {last}")
        meta.setProperty("kind", "muted")
        meta.setStyleSheet("font-size: 11px;")
        col.addWidget(meta)
        self.srv = QLabel("")
        self.srv.setProperty("kind", "muted")
        self.srv.setStyleSheet("font-size: 11px;")
        self.srv.hide()
        col.addWidget(self.srv)
        row.addLayout(col, 1)
        self.btn = QPushButton(app.t("Играть") if selected else app.t("Выбрать"))
        self.btn.setProperty("kind", "primary" if selected else "ghost")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda _=False: self.play.emit(self.pid) if self.selected else self.chosen.emit(self.pid))
        row.addWidget(self.btn)
        self.actions = actions or []  # [(текст, функция)] — меню «⋯»; текст None — разделитель
        if self.actions:
            self.more = QPushButton("\u22EF")
            self.more.setProperty("kind", "small")
            self.more.setToolTip(app.t("Ещё"))
            self.more.setCursor(Qt.PointingHandCursor)
            self.more.clicked.connect(lambda _=False: self._menu())
            row.addWidget(self.more)

    def load_status(self) -> None:
        """Запросить онлайн/пинг избранного (или последнего) сервера; результат кэшируется на минуту."""
        if not self.profile.get("servers"):
            return
        hit = _STATUS_CACHE.get(self.pid)
        if hit and time.time() - hit[0] < STATUS_TTL:
            self.set_status(hit[1])
            return

        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                _STATUS_CACHE[self.pid] = (time.time(), r)
                self.set_status(r)
        self.app.call("servers:status", {"profileId": self.pid}, ok, None)

    def set_status(self, r: dict) -> None:
        try:
            if not r.get("server"):
                return
            text, online = status_text(self.app, r)
            self.srv.setText(text)
            self.srv.setStyleSheet(f"font-size: 11px; color: {'#4caf7d' if online else '#d9695f'};")
            self.srv.show()
        except RuntimeError:  # карточку уже удалили
            pass

    def _menu(self) -> None:
        m = QMenu(self)
        for ru, fn in self.actions:
            if ru is None:
                m.addSeparator()
                continue
            m.addAction(self.app.t(ru)).triggered.connect(lambda _=False, f=fn: f())
        m.exec(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and not self.selected:
            self.chosen.emit(self.pid)
        super().mousePressEvent(e)


def recent_first(profiles: list[dict]) -> list[dict]:
    """Недавно игравшие — сверху, потом остальные в исходном порядке."""
    played = sorted((p for p in profiles if p.get("lastPlayed")), key=lambda p: p["lastPlayed"], reverse=True)
    rest = [p for p in profiles if not p.get("lastPlayed")]
    return played + rest


def filter_profiles(profiles: list[dict], query: str) -> list[dict]:
    """Поиск сборки по названию, версии Minecraft, загрузчику или группе."""
    q = query.strip().lower() if isinstance(query, str) else ""
    if not q:
        return list(profiles)
    return [p for p in profiles
            if q in str(p.get("name", "")).lower() or q in str(p.get("version", "")).lower()
            or q in str(p.get("loader", "")).lower() or q in str(p.get("group", "")).lower()]


def group_profiles(profiles: list[dict]) -> list[tuple[str, list[dict]]]:
    """[(группа, сборки)]: сначала сборки без группы (имя группы пустое), затем группы по алфавиту."""
    by: dict[str, list[dict]] = {}
    for p in profiles:
        g = p.get("group")
        by.setdefault(g.strip() if isinstance(g, str) else "", []).append(p)
    return [(g, by[g]) for g in sorted(by, key=lambda x: (x != "", x.lower()))]
