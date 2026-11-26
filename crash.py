"""Окно «Почему игра вылетела»: crash:analyze -> понятные причины и кнопки действий."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from .. import i18n
from ..widgets import Card, Modal, VScroll, clear_layout, label

i18n.register({
    "Игра завершилась с ошибкой": "The game crashed",
    "Разбираю причину...": "Analysing the cause...",
    "Журналов для разбора пока нет.": "There are no logs to analyse yet.",
    "Открыть отчёт о вылете": "Open crash report",
    "Открыть консоль": "Open console",
    "Открыть настройки": "Open settings",
    "Открыть «Установлено»": "Open “Installed”",
    "Закрыть": "Close",
    "Код выхода: {c}": "Exit code: {c}",
})


class CrashDialog(Modal):
    def __init__(self, app, profile_id, code=None, parent=None):
        super().__init__(app, "Игра завершилась с ошибкой", width=640, height=420, parent=parent)
        self.profile_id = profile_id
        self.code = code
        self.setModal(False)
        self.summary = label(app, None, "muted", wrap=True, selectable=True)
        self.body.addWidget(self.summary)
        self.scroll = VScroll()
        self.body.addWidget(self.scroll, 1)
        self.btn_open = self.add_button("Открыть отчёт о вылете", "ghost", self._open_report)
        self.btn_open.hide()
        self.add_button("Открыть консоль", "ghost", self._console)
        self.add_button("Закрыть", "primary", close=True)
        self.scroll.lay.addWidget(label(app, "Разбираю причину...", "muted"))
        app.call("crash:analyze", {"profileId": profile_id, "code": code}, self._ok, lambda m: self._fail(m))

    def _fail(self, msg):
        self.scroll.clear()
        lb = label(self.app, None, "err", wrap=True)
        lb.setText(msg)
        self.scroll.lay.addWidget(lb)

    def _ok(self, r):
        self.scroll.clear()
        if not isinstance(r, dict) or not r.get("ok"):
            return self._fail((r or {}).get("error") or "?")
        if r.get("empty"):
            self.scroll.lay.addWidget(label(self.app, "Журналов для разбора пока нет.", "muted"))
            return
        s = r.get("summary") or ""
        if self.code is not None:
            s = (self.app.t("Код выхода: {c}", c=self.code) + (" — " + s if s else ""))
        self.summary.setText(s)
        self.btn_open.setVisible(bool(r.get("hasReport")))
        for f in r.get("findings") or []:
            c = Card("soft", spacing=4)
            t = QLabel(f.get("title", ""))
            t.setProperty("kind", "accent")
            t.setWordWrap(True)
            c.lay.addWidget(t)
            tx = QLabel(f.get("text", ""))
            tx.setWordWrap(True)
            tx.setTextInteractionFlags(tx.textInteractionFlags() | 1)
            c.lay.addWidget(tx)
            act = f.get("action")
            if act in ("ram", "java"):
                from ..widgets import button
                c.lay.addWidget(button(self.app, "Открыть настройки", "small", lambda: (self.app.show_page("settings"), self.close())))
            elif f.get("mods"):
                from ..widgets import button
                c.lay.addWidget(button(self.app, "Открыть «Установлено»", "small", lambda: (self.app.show_page("installed"), self.close())))
            self.scroll.lay.addWidget(c)
        self.scroll.lay.addStretch(1)

    def _open_report(self):
        self.app.call("crash:open", {"profileId": self.profile_id}, lambda r: None if (r or {}).get("ok") else self.app.toast((r or {}).get("error", "?"), "err"), lambda m: self.app.toast(m, "err"))

    def _console(self):
        from .console import ConsoleDialog
        d = ConsoleDialog(self.app)
        d.show()
        self._con = d
