"""Общие виджеты интерфейса. Страницы строят экран только из них + стандартных виджетов Qt.

Подписи всегда задаём через app.bind(widget, "Русский текст") — так язык переключается на лету.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)


def polish(w: QWidget) -> None:
    """Применить стиль после смены динамического свойства (kind)."""
    w.style().unpolish(w)
    w.style().polish(w)


def set_kind(w: QWidget, kind: str) -> None:
    w.setProperty("kind", kind)
    polish(w)


def label(app, ru: str | None = "", kind: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    """Надпись. kind: h1 h2 h3 muted ok warn err accent ph. ru=None -> пустая надпись без перевода."""
    lb = QLabel()
    if kind:
        lb.setProperty("kind", kind)
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if ru:
        app.bind(lb, ru)
    return lb


def button(app, ru: str, kind: str = "ghost", on_click=None, parent=None, checkable: bool = False) -> QPushButton:
    """Кнопка. kind: ghost primary danger small nav chip play."""
    b = QPushButton(parent)
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(checkable)
    app.bind(b, ru)
    if on_click is not None:
        b.clicked.connect(lambda _=False: on_click())
    return b


class Card(QFrame):
    """Панель-«стекло». kind: card (по умолчанию) | soft | current | fit."""

    def __init__(self, kind: str = "card", layout: str = "v", margins=(16, 14, 16, 14), spacing: int = 8, parent=None):
        super().__init__(parent)
        self.setProperty("kind", kind)
        lay = QVBoxLayout(self) if layout == "v" else QHBoxLayout(self)
        lay.setContentsMargins(*margins)
        lay.setSpacing(spacing)
        self.lay = lay

    def set_kind(self, kind: str) -> None:
        set_kind(self, kind)


class FlowLayout(QLayout):
    """Раскладка «в строку с переносом» (для чипов и карточек)."""

    def __init__(self, parent=None, hspacing: int = 8, vspacing: int = 8):
        super().__init__(parent)
        self._items: list = []
        self._h, self._v = hspacing, vspacing

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            sz = it.sizeHint()
            if x + sz.width() > r.right() + 1 and line_h > 0:
                x = r.x()
                y += line_h + self._v
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._h
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()

    def clear(self):
        while self._items:
            it = self._items.pop()
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()


def clear_layout(lay) -> None:
    """Удалить все элементы раскладки (для перерисовки списков)."""
    if lay is None:
        return
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        else:
            sub = it.layout()
            if sub is not None:
                clear_layout(sub)


class VScroll(QScrollArea):
    """Прокручиваемая колонка: добавляй виджеты в .lay (QVBoxLayout)."""

    def __init__(self, parent=None, margins=(0, 0, 6, 0), spacing: int = 10):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setAttribute(Qt.WA_StyledBackground, False)
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(spacing)
        self.setWidget(inner)
        self.viewport().setAutoFillBackground(False)

    def clear(self):
        clear_layout(self.lay)

    def scroll_to_widget(self, w: QWidget) -> None:
        self.ensureWidgetVisible(w, 0, 40)


class Modal(QDialog):
    """Диалог. Содержимое — в .body (QVBoxLayout), кнопки — через add_button().

    dlg = Modal(app, "Заголовок", width=520); dlg.body.addWidget(...); dlg.add_button("Закрыть", on_click=dlg.accept)
    dlg.exec() — блокирует до закрытия; либо dlg.show().
    """

    def __init__(self, app, title_ru: str, width: int = 520, parent=None, height: int | None = None):
        super().__init__(parent or app.window)
        self.app = app
        app.bind(self, title_ru, prop="windowTitle")
        self.setModal(True)
        self.setMinimumWidth(width)
        if height:
            self.setMinimumHeight(height)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        self.title = label(app, title_ru, "h2")
        root.addWidget(self.title)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.addStretch(1)
        root.addLayout(self.actions)

    def add_button(self, ru: str, kind: str = "ghost", on_click=None, close: bool = False) -> QPushButton:
        b = button(self.app, ru, kind)
        def go(_=False):
            if on_click is not None:
                on_click()
            if close:
                self.accept()
        b.clicked.connect(go)
        self.actions.addWidget(b)
        return b


class RemoteIcon(QLabel):
    """Квадратная иконка с сервера (мод, сборка). Пока грузится — буква-заглушка."""

    def __init__(self, app, url: str | None, size: int = 56, fallback: str = "?", parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("kind", "ph")
        self._size = size
        self.setText((fallback or "?")[:1].upper())
        if url:
            app.call("icon:get", url, self._loaded)

    def _loaded(self, path):
        try:
            if not path:
                return
            pm = QPixmap(path)
            if pm.isNull():
                return
            self.setProperty("kind", "")
            polish(self)
            self.setPixmap(pm.scaled(self._size, self._size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        except RuntimeError:
            pass  # виджет уже удалён


class ClickLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: rgba(255,255,255,30); background: rgba(255,255,255,30); max-height: 1px;")
    return f


def hrow(*widgets, spacing: int = 8, stretch_last: bool = False) -> QHBoxLayout:
    """Строка из виджетов/растяжек: hrow(w1, w2, 1, w3) — число = растяжка."""
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addStretch(w)
        elif isinstance(w, QLayout):
            lay.addLayout(w)
        else:
            lay.addWidget(w)
    return lay


def sizepolicy_expand(w: QWidget) -> QWidget:
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    return w
