"""Вкладка «Профили»: список, создание, настройки профиля (память, JVM, окно, Java, серверы), экспорт/импорт."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QSlider, QVBoxLayout, QWidget)

from .. import i18n
from ...core.base import PROFILE_COLORS, PROFILE_GLYPHS
from ..dialogs import extras
from ..buildcard import BuildCard, filter_profiles, group_profiles, tile_look
from ..widgets import Card, Modal, VScroll, button, clear_layout, label
from ._profile_util import NAMES, TYPE_LABEL, fmt_date, get_page, loader_name, profile_label

i18n.register({
    "Профили": "Profiles",
    "Мои сборки": "My builds",
    "Сборка сохранена: {f} (модов по ссылкам: {a}, вложено: {b})": "Build saved: {f} (mods by link: {a}, bundled: {b})",
    "Сборка экспортирована в .mrpack": "Build exported to .mrpack",
    "Поиск сборки": "Search builds",
    "Импорт": "Import",
    "Ничего не найдено": "Nothing found",
    "Играть": "Play",
    "Создать профиль": "Create profile",
    "Импорт из других лаунчеров": "Import from other launchers",
    "Импорт .mrpack": "Import .mrpack",
    "Экспорт .mrpack": "Export .mrpack",
    "Скачать сборку": "Download a modpack",
    "Выбрать": "Select",
    "Настройки": "Settings",
    "Удалить": "Delete",
    "Выбран": "Selected",
    "Модов: {n}": "Mods: {n}",
    "Название": "Name",
    "Версия Minecraft": "Minecraft version",
    "Тип версий": "Version type",
    "Поиск версии": "Search version",
    "Загрузчик": "Loader",
    "Версия загрузчика": "Loader version",
    "Создать": "Create",
    "Отмена": "Cancel",
    "Сохранить": "Save",
    "Память для этого профиля": "Memory for this profile",
    "Как в настройках": "Same as in settings",
    "Аргументы Java": "Java arguments",
    "Размер окна (ширина × высота)": "Window size (width × height)",
    "На весь экран": "Fullscreen",
    "Путь к Java для профиля": "Java path for this profile",
    "Серверы": "Servers",
    "Адрес сервера (host:port)": "Server address (host:port)",
    "Название (необязательно)": "Name (optional)",
    "Добавить": "Add",
    "Из servers.dat": "From servers.dat",
    "Проверить": "Ping",
    "Открыть папку": "Open folder",
    "Моды": "Mods",
    "Сохранения": "Saves",
    "Удалить профиль «{n}»? Файлы профиля (моды, миры) тоже будут удалены.": "Delete profile “{n}”? Its files (mods, worlds) will be deleted too.",
    "Загрузка версий...": "Loading versions...",
    "Загрузчик не нужен": "No loader needed",
    "Релизы": "Releases",
    "Снапшоты": "Snapshots",
    "Старые": "Old",
    "онлайн": "online",
    "офлайн": "offline",
    "Профиль сохранён": "Profile saved",
    "Профиль создан": "Profile created",
    "Игроков: {o}/{m}": "Players: {o}/{m}",
    "Подобрать": "Suggest",
    "Подобрать память под сборку": "Suggest memory for this build",
    "Цвет и значок": "Color and icon",
    "Группа": "Group",
    "Группа (например: Выживание)": "Group (e.g. Survival)",
    "Авто": "Auto",
    "В избранное": "Favorite",
    "★ В избранное": "★ Favorite",
    "Без группы": "No group",
    "Выбери сервер в списке": "Pick a server in the list",
    "Рекомендуем {n} GB: {r}": "Suggested {n} GB: {r}",
    "чистая игра без модов": "plain game without mods",
    "немного модов": "a few mods",
    "средняя сборка": "a medium build",
    "большая сборка": "a big build",
    "очень большая сборка": "a very big build",
    "ограничено половиной оперативной памяти": "limited to half of your RAM",
})

TYPE_FILTERS = [("release", "Релизы"), ("snapshot", "Снапшоты"), ("old", "Старые")]


def _type_ok(kind: str, t: str) -> bool:
    if kind == "old":
        return t in ("old_beta", "old_alpha")
    return t == kind


def filter_versions(versions: list[dict], kind: str, query: str) -> list[dict]:
    q = (query or "").strip().lower()
    return [v for v in versions if _type_ok(kind, v.get("type", "")) and (not q or q in v["id"].lower())]


class CreateDialog(Modal):
    def __init__(self, app, on_created=None, parent=None):
        super().__init__(app, "Создать профиль", width=520, parent=parent)
        self.on_created = on_created
        self.versions: list[dict] = []
        self.loaders: list[dict] = []
        form = QFormLayout()
        form.setSpacing(8)
        self.name = QLineEdit()
        app.bind(self.name, "Название", "placeholder")
        form.addRow(label(app, "Название", "muted"), self.name)
        self.kind = QComboBox()
        for k, ru in TYPE_FILTERS:
            self.kind.addItem(app.t(ru), k)
        self.kind.currentIndexChanged.connect(self._fill_versions)
        form.addRow(label(app, "Тип версий", "muted"), self.kind)
        self.search = QLineEdit()
        app.bind(self.search, "Поиск версии", "placeholder")
        self.search.textChanged.connect(self._fill_versions)
        form.addRow(label(app, "Поиск версии", "muted"), self.search)
        self.ver = QComboBox()
        self.ver.currentIndexChanged.connect(self._version_changed)
        form.addRow(label(app, "Версия Minecraft", "muted"), self.ver)
        self.loader = QComboBox()
        self.loader.currentIndexChanged.connect(self._fill_loader_versions)
        form.addRow(label(app, "Загрузчик", "muted"), self.loader)
        self.lver = QComboBox()
        form.addRow(label(app, "Версия загрузчика", "muted"), self.lver)
        self.body.addLayout(form)
        self.status = label(app, "Загрузка версий...", "muted")
        self.body.addWidget(self.status)
        self.btn_create = self.add_button("Создать", "primary", self._create)
        self.btn_create.setEnabled(False)
        self.add_button("Отмена", "ghost", self.reject)
        app.call("versions:list", None, self._versions_ok, lambda m: self.status.setText(m))

    # ----- версии
    def _versions_ok(self, r) -> None:
        self.versions = r.get("versions") or []
        self.status.setText("")
        self._fill_versions()

    def _fill_versions(self, *_a) -> None:
        shown = filter_versions(self.versions, self.kind.currentData() or "release", self.search.text())
        cur = self.ver.currentData()
        self.ver.blockSignals(True)
        self.ver.clear()
        for v in shown[:600]:
            self.ver.addItem(v["id"], v["id"])
        if cur:
            i = self.ver.findData(cur)
            if i >= 0:
                self.ver.setCurrentIndex(i)
        self.ver.blockSignals(False)
        self._version_changed()

    def _version_changed(self, *_a) -> None:
        mc = self.ver.currentData()
        self.btn_create.setEnabled(bool(mc))
        self.loader.blockSignals(True)
        self.loader.clear()
        self.lver.clear()
        self.loader.blockSignals(False)
        if not mc:
            return
        self._loading_for = mc
        self.status.setText(self.app.t("Загрузка версий..."))

        def ok(r):
            if getattr(self, "_loading_for", None) != mc:
                return
            self.status.setText("")
            self.loaders = r or []
            self.loader.blockSignals(True)
            self.loader.clear()
            for l in self.loaders:
                self.loader.addItem(NAMES.get(l["loader"], l["loader"]), l["loader"])
            self.loader.blockSignals(False)
            self._fill_loader_versions()
        self.app.call("loaders:list", mc, ok, lambda m: self.status.setText(m))

    def _fill_loader_versions(self, *_a) -> None:
        cur = self.loader.currentData()
        self.lver.clear()
        entry = next((l for l in self.loaders if l["loader"] == cur), None)
        if cur == "vanilla" or not entry:
            self.lver.addItem(self.app.t("Загрузчик не нужен"), "")
            self.lver.setEnabled(False)
            return
        self.lver.setEnabled(True)
        for v in entry["versions"]:
            self.lver.addItem(str(v), str(v))

    def _create(self) -> None:
        mc = self.ver.currentData()
        if not mc:
            return
        payload = {"name": self.name.text().strip(), "version": mc, "loader": self.loader.currentData() or "vanilla",
                   "loaderVersion": self.lver.currentData() or ""}
        self.btn_create.setEnabled(False)

        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                self.accept()
                self.app.toast("Профиль создан", "ok")
                self.app.refresh_profiles()
                if self.on_created:
                    self.on_created(r["profile"])
            else:
                self.btn_create.setEnabled(True)
                self.app.toast((r or {}).get("error") or "Не удалось создать профиль", "err")
        self.app.call("profiles:create", payload, ok, lambda m: (self.btn_create.setEnabled(True), self.app.toast(m, "err")))


class EditDialog(Modal):
    def __init__(self, app, profile: dict, on_saved=None, parent=None):
        super().__init__(app, "Настройки", width=560, parent=parent)
        self.p = profile
        self.on_saved = on_saved
        self.title.setText(f"{app.t('Настройки')}: {profile['name']}")
        form = QFormLayout()
        form.setSpacing(8)
        self.name = QLineEdit(profile.get("name", ""))
        form.addRow(label(app, "Название", "muted"), self.name)

        max_ram = int(app.settings.get("systemRamGb") or 8)
        self.ram_on = QCheckBox()
        app.bind(self.ram_on, "Память для этого профиля")
        self.ram_on.setChecked(profile.get("ram") is not None)
        self.ram = QSlider(Qt.Horizontal)
        self.ram.setRange(1, max(2, max_ram))
        self.ram.setValue(int(profile.get("ram") or app.settings.get("ram") or 4))
        self.ram_lbl = QLabel()
        self.ram.valueChanged.connect(lambda v: self.ram_lbl.setText(f"{v} GB"))
        self.ram_lbl.setText(f"{self.ram.value()} GB")
        self.ram_on.toggled.connect(self.ram.setEnabled)
        self.ram.setEnabled(self.ram_on.isChecked())
        rr = QHBoxLayout()
        rr.addWidget(self.ram, 1)
        rr.addWidget(self.ram_lbl)
        rr.addWidget(button(app, "Подобрать", "small", self._suggest_ram))
        form.addRow(self.ram_on, rr)
        self.ram_hint = label(app, None, "muted", wrap=True)
        form.addRow(self.ram_hint)

        # внешний вид: цвет, значок, группа
        self.color = profile.get("color") if profile.get("color") in PROFILE_COLORS else None
        self.glyph = profile.get("glyph") if profile.get("glyph") in PROFILE_GLYPHS else None
        form.addRow(label(app, "Цвет и значок", "muted"), self._look_picker())
        self.group = QLineEdit(str(profile.get("group") or ""))
        self.group.setMaxLength(24)
        app.bind(self.group, "Группа (например: Выживание)", "placeholder")
        form.addRow(label(app, "Группа", "muted"), self.group)

        self.jvm = QLineEdit(profile.get("jvmArgs", ""))
        self.jvm.setPlaceholderText("-XX:+UseG1GC -Dfoo=bar")
        form.addRow(label(app, "Аргументы Java", "muted"), self.jvm)
        self.w = QLineEdit(str(profile.get("width") or ""))
        self.h = QLineEdit(str(profile.get("height") or ""))
        self.w.setPlaceholderText("854")
        self.h.setPlaceholderText("480")
        wh = QHBoxLayout()
        wh.addWidget(self.w)
        wh.addWidget(QLabel("×"))
        wh.addWidget(self.h)
        form.addRow(label(app, "Размер окна (ширина × высота)", "muted"), wh)
        self.full = QCheckBox()
        app.bind(self.full, "На весь экран")
        self.full.setChecked(bool(profile.get("fullscreen")))
        form.addRow(self.full)
        self.java = QLineEdit(profile.get("javaPath", ""))
        form.addRow(label(app, "Путь к Java для профиля", "muted"), self.java)
        self.body.addLayout(form)

        # серверы
        self.body.addWidget(label(app, "Серверы", "h3"))
        self.srv_list = QListWidget()
        self.srv_list.setMinimumHeight(110)
        self.body.addWidget(self.srv_list)
        row = QHBoxLayout()
        self.srv_addr = QLineEdit()
        app.bind(self.srv_addr, "Адрес сервера (host:port)", "placeholder")
        self.srv_name = QLineEdit()
        app.bind(self.srv_name, "Название (необязательно)", "placeholder")
        row.addWidget(self.srv_name, 1)
        row.addWidget(self.srv_addr, 1)
        self.body.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(button(app, "Добавить", "small", self._srv_add))
        row2.addWidget(button(app, "★ В избранное", "small", self._srv_favorite))
        row2.addWidget(button(app, "Проверить", "small", self._srv_ping))
        row2.addWidget(button(app, "Из servers.dat", "small", self._srv_import))
        row2.addWidget(button(app, "Удалить", "small", self._srv_remove))
        row2.addStretch(1)
        self.body.addLayout(row2)
        self.srv_status = label(app, None, "muted", wrap=True)
        self.body.addWidget(self.srv_status)
        self._load_servers()

        self.add_button("Отмена", "ghost", self.reject)
        self.add_button("Сохранить", "primary", self._save)

    def _pid(self) -> str:
        return self.p["id"]

    # ----- цвет, значок, группа
    def _look_picker(self) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.look_btns: list[tuple[str | None, QPushButton]] = []
        row = QHBoxLayout()
        row.setSpacing(4)
        auto = QPushButton(self.app.t("Авто"))
        auto.setProperty("kind", "small")
        auto.clicked.connect(lambda _=False: self._set_color(None))
        row.addWidget(auto)
        for c in PROFILE_COLORS:
            b = QPushButton("")
            b.setFixedSize(24, 24)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=c: self._set_color(c))
            self.look_btns.append((c, b))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        auto2 = QPushButton(self.app.t("Авто"))
        auto2.setProperty("kind", "small")
        auto2.clicked.connect(lambda _=False: self._set_glyph(None))
        row2.addWidget(auto2)
        for g in PROFILE_GLYPHS:
            b = QPushButton(g)
            b.setFixedSize(28, 28)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, g=g: self._set_glyph(g))
            row2.addWidget(b)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(44, 44)
        lay.addWidget(self.preview)
        self._paint_look()
        return box

    def _paint_look(self) -> None:
        color, text = tile_look({"name": self.name.text() or self.p.get("name"), "color": self.color, "glyph": self.glyph})
        self.preview.setText(text)
        self.preview.setStyleSheet(f"background: {color}; color: #fff; border-radius: 10px; font-weight: 800;"
                                   "font-size: 16px; border: none;")
        for c, b in self.look_btns:
            ring = "2px solid #fff" if c == self.color else "2px solid transparent"
            b.setStyleSheet(f"background: {c}; border: {ring}; border-radius: 12px;")

    def _set_color(self, c) -> None:
        self.color = c
        self._paint_look()

    def _set_glyph(self, g) -> None:
        self.glyph = g
        self._paint_look()

    # ----- подбор памяти
    def _suggest_ram(self) -> None:
        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                self.ram_on.setChecked(True)
                self.ram.setValue(int(r["ram"]))
                self.ram_hint.setText(self.app.t("Рекомендуем {n} GB: {r}", n=r["ram"], r=self.app.t(str(r.get("reason") or ""))))
            else:
                self.ram_hint.setText(self.app.t(str((r or {}).get("error") or "?")))
        self.app.call("ram:suggest", {"profileId": self._pid()}, ok, lambda m: self.ram_hint.setText(m))

    def _srv_favorite(self) -> None:
        s = self._selected()
        if not s:
            self.srv_status.setText(self.app.t("Выбери сервер в списке"))
            return
        self.app.call("servers:edit", {"profileId": self._pid(), "id": s["id"], "favorite": not s.get("favorite")},
                      lambda r: self._load_servers(), lambda m: self.srv_status.setText(m))

    def _load_servers(self) -> None:
        def ok(r):
            self.srv_list.clear()
            for s in (r or {}).get("servers") or []:
                it = QListWidgetItem(f"{'★ ' if s.get('favorite') else ''}{s['name']}  —  {s['host']}:{s['port']}")
                it.setData(Qt.UserRole, s)
                self.srv_list.addItem(it)
        self.app.call("servers:list", {"profileId": self._pid()}, ok, lambda m: self.srv_status.setText(m))

    def _srv_add(self) -> None:
        addr = self.srv_addr.text().strip()
        if not addr:
            return

        def ok(r):
            if (r or {}).get("ok"):
                self.srv_addr.clear()
                self.srv_name.clear()
                self.srv_status.setText("")
                self._load_servers()
            else:
                self.srv_status.setText(self.app.t((r or {}).get("error") or "?"))
        self.app.call("servers:add", {"profileId": self._pid(), "name": self.srv_name.text(), "address": addr}, ok,
                      lambda m: self.srv_status.setText(m))

    def _selected(self):
        it = self.srv_list.currentItem()
        d = it.data(Qt.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _srv_remove(self) -> None:
        s = self._selected()
        if s:
            self.app.call("servers:remove", {"profileId": self._pid(), "id": s["id"]}, lambda r: self._load_servers(),
                          lambda m: self.srv_status.setText(m))

    def _srv_import(self) -> None:
        def ok(r):
            if (r or {}).get("ok"):
                self.srv_status.setText(f"+{r.get('added', 0)} / {r.get('found', 0)}")
                self._load_servers()
            else:
                self.srv_status.setText(self.app.t((r or {}).get("error") or "?"))
        self.app.call("servers:import", {"profileId": self._pid()}, ok, lambda m: self.srv_status.setText(m))

    def _srv_ping(self) -> None:
        s = self._selected()
        if not s:
            return
        self.srv_status.setText("…")

        def ok(r):
            if r.get("online"):
                pl = r.get("players") or {}
                self.srv_status.setText(f"{self.app.t('онлайн')} · {r.get('latency')} ms · "
                                        f"{self.app.t('Игроков: {o}/{m}', o=pl.get('online', 0), m=pl.get('max', 0))} · {r.get('motd', '')}")
            else:
                self.srv_status.setText(f"{self.app.t('офлайн')}: {r.get('error', '')}")
        self.app.call("servers:ping", {"host": s["host"], "port": s["port"]}, ok, lambda m: self.srv_status.setText(m))

    def _save(self) -> None:
        patch = {
            "name": self.name.text(),
            "ram": self.ram.value() if self.ram_on.isChecked() else None,
            "jvmArgs": self.jvm.text(),
            "width": self.w.text().strip() or None,
            "height": self.h.text().strip() or None,
            "fullscreen": self.full.isChecked(),
            "javaPath": self.java.text(),
            "color": self.color,
            "glyph": self.glyph,
            "group": self.group.text(),
        }

        def ok(r):
            if (r or {}).get("ok"):
                self.accept()
                self.app.toast("Профиль сохранён", "ok")
                self.app.refresh_profiles()
                if self.on_saved:
                    self.on_saved()
            else:
                self.app.toast((r or {}).get("error") or "?", "err")
        self.app.call("profiles:update", {"id": self._pid(), "patch": patch}, ok, lambda m: self.app.toast(m, "err"))


class ProfilesPage(QWidget):
    """«Мои сборки»: поиск, кнопки «Импорт» и «Создать», сетка карточек (две колонки). Действия сборки — в меню «⋯»."""

    COLS = 2

    def __init__(self, app):
        super().__init__()
        self.app = app
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label(app, "Мои сборки", "h2"))
        bar.addSpacing(10)
        self.search = QLineEdit()
        app.bind(self.search, "Поиск сборки", "placeholder")
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search)
        bar.addStretch(1)
        self.btn_import = button(app, "Импорт", "ghost", self._import_menu)
        bar.addWidget(self.btn_import)
        bar.addWidget(button(app, "Создать профиль", "primary", self.open_create))
        root.addLayout(bar)
        self.status = label(app, None, "muted", wrap=True)
        root.addWidget(self.status)
        self.scroll = VScroll()
        root.addWidget(self.scroll, 1)
        app.profiles_changed.connect(self.refresh)
        app.event.connect(self._on_event)
        self.refresh()

    def _import_menu(self) -> None:
        m = QMenu(self)
        for ru, fn in (("Скачать сборку", self._get_pack), ("Импорт .mrpack", self._import_mrpack),
                       ("Ввести код сборки", self._enter_code),
                       ("Импорт из других лаунчеров", self._import_launchers)):
            m.addAction(self.app.t(ru)).triggered.connect(lambda _=False, f=fn: f())
        m.exec(self.btn_import.mapToGlobal(self.btn_import.rect().bottomLeft()))

    def _on_event(self, ch: str, payload) -> None:
        if ch in ("profile:progress", "pack:progress") and isinstance(payload, dict) and payload.get("text"):
            self.status.setText(self.app.t(str(payload["text"])))

    def on_show(self) -> None:
        self.app.refresh_profiles()

    def refresh(self) -> None:
        self.scroll.clear()
        app = self.app
        shown = filter_profiles(app.profiles, self.search.text())
        if not app.profiles:
            self.scroll.lay.addWidget(label(app, "Профилей пока нет. Создай первый — это быстро.", "muted", wrap=True))
        elif not shown:
            self.scroll.lay.addWidget(label(app, "Ничего не найдено", "muted"))
        groups = group_profiles(shown)
        multi = len(groups) > 1 or (groups and groups[0][0] != "")
        for gname, items in groups:
            if multi:
                head = QLabel((gname or app.t("Без группы")).upper())
                head.setProperty("kind", "muted")
                head.setStyleSheet("font-weight: 700; font-size: 11px; letter-spacing: 1px; padding-top: 6px;")
                self.scroll.lay.addWidget(head)
            host = QWidget()
            grid = QGridLayout(host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(10)
            for n, p in enumerate(items):
                card = self._card(p)
                grid.addWidget(card, n // self.COLS, n % self.COLS)
                card.load_status()
            for c in range(self.COLS):
                grid.setColumnStretch(c, 1)
            self.scroll.lay.addWidget(host)
        self.scroll.lay.addStretch(1)

    def _card(self, p: dict) -> QWidget:
        cur = p["id"] == self.app.current_id
        card = BuildCard(self.app, p, selected=cur, actions=[
            ("Настройки", lambda p=p: self.open_edit(p)),
            ("Открыть папку", lambda p=p: self._folder(p)),
            ("Экспорт .mrpack", lambda p=p: self._export(p)),
            ("Код сборки", lambda p=p: extras.show_code(self.app, p)),
            ("Дублировать", lambda p=p: extras.duplicate(self.app, p)),
            ("Обновить сборку", lambda p=p: extras.update_pack(self.app, p)),
            (None, None),
            ("Удалить", lambda p=p: self._delete(p)),
        ])
        card.chosen.connect(self._select)
        card.play.connect(lambda pid: self.app.event.emit("tray:play", None))
        return card

    # ----- действия
    def open_create(self) -> None:
        CreateDialog(self.app).exec()

    def open_edit(self, p: dict) -> None:
        EditDialog(self.app, p).exec()

    def _select(self, pid: str) -> None:
        self.app.call("profiles:select", pid, lambda r: self.app.refresh_profiles(), lambda m: self.app.toast(m, "err"))

    def _folder(self, p: dict) -> None:
        self.app.call("folder:open", {"which": "instance", "profileId": p["id"]}, None, lambda m: self.app.toast(m, "err"))

    def _delete(self, p: dict) -> None:
        if not self.app.confirm("Удалить профиль «{n}»? Файлы профиля (моды, миры) тоже будут удалены.", "Удалить",
                                danger=True, n=p["name"]):
            return

        def ok(r):
            if (r or {}).get("ok"):
                self.app.refresh_profiles()
            else:
                self.app.toast((r or {}).get("error") or "?", "err")
        self.app.call("profiles:delete", {"id": p["id"], "deleteFiles": True}, ok, lambda m: self.app.toast(m, "err"))

    def _export(self, p: dict) -> None:
        self.status.setText("…")

        def ok(r):
            if (r or {}).get("canceled"):
                self.status.setText("")
            elif (r or {}).get("ok"):
                self.status.setText(self.app.t("Сборка сохранена: {f} (модов по ссылкам: {a}, вложено: {b})",
                                               f=r.get("file"), a=r.get("linked", 0), b=r.get("bundled", 0)))
                self.app.toast("Сборка экспортирована в .mrpack", "ok")
            else:
                self.status.setText((r or {}).get("error") or "?")
        self.app.call("profile:export", {"profileId": p["id"]}, ok, lambda m: self.status.setText(m))

    def _import_mrpack(self) -> None:
        self.status.setText("…")

        def ok(r):
            if (r or {}).get("canceled"):
                self.status.setText("")
                return
            self.app.refresh_profiles()
            if (r or {}).get("ok"):
                miss = r.get("missing") or []
                self.status.setText(self.app.t("Готово: создан профиль «{n}»", n=r["profile"]["name"]) +
                                    (f" · {len(miss)} ✗" if miss else ""))
            else:
                self.status.setText((r or {}).get("error") or "?")
        self.app.call("profile:import", None, ok, lambda m: self.status.setText(m))

    def _get_pack(self) -> None:
        self.app.show_page("mods")
        page = get_page(self.app, "mods")
        fn = getattr(page, "set_kind", None)
        if callable(fn):
            fn("modpack")

    def _enter_code(self) -> None:
        extras.EnterCodeDialog(self.app).exec()

    def _import_launchers(self) -> None:
        try:
            from ..dialogs.importer import ImportDialog
            ImportDialog(self.app).exec()
        except ImportError as e:
            self.app.toast(str(e), "err")

    def retranslate(self) -> None:
        self.refresh()

    def selftest(self) -> None:
        CreateDialog(self.app)
        if self.app.profiles:
            EditDialog(self.app, self.app.profiles[0])
