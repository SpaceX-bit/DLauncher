"""Окно «Вышло обновление»: список изменений, кнопки «Скачать» и «Позже». После загрузки лаунчер сам перезапускается."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar

from .. import i18n
from ..widgets import Modal

i18n.register({
    "Вышло обновление": "An update is available",
    "Вышла новая версия DLauncher: {v}": "A new DLauncher version is out: {v}",
    "Скачать": "Download",
    "Позже": "Later",
    "Скачиваю обновление: {p}%": "Downloading update: {p}%",
    "Обновление скачано. Лаунчер перезапустится...": "Update downloaded. The launcher will restart...",
    "Ошибка обновления: {m}": "Update error: {m}",
    "Что изменилось:": "What changed:",
})


class UpdateDialog(Modal):
    def __init__(self, app, version: str, notes: str = "", parent=None):
        super().__init__(app, "Вышло обновление", width=460, parent=parent)
        self.version = version
        self._started = False
        self.head = QLabel(app.t("Вышла новая версия DLauncher: {v}", v=version))
        self.head.setProperty("kind", "h3")
        self.head.setWordWrap(True)
        self.body.addWidget(self.head)
        notes = (notes or "").strip()
        if notes:
            self.body.addWidget(QLabel(app.t("Что изменилось:")))
            n = QLabel(notes)
            n.setWordWrap(True)
            n.setProperty("kind", "muted")
            self.body.addWidget(n)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()
        self.body.addWidget(self.bar)
        self.btn_later = self.add_button("Позже", "ghost", self.reject)
        self.btn_go = self.add_button("Скачать", "primary", self._download, close=False)
        app.event.connect(self._on_event)

    def _download(self) -> None:
        self._started = True
        self.btn_go.setEnabled(False)
        self.btn_later.setEnabled(False)
        self.bar.show()
        self.status.setText(self.app.t("Скачиваю обновление: {p}%", p=0))

        def fail(m):
            self.status.setText(self.app.t("Ошибка обновления: {m}", m=m))
            self.btn_go.setEnabled(True)
            self.btn_later.setEnabled(True)

        def ok(r):
            if isinstance(r, dict) and not r.get("ok"):
                fail(self.app.t(str(r.get("error") or "?")))
        self.app.call("update:download", None, ok, fail)

    def _on_event(self, ch: str, payload) -> None:
        if not self._started or ch != "update:status" or not isinstance(payload, dict):
            return
        st = payload.get("state")
        if st == "downloading":
            pc = int(payload.get("percent") or 0)
            self.bar.setValue(pc)
            self.status.setText(self.app.t("Скачиваю обновление: {p}%", p=pc))
        elif st == "ready":
            self.bar.setValue(100)
            self.status.setText(self.app.t("Обновление скачано. Лаунчер перезапустится..."))
            self.app.call("update:install", None, self._installed, lambda m: self.status.setText(m))

    def _installed(self, r) -> None:
        if isinstance(r, dict) and not r.get("ok"):
            self.status.setText(self.app.t(str(r.get("error") or "?")))
            self.btn_later.setEnabled(True)
