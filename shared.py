"""Общие мелочи страниц «Моды», «Установлено» и их окон: названия, форматирование, переключатель-сегмент."""
from __future__ import annotations

import datetime
import re

from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QVBoxLayout

from ..widgets import button

NAMES = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt"}
KIND_LABEL = {"mod": "Моды", "modpack": "Сборки", "resourcepack": "Ресурспаки", "shader": "Шейдеры"}
INST_DIR = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
INST_WHAT = {"mod": "модов", "resourcepack": "ресурспаков", "shader": "шейдеров"}


def profile_label(p: dict) -> str:
    return f"{p.get('name')} · {p.get('version')} · {NAMES.get(p.get('loader'), p.get('loader'))}"


def fmt_size(b) -> str:
    b = float(b or 0)
    if b > 1073741824:
        return f"{b / 1073741824:.1f} ГБ"
    if b > 1048576:
        return f"{b / 1048576:.1f} МБ"
    return f"{max(1, round(b / 1024))} КБ"


def fmt_num(app, n) -> str:
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    return f"{n:,}".replace(",", " " if app.lang == "ru" else ",")


def fmt_date(app, s) -> str:
    if not s:
        return ""
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return d.strftime("%d.%m.%Y" if app.lang == "ru" else "%m/%d/%Y")


def meta(parts) -> str:
    return " · ".join(str(p) for p in parts if p)


def strip_ext(name: str) -> str:
    return re.sub(r"\.(jar|zip)(\.disabled)?$", "", name or "", flags=re.I)


class Segment(QFrame):
    """Переключатель из кнопок (как .seg в Electron-версии). items: [(ключ, русская подпись)]."""

    def __init__(self, app, items, current: str, on_change=None, translate: bool = True, vertical: bool = False):
        super().__init__()
        self.setProperty("kind", "soft")
        self.app = app
        self.on_change = on_change
        self.key = current
        self.buttons: dict = {}
        lay = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, ru in items:
            b = button(app, ru, "nav", checkable=True)
            if not translate:
                b.setText(ru)
            b.setChecked(key == current)
            if vertical:
                b.setStyleSheet("text-align: left; padding: 8px 12px;")
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            self._group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b

    def select(self, key: str, notify: bool = True) -> None:
        self.key = key
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        if notify and self.on_change:
            self.on_change(key)
