"""Окно консоли игры: снимок console:get + живые события console:lines / console:reset."""
from __future__ import annotations

import html
import re

from PySide6.QtWidgets import QCheckBox, QPlainTextEdit

from .. import i18n, theme
from ..widgets import Modal, label

CON_MAX = 3000
_ERR = re.compile(r"\bERROR\b|\bFATAL\b|Exception|^\s+at\s")
_WARN = re.compile(r"\bWARN\b")

i18n.register({
    "Консоль": "Console",
    "Консоль пуста: запусти игру, и здесь появится её вывод.": "The console is empty: start the game and its output will appear here.",
    "Строк: {n}": "Lines: {n}",
    "Скопировано ✓": "Copied ✓",
})


def line_color(l: dict) -> str:
    """Цвет строки консоли: лаунчер — приглушённый, ошибки красные, предупреждения жёлтые."""
    t = str(l.get("t", ""))
    if l.get("s") == "l":
        return theme.MUTED
    if _ERR.search(t):
        return theme.ERR
    if _WARN.search(t):
        return theme.WARN
    return theme.TEXT


class ConsoleDialog(Modal):
    def __init__(self, app, parent=None):
        super().__init__(app, "Консоль", width=900, height=520, parent=parent)
        self.setModal(False)  # окно можно держать открытым, пока идёт игра
        self.count = label(app, None, "muted")
        self.body.addWidget(self.count)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(CON_MAX)
        self.log.setStyleSheet("QPlainTextEdit { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 12px; }")
        self.body.addWidget(self.log, 1)
        self.follow = QCheckBox()
        app.bind(self.follow, "Прокручивать вниз")
        self.follow.setChecked(True)
        self.body.addWidget(self.follow)
        self._empty = False
        self._n = 0
        self.log.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.btn_clear = self.add_button("Очистить", on_click=self._clear)
        self.btn_copy = self.add_button("Копировать всё", on_click=self._copy)
        self.add_button("Закрыть", "primary", on_click=self.accept)
        app.event.connect(self._on_event)

    # ---------- данные ----------
    def open(self) -> None:
        """Показать окно и подтянуть текущее содержимое консоли."""
        self._reset_view()
        self.show()
        self.raise_()
        self.app.call("console:get", None, self._loaded, lambda m: self._set_empty())

    def _loaded(self, r) -> None:
        lines = r.get("lines") if isinstance(r, dict) else None
        if lines:
            self.append(lines)
        else:
            self._set_empty()

    def _reset_view(self) -> None:
        self.log.clear()
        self._n = 0
        self._empty = False
        self._count()

    def _set_empty(self) -> None:
        self._reset_view()
        self.log.appendHtml(f'<span style="color:{theme.MUTED}">{html.escape(self.app.t("Консоль пуста: запусти игру, и здесь появится её вывод."))}</span>')
        self._empty = True

    def append(self, lines: list) -> None:
        if self._empty:
            self.log.clear()
            self._empty = False
        parts = []
        for l in lines:
            if not isinstance(l, dict):
                continue
            parts.append(f'<span style="color:{line_color(l)}">{html.escape(str(l.get("t", "")))}</span>')
        if parts:
            self.log.appendHtml("<br>".join(parts))
            self._n = min(CON_MAX, self._n + len(parts))
        self._count()
        if self.follow.isChecked():
            bar = self.log.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _count(self) -> None:
        self.count.setText(self.app.t("Строк: {n}", n=self._n) if self._n else "")

    def _on_event(self, channel, payload) -> None:
        try:
            if not self.isVisible():
                return
            if channel == "console:lines" and isinstance(payload, list):
                self.append(payload)
            elif channel == "console:reset":
                self._reset_view()
        except RuntimeError:
            pass

    def _on_scroll(self, _v=0) -> None:
        bar = self.log.verticalScrollBar()
        self.follow.setChecked(bar.maximum() - bar.value() < 40)

    def _clear(self) -> None:
        self.app.call("console:clear", None, None, lambda m: self.app.toast(m, "err"))

    def _copy(self) -> None:
        def ok(r):
            good = isinstance(r, dict) and r.get("ok")
            self.btn_copy.setText(self.app.t("Скопировано ✓") if good else self.app.t("Копировать всё"))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1800, lambda: self._restore_copy())
        self.app.call("console:copy", None, ok, lambda m: self.app.toast(m, "err"))

    def _restore_copy(self) -> None:
        try:
            self.btn_copy.setText(self.app.t("Копировать всё"))
        except RuntimeError:
            pass
