"""Окно «Вход через Microsoft»: показывает код устройства (device code flow).

Ядро шлёт событие ms:code {code, url, expires}; страница настроек открывает это окно через show()
(не exec — иначе заблокируется цикл событий, пока идёт опрос входа) и закрывает, когда ms:login вернул результат.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer

from .. import i18n
from ..widgets import ClickLabel, Modal, label

i18n.register({
    "Открыть страницу входа": "Open the sign-in page",
    "Страница откроется в браузере сама. Окно закроется, когда вход завершится.":
        "The page opens in your browser by itself. This window closes when sign-in completes.",
})

_ALLOWED = re.compile(r"(^|\.)(microsoft\.com|microsoftonline\.com|live\.com)$")


def is_allowed_login_url(url: str) -> bool:
    """Открываем во внешнем браузере только страницы входа Microsoft (как в Electron-версии)."""
    try:
        u = urlparse(str(url))
    except ValueError:
        return False
    return u.scheme == "https" and bool(u.hostname) and bool(_ALLOWED.search(u.hostname.lower()))


class MsLoginDialog(Modal):
    def __init__(self, app, code: str, url: str, on_cancel=None, parent=None):
        super().__init__(app, "Вход через Microsoft", width=440, parent=parent)
        self.code = str(code or "")
        self.url = str(url or "")
        self._on_cancel = on_cancel
        self.body.addWidget(label(app, "Открой страницу и введи этот код:", "muted", wrap=True))

        self.code_label = label(app, None, "h1", selectable=True)
        self.code_label.setAlignment(Qt.AlignCenter)
        self.code_label.setStyleSheet("font-size: 30px; letter-spacing: 4px; padding: 14px;"
                                      "border: 1px dashed #9b9ba7; border-radius: 14px;")
        self.code_label.setText(self.code or "—")
        self.body.addWidget(self.code_label)

        self.url_label = ClickLabel(self.url or "—")
        self.url_label.setProperty("kind", "accent")
        self.url_label.setAlignment(Qt.AlignCenter)
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.clicked.connect(self.open_page)
        self.body.addWidget(self.url_label)
        self.body.addWidget(label(app, "Страница откроется в браузере сама. Окно закроется, когда вход завершится.",
                                  "muted", wrap=True))

        self.open_btn = self.add_button("Открыть страницу входа", "ghost", self.open_page)
        self.copy_btn = self.add_button("Копировать код", "ghost", self.copy_code)
        self.cancel_btn = self.add_button("Отмена", "ghost", self.cancel)
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(lambda: self.app.bind(self.copy_btn, "Копировать код"))

    def set_code(self, code: str, url: str) -> None:
        self.code, self.url = str(code or ""), str(url or "")
        self.code_label.setText(self.code or "—")
        self.url_label.setText(self.url or "—")

    def open_page(self) -> None:
        if is_allowed_login_url(self.url):
            self.app.ctx.ui.open_url(self.url)

    def copy_code(self) -> None:
        try:
            self.app.ctx.ui.set_clipboard_text(self.code)
            self.app.bind(self.copy_btn, "Скопировано")
            self._copy_timer.start(1500)
        except Exception:  # noqa: BLE001
            pass

    def cancel(self) -> None:
        if self._on_cancel is not None:
            self._on_cancel()
        self.close()

    def closeEvent(self, e):  # noqa: N802
        # крестик окна = отмена входа
        cb, self._on_cancel = self._on_cancel, None
        if cb is not None:
            cb()
        super().closeEvent(e)
