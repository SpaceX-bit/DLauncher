"""Вкладка «Моды»: поиск и установка модов, ресурспаков, шейдеров и сборок (Modrinth / CurseForge)."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .. import i18n
from ..dialogs.shared import KIND_LABEL, Segment, fmt_num
from ..widgets import Card, RemoteIcon, VScroll, button, label
from ._profile_util import loader_name, profile_label

i18n.register({
    "Моды": "Mods",
    "Сборки": "Modpacks",
    "Ресурспаки": "Resource packs",
    "Шейдеры": "Shaders",
    "Поиск...": "Search...",
    "Тип": "Type",
    "Источник": "Source",
    "Подбор под профиль": "Matched to profile",
    "Показываются только моды под версию игры и загрузчик выбранного профиля.": "Only mods for the game version and loader of the selected profile are shown.",
    "Найти": "Search",
    "Установить": "Install",
    "Версии": "Versions",
    "Ещё": "More",
    "Оптимизация": "Optimize",
    "Ищу...": "Searching...",
    "Ничего не найдено": "Nothing found",
    "Профиль: {p}": "Profile: {p}",
    "Сначала создай профиль на вкладке «Профили».": "Create a profile on the Profiles tab first.",
    "Установлено: {f}": "Installed: {f}",
    "Установлено: {f} (+{n} зависимостей)": "Installed: {f} (+{n} dependencies)",
    "{n} загрузок": "{n} downloads",
    "Установка сборки...": "Installing modpack...",
    "Сборка установлена: профиль «{n}»": "Modpack installed: profile “{n}”",
})

KINDS = [("mod", "Моды"), ("modpack", "Сборки"), ("resourcepack", "Ресурспаки"), ("shader", "Шейдеры")]


class ModsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.kind = "mod"
        self.source = "modrinth"
        self.offset = 0
        self.total = 0
        self.busy = False
        self._more_btn = None

        # слева панель фильтров (тип, источник, профиль), справа поиск и результаты — как каталог в 16Launcher
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        side = QFrame()
        side.setProperty("kind", "card")
        side.setFixedWidth(210)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 12, 12)
        sl.setSpacing(6)
        sl.addWidget(label(app, "Тип", "h3"))
        self.kind_seg = Segment(app, KINDS, self.kind, self.set_kind, vertical=True)
        sl.addWidget(self.kind_seg)
        sl.addSpacing(6)
        sl.addWidget(label(app, "Источник", "h3"))
        self.src_seg = Segment(app, [("modrinth", "Modrinth"), ("curseforge", "CurseForge")], self.source,
                               self._set_source, translate=False, vertical=True)
        sl.addWidget(self.src_seg)
        sl.addSpacing(6)
        sl.addWidget(label(app, "Подбор под профиль", "h3"))
        self.prof = label(app, None, "muted", wrap=True)
        sl.addWidget(self.prof)
        sl.addWidget(label(app, "Показываются только моды под версию игры и загрузчик выбранного профиля.", "muted", wrap=True))
        sl.addStretch(1)
        sl.addWidget(button(app, "Оптимизация", "ghost", self._optimize))
        outer.addWidget(side)

        right = QVBoxLayout()
        right.setSpacing(10)
        outer.addLayout(right, 1)
        row = QHBoxLayout()
        self.query = QLineEdit()
        app.bind(self.query, "Поиск...", "placeholder")
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(button(app, "Найти", "primary", self.search))
        right.addLayout(row)
        self.status = label(app, None, "muted", wrap=True)
        right.addWidget(self.status)
        self.scroll = VScroll()
        right.addWidget(self.scroll, 1)
        app.profiles_changed.connect(self._profile_changed)
        app.event.connect(self._event)
        self._fill_profile()

    # ----- публичное
    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.kind_seg.select(kind, notify=False)
        self.search()

    def search_for(self, query: str) -> None:
        self.kind = "mod"
        self.kind_seg.select("mod", notify=False)
        self.query.setText(query)
        self.search()

    def on_show(self) -> None:
        self._fill_profile()
        if not self.scroll.lay.count():
            self.search()

    # ----- внутреннее
    def _set_source(self, s: str) -> None:
        self.source = s
        self.search()

    def _fill_profile(self) -> None:
        p = self.app.current_profile()
        self.prof.setText(self.app.t("Профиль: {p}", p=profile_label(p)) if p else self.app.t("Сначала создай профиль на вкладке «Профили»."))

    def _profile_changed(self) -> None:
        self._fill_profile()

    def _event(self, ch, p) -> None:
        if ch == "pack:progress" and isinstance(p, dict) and p.get("text"):
            self.status.setText(self.app.t(str(p["text"])))

    def search(self, more: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        if not more:
            self.offset = 0
            self.scroll.clear()
        self.status.setText(self.app.t("Ищу..."))
        p = self.app.current_profile()
        payload = {"source": self.source, "query": self.query.text().strip(), "kind": self.kind, "offset": self.offset}
        if p and self.kind != "modpack":
            payload.update(mc=p["version"], loader=p.get("loader"))

        def ok(r):
            self.busy = False
            if not (r or {}).get("ok"):
                self.status.setText(self.app.t((r or {}).get("error") or "?"))
                return
            self.status.setText("")
            self.total = r.get("total") or 0
            if self._more_btn is not None:
                self._more_btn.setParent(None)
                self._more_btn = None
            # убрать растяжку в конце перед добавлением
            items = r.get("items") or []
            if not items and not more:
                self.status.setText(self.app.t("Ничего не найдено"))
            for it in items:
                self.scroll.lay.addWidget(self._card(it))
            self.offset += len(items)
            if items and self.offset < self.total:
                self._more_btn = button(self.app, "Ещё", "ghost", lambda: self.search(True))
                self.scroll.lay.addWidget(self._more_btn)
            self.scroll.lay.addStretch(1)

        def err(m):
            self.busy = False
            self.status.setText(m)
        self.app.call("mods:search", payload, ok, err)

    def _card(self, it: dict) -> QWidget:
        app = self.app
        c = Card(layout="h", margins=(12, 10, 12, 10), spacing=12)
        c.lay.addWidget(RemoteIcon(app, it.get("icon"), 56, it.get("title") or "?"))
        mid = QVBoxLayout()
        mid.setSpacing(2)
        t = QLabel(str(it.get("title") or ""))
        t.setProperty("kind", "h2")
        mid.addWidget(t)
        meta = " · ".join(x for x in [it.get("author"), app.t("{n} загрузок", n=fmt_num(app, it.get("downloads")))] if x)
        m = QLabel(meta)
        m.setProperty("kind", "muted")
        mid.addWidget(m)
        d = QLabel(str(it.get("description") or "")[:220])
        d.setWordWrap(True)
        mid.addWidget(d)
        c.lay.addLayout(mid, 1)
        col = QVBoxLayout()
        col.addWidget(button(app, "Установить", "primary", lambda it=it: self._install(it)))
        if self.kind != "modpack":
            col.addWidget(button(app, "Версии", "small", lambda it=it: self._versions(it)))
        col.addStretch(1)
        c.lay.addLayout(col)
        return c

    def _need_profile(self):
        p = self.app.current_profile()
        if not p and self.kind != "modpack":
            self.app.toast("Сначала создай профиль на вкладке «Профили».", "warn")
        return p

    def _install(self, it: dict, version_id: str | None = None) -> None:
        if self.kind == "modpack":
            if version_id is None:
                return self._pick(it)
            return self._install_pack(it, version_id)
        p = self._need_profile()
        if not p:
            return
        payload = {"source": self.source, "id": it["id"], "kind": self.kind, "profileId": p["id"]}
        if version_id:
            payload["versionId"] = version_id
        self.status.setText(self.app.t("Установка..."))

        def ok(r):
            if not (r or {}).get("ok"):
                self.status.setText("")
                return self.app.toast((r or {}).get("error") or "?", "err")
            self.status.setText("")
            extra = r.get("extra") or 0
            self.app.toast(self.app.t("Установлено: {f} (+{n} зависимостей)", f=r.get("filename"), n=extra) if extra
                           else self.app.t("Установлено: {f}", f=r.get("filename")), "ok")
            self.app.refresh_profiles()
        self.app.call("mods:install", payload, ok, lambda m: (self.status.setText(""), self.app.toast(m, "err")))

    def _pick(self, it: dict) -> None:
        from ..dialogs.versions import pick_version
        pick_version(self.app, it, self.source, self.kind, lambda vid: self._install(it, vid or ""))

    def _versions(self, it: dict) -> None:
        if not self._need_profile():
            return
        from ..dialogs.versions import pick_version
        pick_version(self.app, it, self.source, self.kind, lambda vid: self._install(it, vid or ""))

    def _install_pack(self, it: dict, version_id: str) -> None:
        self.status.setText(self.app.t("Установка сборки..."))

        def ok(r):
            if not (r or {}).get("ok"):
                self.status.setText("")
                return self.app.toast((r or {}).get("error") or "?", "err")
            name = (r.get("profile") or {}).get("name") or it.get("title")
            self.status.setText(self.app.t("Сборка установлена: профиль «{n}»", n=name))
            self.app.toast(self.app.t("Сборка установлена: профиль «{n}»", n=name), "ok")
            self.app.refresh_profiles()
        payload = {"source": self.source, "id": it["id"], "title": it.get("title")}
        if version_id:
            payload["versionId"] = version_id
        self.app.call("pack:install", payload, ok, lambda m: (self.status.setText(""), self.app.toast(m, "err")))

    def _optimize(self) -> None:
        p = self.app.current_profile()
        if not p:
            return self.app.toast("Сначала создай профиль на вкладке «Профили».", "warn")
        from ..dialogs.optimize import OptimizeDialog
        OptimizeDialog(self.app, p).exec()

    def retranslate(self) -> None:
        self._fill_profile()

    def selftest(self) -> None:
        from ..dialogs.optimize import OptimizeDialog
        p = self.app.current_profile()
        if p:
            OptimizeDialog(self.app, p)
