"""Проверка совместимости модов: окно с результатом и проверка перед запуском игры."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

from .. import i18n
from ..widgets import Card, Modal, VScroll, button, label

i18n.register({
    "Совместимость модов": "Mod compatibility",
    "Проверяю моды...": "Checking mods...",
    "Ошибка": "Error",
    "Предупреждение": "Warning",
    "Заметка": "Note",
    "Есть ошибки": "Errors found",
    "Есть предупреждения": "Warnings found",
    "Всё в порядке": "All good",
    "Проверено модов: {n}": "Mods checked: {n}",
    "Выключено: {n}": "Disabled: {n}",
    "Ошибок: {n}": "Errors: {n}",
    "Предупреждений: {n}": "Warnings: {n}",
    "Проверка перед запуском": "Pre-launch check",
    "Найдены проблемы с модами. Игра, скорее всего, не запустится.": "Mod problems were found. The game will most likely not start.",
    "Всё равно запустить": "Launch anyway",
    "Исправить": "Fix",
    "Отмена": "Cancel",
    "Закрыть": "Close",
    "Не удалось проверить моды": "Could not check the mods",
})

LVL_KIND = {"error": "err", "warn": "warn", "info": "muted"}
LVL_TEXT = {"error": "Ошибка", "warn": "Предупреждение", "info": "Заметка"}
_ACCEPTED: set[str] = set()
_STATE = {"busy": False}


def fix_problem(app, profile_id: str, fix: dict, after) -> None:
    """Применить кнопку исправления: выключить мод или перейти к поиску."""
    if fix.get("type") == "search":
        app.show_page("mods")
        page = getattr(getattr(app, "window", None), "pages", {}).get("mods")
        fn = getattr(page, "search_for", None)
        if callable(fn):
            fn(fix.get("query") or "")
        return
    if fix.get("type") == "disable":
        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                after()
            else:
                app.toast((r or {}).get("error") or "Не удалось выключить мод", "err")
        app.call("installed:toggle", {"profileId": profile_id, "file": fix.get("file"), "kind": "mod"}, ok,
                 lambda m: app.toast(m, "err"))


def problem_card(app, pr: dict, profile_id: str | None = None, after=None, close=None) -> Card:
    lvl = pr.get("level") if pr.get("level") in LVL_TEXT else "info"
    c = Card("soft", spacing=6)
    head = label(app, LVL_TEXT[lvl], LVL_KIND[lvl])
    c.lay.addWidget(head)
    t = QLabel(str(pr.get("text", "")))
    t.setWordWrap(True)
    c.lay.addWidget(t)
    if after is not None and profile_id:
        for f in pr.get("fixes") or []:
            if isinstance(f, dict) and f.get("type") in ("disable", "search"):
                b = button(app, "", "small")
                b.setText(str(f.get("label") or ""))
                b.clicked.connect(lambda _=False, f=f: (fix_problem(app, profile_id, f, after), close() if close and f.get("type") == "search" else None))
                c.lay.addWidget(b)
    return c


def summary_text(app, r: dict) -> tuple[str, str]:
    s = r.get("summary") or {}
    errors, warnings = s.get("errors", 0), s.get("warnings", 0)
    if errors:
        head, kind = "Есть ошибки", "err"
    elif warnings:
        head, kind = "Есть предупреждения", "warn"
    else:
        head, kind = "Всё в порядке", "ok"
    parts = [app.t("Проверено модов: {n}", n=r.get("scanned", 0))]
    if r.get("disabled"):
        parts.append(app.t("Выключено: {n}", n=r["disabled"]))
    if errors:
        parts.append(app.t("Ошибок: {n}", n=errors))
    if warnings:
        parts.append(app.t("Предупреждений: {n}", n=warnings))
    return head, kind + "|" + " · ".join(parts)


class CompatDialog(Modal):
    """Окно проверки для текущего профиля (кнопка на вкладке «Установлено»)."""

    def __init__(self, app, profile: dict, on_changed=None, parent=None):
        super().__init__(app, "Совместимость модов", width=680, height=460, parent=parent)
        self.profile = profile
        self.on_changed = on_changed
        self.head = label(app, None, None)
        self.body.addWidget(self.head)
        self.meta = label(app, None, "muted", wrap=True)
        self.body.addWidget(self.meta)
        self.scroll = VScroll()
        self.body.addWidget(self.scroll, 1)
        self.add_button("Закрыть", "primary", close=True)
        self.run()

    def run(self) -> None:
        self.scroll.clear()
        self.scroll.lay.addWidget(label(self.app, "Проверяю моды...", "muted"))
        self.app.call("compat:check", {"profileId": self.profile["id"]}, self._ok,
                      lambda m: self._msg(m))

    def _msg(self, text: str) -> None:
        self.scroll.clear()
        lb = label(self.app, None, "muted", wrap=True)
        lb.setText(self.app.t(text))
        self.scroll.lay.addWidget(lb)

    def _after_fix(self) -> None:
        if self.on_changed:
            self.on_changed()
        self.run()

    def _ok(self, r) -> None:
        if not isinstance(r, dict) or not r.get("ok"):
            return self._msg((r or {}).get("error") or "Не удалось проверить моды")
        head, rest = summary_text(self.app, r)
        kind, meta = rest.split("|", 1)
        self.head.setText(self.app.t(head))
        self.head.setProperty("kind", kind)
        self.head.style().unpolish(self.head)
        self.head.style().polish(self.head)
        self.meta.setText(meta)
        self.scroll.clear()
        for pr in r.get("problems") or []:
            self.scroll.lay.addWidget(problem_card(self.app, pr, self.profile["id"], self._after_fix, self.close))
        self.scroll.lay.addStretch(1)


class PreLaunchDialog(Modal):
    def __init__(self, app, profile: dict, result: dict, errs: list, sig: str, proceed, parent=None):
        super().__init__(app, "Проверка перед запуском", width=640, height=420, parent=parent)
        self.choice = None
        self.body.addWidget(label(app, "Найдены проблемы с модами. Игра, скорее всего, не запустится.", "muted", wrap=True))
        sc = VScroll()
        for pr in errs[:8]:
            sc.lay.addWidget(problem_card(app, pr))
        sc.lay.addStretch(1)
        self.body.addWidget(sc, 1)
        self.add_button("Отмена", "ghost", self.reject)
        self.add_button("Всё равно запустить", "danger", lambda: self._go(sig, proceed))
        self.add_button("Исправить", "primary", lambda: self._fix())

    def _go(self, sig, proceed):
        _ACCEPTED.add(sig)
        self.accept()
        proceed()

    def _fix(self):
        self.accept()
        self.app.show_page("installed")
        page = getattr(getattr(self.app, "window", None), "pages", {}).get("installed")
        fn = getattr(page, "run_compat", None)
        if callable(fn):
            fn()


def pre_launch_check(app, profile: dict, proceed) -> None:
    """Перед запуском: если включена проверка и есть ошибки — спросить. Никогда не мешает запуску при сбоях."""
    if _STATE["busy"]:
        return
    if not app.settings.get("compatCheck", True) or not profile or profile.get("loader") == "vanilla":
        return proceed()
    _STATE["busy"] = True
    done = {"v": False}

    def finish(r):
        if done["v"]:
            return
        done["v"] = True
        _STATE["busy"] = False
        try:
            if not isinstance(r, dict) or not r.get("ok") or not (r.get("summary") or {}).get("errors"):
                return proceed()
            errs = [x for x in r.get("problems") or [] if x.get("level") == "error"]
            sig = profile["id"] + "|" + ",".join(f"{x.get('code')}{x.get('file')}" for x in errs)
            if sig in _ACCEPTED:
                return proceed()
            PreLaunchDialog(app, profile, r, errs, sig, proceed).exec()
        except Exception as e:  # noqa: BLE001
            app.ctx.diag(f"pre_launch_check: {e}")
            proceed()

    app.call("compat:check", {"profileId": profile["id"]}, finish, lambda m: finish(None))
    QTimer.singleShot(12000, lambda: finish(None))
