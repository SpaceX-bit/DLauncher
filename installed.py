"""Вкладка «Установлено»: моды, ресурспаки и шейдеры профиля — выключить, удалить, обновить, проверить совместимость."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .. import i18n
from ..dialogs.shared import INST_DIR, Segment, fmt_size, strip_ext
from ..widgets import Card, RemoteIcon, VScroll, button, label
from ._profile_util import profile_label

i18n.register({
    "Установлено": "Installed",
    "Моды": "Mods",
    "Ресурспаки": "Resource packs",
    "Шейдеры": "Shaders",
    "Фильтр...": "Filter...",
    "Проверить совместимость": "Check compatibility",
    "Обновить все": "Update all",
    "Открыть папку": "Open folder",
    "Выключить": "Disable",
    "Включить": "Enable",
    "Удалить": "Delete",
    "Обновить до {v}": "Update to {v}",
    "Выключен": "Disabled",
    "Загрузка...": "Loading...",
    "Здесь пока пусто": "Nothing here yet",
    "Обновлений нет": "No updates",
    "Обновлено: {n}": "Updated: {n}",
    "Удалить «{f}»?": "Delete “{f}”?",
    "Профиль: {p}": "Profile: {p}",
    "Сначала создай профиль на вкладке «Профили».": "Create a profile on the Profiles tab first.",
    "Доступны обновления: {n}": "Updates available: {n}",
    "Файлов: {n}": "Files: {n}",
})

KINDS = [("mod", "Моды"), ("resourcepack", "Ресурспаки"), ("shader", "Шейдеры")]


class InstalledPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.kind = "mod"
        self.items: list[dict] = []
        self._token = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(label(app, "Установлено", "h2"))
        top = QHBoxLayout()
        self.seg = Segment(app, KINDS, self.kind, self._set_kind)
        top.addWidget(self.seg)
        top.addStretch(1)
        self.btn_compat = button(app, "Проверить совместимость", "ghost", self.run_compat)
        top.addWidget(self.btn_compat)
        self.btn_all = button(app, "Обновить все", "ghost", self._update_all)
        self.btn_all.hide()
        top.addWidget(self.btn_all)
        self.btn_rb = button(app, "Откатить", "ghost", self._rollback)
        self.btn_rb.hide()
        top.addWidget(self.btn_rb)
        top.addWidget(button(app, "Открыть папку", "ghost", self._folder))
        root.addLayout(top)
        self.filter = QLineEdit()
        app.bind(self.filter, "Фильтр...", "placeholder")
        self.filter.textChanged.connect(self._draw)
        root.addWidget(self.filter)
        self.info = label(app, None, "muted", wrap=True)
        root.addWidget(self.info)
        self.scroll = VScroll()
        root.addWidget(self.scroll, 1)
        app.profiles_changed.connect(self.load)

    def on_show(self) -> None:
        self.load()

    def _set_kind(self, k: str) -> None:
        self.kind = k
        self.btn_compat.setVisible(k == "mod")
        self.load()

    def _sync_rollback(self) -> None:
        p = self._profile()
        self.btn_rb.hide()
        if not p or self.kind != "mod":
            return

        def ok(r):
            n = int((r or {}).get("count") or 0)
            self.btn_rb.setVisible(n > 0)
            if n:
                self.btn_rb.setText(self.app.t("Откатить обновление ({n})", n=n))
        self.app.call("installed:rollback_info", {"profileId": p["id"]}, ok, lambda m: None)

    def _rollback(self) -> None:
        p = self._profile()
        if not p or not self.app.confirm("Откатить последнее обновление модов? Новые версии удалятся, старые вернутся.", "Откатить"):
            return

        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                self.app.toast(self.app.t("Откат выполнен: вернули {n}", n=int(r.get("restored") or 0)), "ok")
            else:
                self.app.toast(self.app.t(str((r or {}).get("error") or "?")), "err")
            self.load()
        self.app.call("installed:rollback", {"profileId": p["id"]}, ok, lambda m: self.app.toast(m, "err"))

    def _profile(self):
        return self.app.current_profile()

    def load(self) -> None:
        p = self._profile()
        self.scroll.clear()
        if not p:
            self.info.setText(self.app.t("Сначала создай профиль на вкладке «Профили»."))
            self.items = []
            return
        self._token += 1
        token = self._token
        self.info.setText(self.app.t("Загрузка..."))
        self._sync_rollback()

        def quick(r):
            if token != self._token or not (r or {}).get("ok"):
                return
            self.items = r["items"]
            self._draw()
            self.app.call("installed:list", {"profileId": p["id"], "check": True, "kind": self.kind}, full, lambda m: None)

        def full(r):
            if token != self._token or not (r or {}).get("ok"):
                return
            self.items = r["items"]
            self._draw()

        self.app.call("installed:list", {"profileId": p["id"], "check": False, "kind": self.kind}, quick,
                      lambda m: self.info.setText(m))

    def _draw(self, *_a) -> None:
        p = self._profile()
        self.scroll.clear()
        q = self.filter.text().strip().lower()
        shown = [i for i in self.items if not q or q in (i.get("title") or i["file"]).lower() or q in i["file"].lower()]
        upd = [i for i in self.items if i.get("update")]
        self.btn_all.setVisible(bool(upd))
        head = self.app.t("Профиль: {p}", p=profile_label(p)) if p else ""
        head += "  ·  " + self.app.t("Файлов: {n}", n=len(self.items))
        if upd:
            head += "  ·  " + self.app.t("Доступны обновления: {n}", n=len(upd))
        self.info.setText(head)
        if not shown:
            self.scroll.lay.addWidget(label(self.app, "Здесь пока пусто", "muted"))
        for it in shown:
            self.scroll.lay.addWidget(self._row(it))
        self.scroll.lay.addStretch(1)

    def _row(self, it: dict) -> QWidget:
        app = self.app
        c = Card("build", layout="h", margins=(12, 8, 12, 8), spacing=10)
        title = it.get("title") or strip_ext(it["file"])
        c.lay.addWidget(RemoteIcon(app, it.get("icon"), 40, title))
        mid = QVBoxLayout()
        mid.setSpacing(1)
        t = QLabel(title)
        t.setProperty("kind", "accent" if it.get("enabled") else "muted")
        mid.addWidget(t)
        meta = " · ".join(x for x in [it.get("version"), fmt_size(it.get("size")), None if it.get("enabled") else app.t("Выключен")] if x)
        m = QLabel(meta)
        m.setProperty("kind", "muted")
        mid.addWidget(m)
        c.lay.addLayout(mid, 1)
        if it.get("update"):
            b = button(app, "Установить", "primary", lambda it=it: self._update(it))
            b.setText(app.t("Обновить до {v}", v=it["update"].get("version", "")))
            c.lay.addWidget(b)
        c.lay.addWidget(button(app, "Выключить" if it.get("enabled") else "Включить", "small", lambda it=it: self._toggle(it)))
        c.lay.addWidget(button(app, "Удалить", "danger", lambda it=it: self._delete(it)))
        return c

    def _args(self, it: dict) -> dict:
        return {"profileId": self._profile()["id"], "file": it["file"], "kind": self.kind}

    def _after(self, r) -> None:
        if (r or {}).get("ok"):
            self.load()
            self.app.refresh_profiles()
        else:
            self.app.toast((r or {}).get("error") or "?", "err")

    def _toggle(self, it: dict) -> None:
        self.app.call("installed:toggle", self._args(it), self._after, lambda m: self.app.toast(m, "err"))

    def _delete(self, it: dict) -> None:
        if self.app.confirm("Удалить «{f}»?", "Удалить", danger=True, f=it["file"]):
            self.app.call("installed:delete", self._args(it), self._after, lambda m: self.app.toast(m, "err"))

    def _update(self, it: dict, then=None) -> None:
        a = self._args(it)
        a.update(url=it["update"]["url"], filename=it["update"]["filename"])

        def ok(r):
            if then:
                then(r)
            else:
                self._after(r)
        self.app.call("installed:update", a, ok, lambda m: self.app.toast(m, "err"))

    def _update_all(self) -> None:
        todo = [i for i in self.items if i.get("update")]
        done = {"n": 0, "left": len(todo)}
        if not todo:
            return self.app.toast("Обновлений нет", "info")

        def one(r):
            done["left"] -= 1
            if (r or {}).get("ok"):
                done["n"] += 1
            if done["left"] == 0:
                self.app.toast(self.app.t("Обновлено: {n}", n=done["n"]), "ok")
                self.load()
        for it in todo:
            self._update(it, one)

    def _folder(self) -> None:
        p = self._profile()
        if p:
            self.app.call("folder:open", {"which": {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}[self.kind],
                                          "profileId": p["id"]}, None, lambda m: self.app.toast(m, "err"))

    def run_compat(self) -> None:
        p = self._profile()
        if not p:
            return self.app.toast("Сначала создай профиль на вкладке «Профили».", "warn")
        from ..dialogs.compat import CompatDialog
        CompatDialog(self.app, p, on_changed=self.load).exec()

    def retranslate(self) -> None:
        self._draw()

    def selftest(self) -> None:
        p = self._profile()
        if p:
            from ..dialogs.compat import CompatDialog
            CompatDialog(self.app, p)
