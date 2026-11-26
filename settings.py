"""Вкладка «Настройки»: аккаунт, игра, оформление, окно, Discord, обновления, о программе."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import i18n, theme
from ..dialogs.msaccount import MsLoginDialog
from ..dialogs.shared import Segment
from ..widgets import Card, ClickLabel, Modal, VScroll, button, clear_layout, label
from ...resources import asset

i18n.register({
    "Обновлять моды автоматически перед запуском игры": "Update mods automatically before launching the game",
    "Настройки": "Settings",
    "Аккаунт": "Account",
    "Режим": "Mode",
    "Офлайн (только ник)": "Offline (nickname only)",
    "Microsoft (лицензия)": "Microsoft (licensed)",
    "Ник (для офлайн-режима)": "Nickname (offline mode)",
    "Client ID приложения Azure": "Azure application Client ID",
    "Добавить аккаунт": "Add account",
    "Не выполнен вход": "Not signed in",
    "Активный": "Active",
    "Выбрать": "Select",
    "Удалить": "Delete",
    "Жду подтверждения входа...": "Waiting for sign-in confirmation...",
    "Аккаунтов можно добавить несколько. В игру заходит тот, что отмечен «Активный». Для входа нужно своё приложение Azure — инструкция в README (раздел «Вход через Microsoft»).":
        "You can add several accounts. The one marked “Active” is used in game. Sign-in needs your own Azure app — see the README (“Microsoft sign-in”).",
    "Игра": "Game",
    "Выделенная память: {n} ГБ": "Allocated memory: {n} GB",
    "Путь к Java": "Java path",
    "Пусто — Java скачается автоматически": "Empty — Java is downloaded automatically",
    "Нужная версия Java подбирается под версию Minecraft и скачивается сама при первом запуске.":
        "The right Java version is picked for the Minecraft version and downloaded on first launch.",
    "Оформление": "Appearance",
    "Язык / Language": "Language",
    "Liquid Glass — стеклянные панели с размытием и бликами": "Glass panels with blur and highlights",
    "Сила эффекта: {n}%": "Effect strength: {n}%",
    "Фон лаунчера": "Launcher background",
    "Сейчас: стандартный фон": "Now: default background",
    "Сейчас: {n}": "Now: {n}",
    "видео": "video",
    "картинка": "image",
    "Выбрать картинку или видео": "Choose an image or video",
    "Сбросить фон": "Reset background",
    "Затемнение фона: {n}%": "Background dimming: {n}%",
    "Окно и запуск": "Window and startup",
    "Крестик прячет лаунчер в трей (значок у часов), а не закрывает его": "The close button hides the launcher to the tray instead of quitting",
    "Запускать вместе с Windows (свёрнутым в трей)": "Start with Windows (minimized to the tray)",
    "Проверять моды перед запуском игры": "Check mods before launching the game",
    "Делать резервные копии изменённых миров перед запуском игры": "Back up changed worlds before launching the game",
    "Сколько копий каждого мира хранить": "Backups to keep per world",
    "Discord": "Discord",
    "Показывать в Discord, во что я играю (Rich Presence)": "Show in Discord what I'm playing (Rich Presence)",
    "Application ID приложения Discord": "Discord application ID",
    "Выключено": "Off",
    "Укажи Application ID": "Enter the Application ID",
    "Жду запуска Discord...": "Waiting for Discord to start...",
    "Discord не принял Application ID": "Discord rejected the Application ID",
    "Подключено: {n}": "Connected: {n}",
    "Подключено": "Connected",
    "Обновление лаунчера": "Launcher updates",
    "Сам искать и скачивать новые версии с GitHub": "Look for and download new versions from GitHub automatically",
    "Адрес обновлений": "Update address",
    "Версия лаунчера: {n}": "Launcher version: {n}",
    "Проверить обновления": "Check for updates",
    "Проверяю обновления...": "Checking for updates...",
    "Найдена версия {v} — скачиваю...": "Version {v} found — downloading...",
    "Скачиваю обновление: {p}%": "Downloading update: {p}%",
    "Обновление {v} готово — перезапусти лаунчер": "Update {v} is ready — restart the launcher",
    "У тебя последняя версия": "You have the latest version",
    "Ошибка обновления: {m}": "Update error: {m}",
    "Перезапустить": "Restart",
    "Дополнительно": "Advanced",
    "CurseForge API-ключ": "CurseForge API key",
    "Корневая папка": "Root folder",
    "Выбрать папку": "Choose folder",
    "Сохранить": "Save",
    "Сохранено": "Saved",
    "Открыть лог лаунчера": "Open launcher log",
    "О программе": "About",
    "Разработчик": "Developer",
    "DLauncher · версия {n}": "DLauncher · version {n}",
    "Тестировщик": "Tester",
    "Звук при получении достижения": "Sound when an achievement is unlocked",
    "Что нового": "What's new",
    "Оформление": "Look", "Цвет лаунчера": "Launcher color", "Белый": "White",
    "Тёмная": "Dark", "Полночь": "Midnight", "Лес": "Forest", "Закат": "Sunset",
    "Закрыть": "Close",
    "Вход через Microsoft: ошибка: {m}": "Microsoft sign-in error: {m}",
    "Удалить аккаунт «{n}»?": "Remove account “{n}”?",
    "Фон сброшен": "Background reset",
    "Фон установлен": "Background set",
})

RAM_CHIPS = (2, 4, 6, 8, 12)


def update_text(app, s: dict) -> str:
    st = (s or {}).get("state")
    v = (s or {}).get("version") or ""
    if st == "checking":
        return app.t("Проверяю обновления...")
    if st == "available":
        return app.t("Найдена версия {v} — скачиваю...", v=v)
    if st == "downloading":
        return app.t("Скачиваю обновление: {p}%", p=(s or {}).get("percent") or 0)
    if st == "ready":
        return app.t("Обновление {v} готово — перезапусти лаунчер", v=v)
    if st == "none":
        return app.t("У тебя последняя версия")
    if st == "error":
        return app.t("Ошибка обновления: {m}", m=(s or {}).get("message") or "")
    return ""


def discord_text(app, s: dict | None) -> str:
    if not s:
        return ""
    base = {"off": "Выключено", "no-id": "Укажи Application ID", "connecting": "Жду запуска Discord...",
            "bad-id": "Discord не принял Application ID"}.get(s.get("state"))
    if base:
        return app.t(base)
    return app.t("Подключено: {n}", n=s["user"]) if s.get("user") else app.t("Подключено")


def clamp_ram(value: float, max_gb: int) -> float:
    return min(max(round(float(value) * 2) / 2, 1), max(1, int(max_gb or 16)))


def fmt_gb(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def build_patch(f: dict, max_ram: int) -> dict:
    """Собирает словарь настроек из значений формы (чистая функция — удобно тестировать)."""
    return {
        "accountMode": f["accountMode"],
        "nickname": str(f["nickname"]).strip()[:16] or "Player",
        "msClientId": str(f["msClientId"]).strip(),
        "ram": clamp_ram(f["ram"], max_ram),
        "javaPath": str(f["javaPath"]).strip(),
        "lang": "en" if f["lang"] == "en" else "ru",
        "glass": bool(f["glass"]),
        "glassStrength": int(f["glassStrength"]),
        "bgDim": int(f["bgDim"]),
        "closeToTray": bool(f["closeToTray"]),
        "autoStart": bool(f["autoStart"]),
        "compatCheck": bool(f["compatCheck"]),
        "autoUpdateMods": bool(f.get("autoUpdateMods", False)),
        "achSound": bool(f.get("achSound", True)),
        "autoBackup": bool(f["autoBackup"]),
        "backupKeep": int(f["backupKeep"]),
        "discordRpc": bool(f["discordRpc"]),
        "discordClientId": "".join(ch for ch in str(f["discordClientId"]) if ch.isdigit())[:20],
        "autoUpdate": bool(f["autoUpdate"]),
        "updateUrl": str(f["updateUrl"]).strip(),
        "curseforgeKey": str(f["curseforgeKey"]).strip(),
        "rootDir": str(f["rootDir"]).strip(),
    }


def slider(lo, hi, step=1):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setSingleStep(step)
    return s


def line(app, placeholder_ru: str | None = None, password: bool = False) -> QLineEdit:
    e = QLineEdit()
    if placeholder_ru:
        app.bind(e, placeholder_ru, "placeholder")
    if password:
        e.setEchoMode(QLineEdit.Password)
    return e


def check(app, ru: str) -> QCheckBox:
    c = QCheckBox()
    app.bind(c, ru)
    return c


def block(app, title_ru: str) -> Card:
    c = Card()
    c.lay.addWidget(label(app, title_ru, "h3"))
    return c


def field(app, ru: str, widget) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addWidget(label(app, ru, "muted"))
    lay.addWidget(widget)
    return w


class SettingsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ms_dialog: MsLoginDialog | None = None
        self.ms_state: dict = {}
        self.dc_state: dict | None = None
        self.up_state: dict = getattr(app, "last_update", None) or {}
        self._loading = False
        self._clicks = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(lambda: setattr(self, "_clicks", 0))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = VScroll()
        outer.addWidget(sc)
        L = sc.lay

        # --- Аккаунт
        b = block(app, "Аккаунт")
        self.mode = QComboBox()
        self.mode.addItem("", "offline")
        self.mode.addItem("", "microsoft")
        b.lay.addWidget(field(app, "Режим", self.mode))
        self.nick = line(app)
        self.nick.setMaxLength(16)
        self.row_nick = field(app, "Ник (для офлайн-режима)", self.nick)
        b.lay.addWidget(self.row_nick)
        self.ms_box = QWidget()
        mv = QVBoxLayout(self.ms_box)
        mv.setContentsMargins(0, 0, 0, 0)
        self.msid = line(app)
        self.msid.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        mv.addWidget(field(app, "Client ID приложения Azure", self.msid))
        self.ms_list = QVBoxLayout()
        mv.addLayout(self.ms_list)
        self.ms_msg = label(app, None, "muted", wrap=True)
        mv.addWidget(self.ms_msg)
        self.ms_login_btn = button(app, "Добавить аккаунт", "ghost", self.ms_login)
        mv.addWidget(self.ms_login_btn)
        mv.addWidget(label(app, "Аккаунтов можно добавить несколько. В игру заходит тот, что отмечен «Активный». Для входа нужно своё приложение Azure — инструкция в README (раздел «Вход через Microsoft»).",
                           "muted", wrap=True))
        b.lay.addWidget(self.ms_box)
        L.addWidget(b)

        # --- Игра
        b = block(app, "Игра")
        self.ram_lbl = label(app, None, "muted")
        b.lay.addWidget(self.ram_lbl)
        self.ram = slider(2, 32)  # шаг 0.5 ГБ
        self.ram.valueChanged.connect(self._ram_changed)
        b.lay.addWidget(self.ram)
        chips = QHBoxLayout()
        for gb in RAM_CHIPS:
            c = button(app, "", "chip", lambda g=gb: self.ram.setValue(int(g * 2)))
            c.setText(f"{gb} " + ("GB" if app.lang == "en" else "ГБ"))
            chips.addWidget(c)
        chips.addStretch(1)
        self._chips = chips
        b.lay.addLayout(chips)
        self.java = line(app, "Пусто — Java скачается автоматически")
        b.lay.addWidget(field(app, "Путь к Java", self.java))
        b.lay.addWidget(label(app, "Нужная версия Java подбирается под версию Minecraft и скачивается сама при первом запуске.", "muted", wrap=True))
        L.addWidget(b)

        # --- Оформление
        b = block(app, "Оформление")
        self.lang = QComboBox()
        self.lang.addItem("Русский", "ru")
        self.lang.addItem("English", "en")
        b.lay.addWidget(field(app, "Язык / Language", self.lang))
        self.glass = check(app, "Liquid Glass — стеклянные панели с размытием и бликами")
        self.glass.toggled.connect(lambda on: self.glass_row.setVisible(on))
        b.lay.addWidget(self.glass)
        self.glass_row = QWidget()
        gl = QVBoxLayout(self.glass_row)
        gl.setContentsMargins(0, 0, 0, 0)
        self.glass_lbl = label(app, None, "muted")
        self.glass_s = slider(0, 100, 5)
        self.glass_s.valueChanged.connect(lambda v: self.glass_lbl.setText(self.app.t("Сила эффекта: {n}%", n=v)))
        gl.addWidget(self.glass_lbl)
        gl.addWidget(self.glass_s)
        b.lay.addWidget(self.glass_row)
        b.lay.addWidget(label(app, "Фон лаунчера", "h3"))
        self.bg_state = label(app, None, "muted", wrap=True)
        b.lay.addWidget(self.bg_state)
        row = QHBoxLayout()
        self.bg_choose_btn = button(app, "Выбрать картинку или видео", "ghost", self.bg_choose)
        self.bg_reset_btn = button(app, "Сбросить фон", "ghost", self.bg_reset)
        row.addWidget(self.bg_choose_btn)
        row.addWidget(self.bg_reset_btn)
        b.lay.addLayout(row)
        self.bg_msg = label(app, None, "muted", wrap=True)
        b.lay.addWidget(self.bg_msg)
        self.dim_lbl = label(app, None, "muted")
        self.dim = slider(0, 80, 5)
        self.dim.valueChanged.connect(lambda v: self.dim_lbl.setText(self.app.t("Затемнение фона: {n}%", n=v)))
        b.lay.addWidget(self.dim_lbl)
        b.lay.addWidget(self.dim)
        # оформление: тон фона и цвет акцента (применяются сразу)
        b.lay.addWidget(label(app, "Оформление", "muted"))
        self.tone_seg = Segment(app, theme.TONE_NAMES, "dark", self._tone_changed)
        b.lay.addWidget(self.tone_seg)
        b.lay.addWidget(label(app, "Цвет лаунчера", "muted"))
        sw = QHBoxLayout()
        sw.setSpacing(6)
        self.accent_btns: list = []
        auto = button(app, "Белый", "small", lambda: self._accent_changed(""))
        sw.addWidget(auto)
        for c in theme.ACCENTS:
            ab = QPushButton("")
            ab.setFixedSize(26, 26)
            ab.setCursor(Qt.PointingHandCursor)
            ab.clicked.connect(lambda _=False, c=c: self._accent_changed(c))
            self.accent_btns.append((c, ab))
            sw.addWidget(ab)
        sw.addStretch(1)
        b.lay.addLayout(sw)
        self._paint_accent("")
        L.addWidget(b)

        # --- Окно и запуск
        b = block(app, "Окно и запуск")
        self.tray = check(app, "Крестик прячет лаунчер в трей (значок у часов), а не закрывает его")
        self.autostart = check(app, "Запускать вместе с Windows (свёрнутым в трей)")
        self.compat = check(app, "Проверять моды перед запуском игры")
        self.autoupdmods = check(app, "Обновлять моды автоматически перед запуском игры")
        self.achsound = check(app, "Звук при получении достижения")
        self.autobackup = check(app, "Делать резервные копии изменённых миров перед запуском игры")
        self.autobackup.toggled.connect(lambda on: self.row_keep.setVisible(on))
        for w in (self.tray, self.autostart, self.compat, self.autoupdmods, self.achsound, self.autobackup):
            b.lay.addWidget(w)
        self.keep = QSpinBox()
        self.keep.setRange(1, 20)
        self.row_keep = field(app, "Сколько копий каждого мира хранить", self.keep)
        b.lay.addWidget(self.row_keep)
        L.addWidget(b)

        # --- Discord
        b = block(app, "Discord")
        self.dc = check(app, "Показывать в Discord, во что я играю (Rich Presence)")
        self.dc.toggled.connect(lambda on: self.dc_box.setVisible(on))
        b.lay.addWidget(self.dc)
        self.dc_box = QWidget()
        dv = QVBoxLayout(self.dc_box)
        dv.setContentsMargins(0, 0, 0, 0)
        self.dcid = line(app)
        self.dcid.setMaxLength(20)
        self.dcid.setPlaceholderText("123456789012345678")
        dv.addWidget(field(app, "Application ID приложения Discord", self.dcid))
        self.dc_lbl = label(app, None, "muted")
        dv.addWidget(self.dc_lbl)
        b.lay.addWidget(self.dc_box)
        L.addWidget(b)

        # --- Обновления
        b = block(app, "Обновление лаунчера")
        self.autoupd = check(app, "Сам искать и скачивать новые версии с GitHub")
        b.lay.addWidget(self.autoupd)
        self.upd_url = line(app)
        self.upd_url.setPlaceholderText("https://github.com/ник/репозиторий")
        b.lay.addWidget(field(app, "Адрес обновлений", self.upd_url))
        self.upd_lbl = label(app, None, "muted", wrap=True)
        b.lay.addWidget(self.upd_lbl)
        row = QHBoxLayout()
        self.upd_check_btn = button(app, "Проверить обновления", "ghost", self.upd_check)
        self.upd_install_btn = button(app, "Перезапустить", "primary", self.upd_install)
        row.addWidget(self.upd_check_btn)
        row.addWidget(self.upd_install_btn)
        b.lay.addLayout(row)
        L.addWidget(b)

        # --- Дополнительно
        b = block(app, "Дополнительно")
        self.cf = line(app, None, password=True)
        self.cf.setPlaceholderText("console.curseforge.com")
        b.lay.addWidget(field(app, "CurseForge API-ключ", self.cf))
        self.root_edit = line(app)
        rr = QHBoxLayout()
        rr.addWidget(self.root_edit, 1)
        rr.addWidget(button(app, "Выбрать папку", "ghost", self.pick_root))
        rw = QWidget()
        rw.setLayout(rr)
        rr.setContentsMargins(0, 0, 0, 0)
        b.lay.addWidget(field(app, "Корневая папка", rw))
        b.lay.addWidget(button(app, "Открыть лог лаунчера", "ghost", self.open_log))
        L.addWidget(b)

        self.save_btn = button(app, "Сохранить", "primary", self.save)
        L.addWidget(self.save_btn)

        # --- О программе (5 нажатий подряд на «Разработчик» — секретная картинка)
        b = block(app, "О программе")
        b.lay.addWidget(label(app, "Разработчик", "muted"))
        self.dev = ClickLabel("DpaceUK")
        self.dev.setProperty("kind", "h2")
        self.dev.clicked.connect(self._dev_click)
        b.lay.addWidget(self.dev)
        self.ver_lbl = label(app, None, "muted")
        b.lay.addWidget(self.ver_lbl)
        b.lay.addWidget(button(app, "Тестировщик", "ghost", self.tester))
        b.lay.addWidget(button(app, "Обучение", "ghost", lambda: app.window.start_tour("overview")))
        b.lay.addWidget(button(app, "Что нового", "ghost", self.show_changelog))
        b.lay.addWidget(button(app, "Папка с героями", "ghost", self.open_guides))
        L.addWidget(b)
        L.addStretch(1)

        app.event.connect(self._on_event)
        app.settings_changed.connect(lambda _s: self._sync_bg())
        self.mode.currentIndexChanged.connect(lambda _=0: self._apply_mode())
        self._retext_combos()
        self.fill(app.settings)

    # ----- заполнение формы
    def _retext_combos(self) -> None:
        self.mode.setItemText(0, self.app.t("Офлайн (только ник)"))
        self.mode.setItemText(1, self.app.t("Microsoft (лицензия)"))

    def fill(self, s: dict) -> None:
        self._loading = True
        try:
            idx = self.mode.findData(s.get("accountMode") or "offline")
            self.mode.setCurrentIndex(max(idx, 0))
            self.nick.setText(s.get("nickname") or "")
            self.msid.setText(s.get("msClientId") or "")
            mx = int(s.get("systemRamGb") or 16)
            self.ram.setRange(2, max(2, mx * 2))
            self.ram.setValue(int(round(float(s.get("ram") or 4) * 2)))
            self._ram_changed(self.ram.value())
            self.java.setText(s.get("javaPath") or "")
            self.lang.setCurrentIndex(1 if s.get("lang") == "en" else 0)
            self.glass.setChecked(s.get("glass") is not False)
            self.glass_row.setVisible(self.glass.isChecked())
            self.glass_s.setValue(int(s.get("glassStrength") if s.get("glassStrength") is not None else 60))
            self.dim.setValue(int(s.get("bgDim") or 0))
            self.tone_seg.select(s.get("tone") or "dark", notify=False)
            self._paint_accent(s.get("accent") or "")
            self.tray.setChecked(bool(s.get("closeToTray")))
            self.autostart.setChecked(bool(s.get("autoStart")))
            self.compat.setChecked(s.get("compatCheck") is not False)
            self.autoupdmods.setChecked(s.get("autoUpdateMods") is True)
            self.achsound.setChecked(s.get("achSound") is not False)
            self.autobackup.setChecked(s.get("autoBackup") is not False)
            self.row_keep.setVisible(self.autobackup.isChecked())
            self.keep.setValue(int(s.get("backupKeep") or 5))
            self.dc.setChecked(bool(s.get("discordRpc")))
            self.dc_box.setVisible(self.dc.isChecked())
            self.dcid.setText(s.get("discordClientId") or "")
            self.autoupd.setChecked(s.get("autoUpdate") is not False)
            self.upd_url.setText(s.get("updateUrl") or "")
            self.cf.setText(s.get("curseforgeKey") or "")
            self.root_edit.setText(s.get("rootDir") or "")
            self.ver_lbl.setText(self.app.t("DLauncher · версия {n}", n=s.get("appVersion") or "—"))
            self._apply_mode()
            self._sync_bg()
            self._show_update()
            self._show_discord()
        finally:
            self._loading = False

    def on_show(self) -> None:
        self.fill(self.app.settings)
        self.refresh_ms()
        self.app.call("discord:status", None, self._set_discord, lambda m: None)
        self.app.call("update:info", None, self._upd_info, lambda m: None)

    def _upd_info(self, r) -> None:
        d = (r or {}).get("defaultUrl")
        if d:
            self.upd_url.setPlaceholderText(d)

    def retranslate(self) -> None:
        self._retext_combos()
        for i in range(self._chips.count()):
            w = self._chips.itemAt(i).widget()
            if w is not None:
                gb = RAM_CHIPS[i]
                w.setText(f"{gb} " + ("GB" if self.app.lang == "en" else "ГБ"))
        self._ram_changed(self.ram.value())
        self.glass_lbl.setText(self.app.t("Сила эффекта: {n}%", n=self.glass_s.value()))
        self.dim_lbl.setText(self.app.t("Затемнение фона: {n}%", n=self.dim.value()))
        self.ver_lbl.setText(self.app.t("DLauncher · версия {n}", n=self.app.settings.get("appVersion") or "—"))
        self._sync_bg()
        self._show_update()
        self._show_discord()
        self._render_ms()

    # ----- мелочи формы
    def _ram_changed(self, v: int) -> None:
        self.ram_lbl.setText(self.app.t("Выделенная память: {n} ГБ", n=fmt_gb(v / 2)))

    def _apply_mode(self) -> None:
        ms = self.mode.currentData() == "microsoft"
        self.ms_box.setVisible(ms)
        self.row_nick.setVisible(not ms)

    def pick_root(self) -> None:
        self._pick_dir_direct()

    def _pick_dir_direct(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        p = QFileDialog.getExistingDirectory(self, self.app.t("Выбрать папку"), self.root_edit.text())
        if p:
            self.root_edit.setText(p)

    def open_log(self) -> None:
        try:
            import os
            self.app.ctx.ui.open_path(os.path.join(self.app.ctx.user_data, "launcher.log"))
        except Exception as e:  # noqa: BLE001
            self.app.toast(str(e), "err")

    # ----- фон
    def _sync_bg(self) -> None:
        s = self.app.settings
        url = s.get("bgUrl") or ""
        if not url:
            self.bg_state.setText(self.app.t("Сейчас: стандартный фон"))
        else:
            name = s.get("bgName") or self.app.t("видео" if s.get("bgType") == "video" else "картинка")
            self.bg_state.setText(self.app.t("Сейчас: {n}", n=name))
        self.bg_reset_btn.setVisible(bool(url))

    def bg_choose(self) -> None:
        self.bg_msg.setText("")
        self.bg_choose_btn.setEnabled(False)

        def done():
            self.bg_choose_btn.setEnabled(True)

        def ok(r):
            done()
            r = r or {}
            if r.get("canceled"):
                return
            if not r.get("ok"):
                self.bg_msg.setText(self.app.t(r.get("error") or "?"))
                return
            self.app.refresh_settings()
            self.app.toast("Фон установлен", "ok")
        self.app.call("bg:choose", None, ok, lambda m: (done(), self.bg_msg.setText(m)))

    def bg_reset(self) -> None:
        def ok(r):
            self.app.refresh_settings()
            self.app.toast("Фон сброшен", "ok")
        self.app.call("bg:reset", None, ok, lambda m: self.app.toast(m, "err"))

    # ----- Microsoft
    def refresh_ms(self) -> None:
        self.app.call("ms:accounts", None, self._ms_got, lambda m: None)

    def _ms_got(self, r) -> None:
        self.ms_state = r or {}
        self._render_ms()

    def _render_ms(self) -> None:
        clear_layout(self.ms_list)
        accs = self.ms_state.get("accounts") or []
        if not accs:
            self.ms_list.addWidget(label(self.app, "Не выполнен вход", "muted"))
            return
        for a in accs:
            on = a["id"] == self.ms_state.get("active")
            row = QHBoxLayout()
            nm = QLabel(str(a.get("name") or "?"))
            row.addWidget(nm, 1)
            if on:
                row.addWidget(label(self.app, "Активный", "ok"))
            else:
                row.addWidget(button(self.app, "Выбрать", "small", lambda i=a["id"]: self.ms_select(i)))
            row.addWidget(button(self.app, "Удалить", "small", lambda i=a["id"], n=a.get("name"): self.ms_remove(i, n)))
            w = QWidget()
            w.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            self.ms_list.addWidget(w)

    def ms_select(self, acc_id: str) -> None:
        self.app.call("ms:select", acc_id, self._ms_after, lambda m: self.app.toast(m, "err"))

    def ms_remove(self, acc_id: str, name) -> None:
        if self.app.confirm("Удалить аккаунт «{n}»?", "Удалить", danger=True, n=name):
            self.app.call("ms:remove", acc_id, self._ms_after, lambda m: self.app.toast(m, "err"))

    def _ms_after(self, r) -> None:
        if (r or {}).get("ok"):
            self.ms_msg.setText("")
            self.ms_state = r
            self._render_ms()
        else:
            self.ms_msg.setText(self.app.t((r or {}).get("error") or "?"))

    def ms_login(self) -> None:
        cid = self.msid.text().strip()
        self.ms_login_btn.setEnabled(False)
        self.ms_msg.setText(self.app.t("Жду подтверждения входа..."))

        def login():
            def ok(r):
                self._close_ms_dialog()
                self.ms_login_btn.setEnabled(True)
                r = r or {}
                if not r.get("ok"):
                    self.ms_msg.setText(self.app.t("Вход через Microsoft: ошибка: {m}", m=self.app.t(r.get("error") or "?")))
                else:
                    self.ms_msg.setText("")
                    self._ms_got(r)
            self.app.call("ms:login", None, ok, lambda m: (self._close_ms_dialog(), self.ms_login_btn.setEnabled(True),
                                                           self.ms_msg.setText(m)))
        # Client ID нужен ядру — сохраняем перед входом
        self.app.save_settings({"msClientId": cid}, lambda s: login(), lambda m: (self.ms_login_btn.setEnabled(True), self.ms_msg.setText(m)))

    def _close_ms_dialog(self) -> None:
        d, self.ms_dialog = self.ms_dialog, None
        if d is not None:
            d.hide()
            d.deleteLater()

    def _ms_cancel(self) -> None:
        self.app.call("ms:cancel", None, None, None)
        self._close_ms_dialog()

    # ----- события ядра
    def _on_event(self, channel: str, payload) -> None:
        if channel == "ms:code" and isinstance(payload, dict):
            if self.ms_dialog is None:
                self.ms_dialog = MsLoginDialog(self.app, payload.get("code"), payload.get("url"), on_cancel=self._ms_cancel)
                self.ms_dialog.rejected.connect(lambda: None)
                self.ms_dialog.show()
            else:
                self.ms_dialog.set_code(payload.get("code"), payload.get("url"))
        elif channel == "update:status" and isinstance(payload, dict):
            self.up_state = payload
            self._show_update()
        elif channel == "discord:status":
            self._set_discord(payload)

    # ----- Discord
    def _set_discord(self, s) -> None:
        self.dc_state = s if isinstance(s, dict) else None
        self._show_discord()

    def _show_discord(self) -> None:
        self.dc_lbl.setText(discord_text(self.app, self.dc_state))

    # ----- обновления
    def _show_update(self) -> None:
        t = update_text(self.app, self.up_state)
        self.upd_lbl.setText(t or self.app.t("Версия лаунчера: {n}", n=self.app.settings.get("appVersion") or "—"))
        self.upd_install_btn.setVisible(self.up_state.get("state") == "ready")

    def upd_check(self) -> None:
        self.upd_lbl.setText(self.app.t("Проверяю обновления..."))

        def go(_s):
            def ok(r):
                if r and not r.get("ok") and r.get("error"):
                    self.upd_lbl.setText(self.app.t(r["error"]))
            self.app.call("update:check", {"download": True}, ok, lambda m: self.upd_lbl.setText(m))
        self.app.save_settings({"updateUrl": self.upd_url.text().strip()}, go)

    def upd_install(self) -> None:
        def ok(r):
            if r and r.get("error"):
                self.upd_lbl.setText(self.app.t(r["error"]))
        self.app.call("update:install", None, ok, lambda m: self.upd_lbl.setText(m))

    # ----- сохранение
    def form(self) -> dict:
        return {
            "accountMode": self.mode.currentData(), "nickname": self.nick.text(), "msClientId": self.msid.text(),
            "ram": self.ram.value() / 2, "javaPath": self.java.text(), "lang": self.lang.currentData(),
            "glass": self.glass.isChecked(), "glassStrength": self.glass_s.value(), "bgDim": self.dim.value(),
            "closeToTray": self.tray.isChecked(), "autoStart": self.autostart.isChecked(),
            "compatCheck": self.compat.isChecked(), "autoUpdateMods": self.autoupdmods.isChecked(),
            "achSound": self.achsound.isChecked(), "autoBackup": self.autobackup.isChecked(),
            "backupKeep": self.keep.value(), "discordRpc": self.dc.isChecked(), "discordClientId": self.dcid.text(),
            "autoUpdate": self.autoupd.isChecked(), "updateUrl": self.upd_url.text(),
            "curseforgeKey": self.cf.text(), "rootDir": self.root_edit.text(),
        }

    def save(self) -> None:
        patch = build_patch(self.form(), int(self.app.settings.get("systemRamGb") or 16))

        def ok(s):
            self.fill(s)
            self.app.toast("Сохранено", "ok")
            self.app.call("discord:status", None, self._set_discord, lambda m: None)
        self.app.save_settings(patch, ok)

    # ----- «О программе»
    def _dev_click(self) -> None:
        self._clicks += 1
        self._click_timer.start(3000)
        if self._clicks >= 5:
            self._clicks = 0
            self.secret()

    def secret(self) -> None:
        self.app.call("achievements:grant", {"id": "secret"}, None, None)
        dlg = Modal(self.app, "", width=360)
        dlg.title.hide()
        lb = QLabel()
        pm = QPixmap(asset("secret.png"))
        if not pm.isNull():
            lb.setPixmap(pm.scaled(440, 440, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lb.setAlignment(Qt.AlignCenter)
        dlg.body.addWidget(lb)
        QTimer.singleShot(3000, dlg.accept)
        dlg.add_button("Закрыть", "ghost", close=True)
        dlg.exec()

    def tester(self) -> None:
        dlg = Modal(self.app, "Тестировщик", width=340)
        nick = QLabel("Hiho")
        nick.setProperty("kind", "h2")
        nick.setAlignment(Qt.AlignCenter)
        dlg.body.addWidget(nick)
        dlg.add_button("TikTok", "primary", lambda: self.app.call("link:open", "tiktok", None, None))
        dlg.add_button("Закрыть", "ghost", close=True)
        dlg.exec()

    def _tone_changed(self, tone: str) -> None:
        self.app.save_settings({"tone": tone})

    def _accent_changed(self, color: str) -> None:
        self._paint_accent(color)
        self.app.save_settings({"accent": color})
        if color:
            self.app.call("achievements:grant", {"id": "accent"}, None, None)

    def _paint_accent(self, cur: str) -> None:
        for c, b in self.accent_btns:
            ring = "2px solid #ffffff" if c == cur else "2px solid transparent"
            b.setStyleSheet(f"background: {c}; border: {ring}; border-radius: 13px; padding: 0;")

    def show_changelog(self) -> None:
        from ..dialogs.changelog import ChangelogDialog
        ChangelogDialog(self.app, self).exec()

    def open_guides(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        d = os.path.join(self.app.ctx.user_data, "guides")
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def selftest(self) -> None:
        p = build_patch(self.form(), 16)
        assert p["ram"] >= 1 and p["lang"] in ("ru", "en")
        update_text(self.app, {"state": "ready", "version": "1"})
        discord_text(self.app, {"state": "off"})
        for d in (MsLoginDialog(self.app, "ABCD1234", "https://microsoft.com/link"),):
            d.deleteLater()
        from ..dialogs.importer import ImportDialog
        ImportDialog(self.app).deleteLater()
