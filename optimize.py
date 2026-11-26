"""Оптимизация: установка набора модов (Sodium, Lithium и т.п.) в текущий профиль. opt:list / opt:install."""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit

from .. import i18n
from ..widgets import Modal, label

i18n.register({
    "Оптимизация модами": "Optimization mods",
    "Будут установлены моды для повышения FPS:": "These FPS-boosting mods will be installed:",
    "Установить всё": "Install all",
    "Закрыть": "Close",
    "Установка...": "Installing...",
    "Для Vanilla оптимизация недоступна": "Optimization is not available for Vanilla",
    "Готово: установлено {n} (Modrinth: {m}, CurseForge: {c})": "Done: installed {n} (Modrinth: {m}, CurseForge: {c})",
    "Пропущено: {n}": "Skipped: {n}",
    "Ошибок: {n}": "Errors: {n}",
    "Чтобы искать и на CurseForge, добавь API-ключ в Настройках.": "To search CurseForge as well, add an API key in Settings.",
})


class OptimizeDialog(Modal):
    def __init__(self, app, profile: dict, parent=None):
        super().__init__(app, "Оптимизация модами", width=560, height=420, parent=parent)
        self.profile = profile
        self.body.addWidget(label(app, "Будут установлены моды для повышения FPS:", "muted", wrap=True))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.body.addWidget(self.log, 1)
        self.summary = label(app, None, "accent", wrap=True)
        self.body.addWidget(self.summary)
        self.btn = self.add_button("Установить всё", "primary", self._go)
        self.add_button("Закрыть", "ghost", close=True)
        app.event.connect(self._event)
        app.call("opt:list", profile.get("loader"), self._list, lambda m: self.log.setPlainText(m))

    def _list(self, items) -> None:
        if not items:
            self.log.setPlainText(self.app.t("Для Vanilla оптимизация недоступна"))
            self.btn.setEnabled(False)
            return
        self.log.setPlainText("\n".join(f"• {i['name']} — {i['desc']}" for i in items))

    def _event(self, ch, p) -> None:
        if ch == "opt:progress" and isinstance(p, dict):
            mark = {"ok": "✓", "fail": "✗", "skip": "–"}.get(p.get("status"), "·")
            self.log.appendPlainText(f"{mark} {p.get('slug')}: {p.get('detail', '')}")

    def _go(self) -> None:
        self.btn.setEnabled(False)
        self.log.clear()
        self.summary.setText(self.app.t("Установка..."))

        def ok(r):
            self.btn.setEnabled(True)
            if not (r or {}).get("ok"):
                self.summary.setText((r or {}).get("error") or "?")
                return
            by = r.get("bySource") or {}
            t = self.app.t("Готово: установлено {n} (Modrinth: {m}, CurseForge: {c})", n=r.get("installed", 0),
                           m=by.get("modrinth", 0), c=by.get("curseforge", 0))
            if r.get("skipped"):
                t += ". " + self.app.t("Пропущено: {n}", n=r["skipped"])
            if r.get("failed"):
                t += ". " + self.app.t("Ошибок: {n}", n=r["failed"])
            if r.get("needKey") and r.get("skipped"):
                t += ". " + self.app.t("Чтобы искать и на CurseForge, добавь API-ключ в Настройках.")
            self.summary.setText(t)
        self.app.call("opt:install", {"profileId": self.profile["id"]}, ok, lambda m: (self.btn.setEnabled(True), self.summary.setText(m)))
