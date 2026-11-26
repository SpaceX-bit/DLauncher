"""Вкладка «Играть»: выбор профиля, запуск, прогресс, быстрый вход, статистика, новости, консоль."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from .. import i18n
from ..widgets import Card, ClickLabel, VScroll, button, clear_layout, label
from ..buildcard import BuildCard, recent_first
from ._profile_util import fmt_dur, get_page, loader_name

i18n.register({
    "Обновляю моды...": "Updating mods...",
    "Моды обновлены: {n}": "Mods updated: {n}",
    "Играть": "Play",
    "Запуск...": "Starting...",
    "Игра запущена": "Game is running",
    "Выбранный профиль": "Selected profile",
    "Создать профиль": "Create a profile",
    "Сначала создай профиль": "Create a profile first",
    "Быстрый вход на сервер": "Quick join a server",
    "Последний сервер": "Last server",
    "Не заходить на сервер": "Don't join a server",
    "Статистика": "Statistics",
    "Всего сыграно": "Total playtime",
    "Запусков": "Launches",
    "Любимый профиль": "Favorite profile",
    "Новости Minecraft": "Minecraft news",
    "Обновить": "Refresh",
    "Консоль": "Console",
    "Загрузка...": "Loading...",
    "Профилей пока нет. Создай первый — это быстро.": "No profiles yet. Create your first one — it's quick.",
    "Игра завершилась с ошибкой": "The game crashed",
    "Разобрать причину": "Find the cause",
    "Закрыть": "Close",
    "Версия: {v} · {l}": "Version: {v} · {l}",
    "Последний запуск: {d}": "Last played: {d}",
    "Ни разу не запускался": "Never played",
    "Нет данных": "No data",
    "Недавние сборки": "Recent builds",
    "Все сборки": "All builds",
    "Моды": "Mods",
    "Логи": "Logs",
    "Папка": "Folder",
    "Настройки": "Settings",
})


class PlayPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.launching = False
        self._news_items: list[dict] = []
        self._servers: list[dict] = []
        self._last_server = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ----- прокручиваемая часть: недавние сборки, статистика, новости
        scroll = VScroll()
        root.addWidget(scroll, 1)
        head = QHBoxLayout()
        head.addWidget(label(app, "Недавние сборки", "h3"))
        head.addStretch(1)
        head.addWidget(button(app, "Все сборки", "small", lambda: self.app.show_page("profiles")))
        scroll.lay.addLayout(head)
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        scroll.lay.addLayout(self.grid)
        self.empty = label(app, "Профилей пока нет. Создай первый — это быстро.", "muted", wrap=True)
        scroll.lay.addWidget(self.empty)
        self.btn_create = button(app, "Создать профиль", "primary", self._open_create)
        scroll.lay.addWidget(self.btn_create, 0, Qt.AlignLeft)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.stats_card = Card()
        self.stats_card.lay.addWidget(label(app, "Статистика", "h3"))
        self.stats_body = QVBoxLayout()
        self.stats_card.lay.addLayout(self.stats_body)
        self.stats_card.lay.addStretch(1)
        cards.addWidget(self.stats_card, 1)
        self.news_card = Card()
        nh = QHBoxLayout()
        nh.addWidget(label(app, "Новости Minecraft", "h3"))
        nh.addStretch(1)
        nh.addWidget(button(app, "Обновить", "small", lambda: self.load_news(True)))
        self.news_card.lay.addLayout(nh)
        self.news_body = QVBoxLayout()
        self.news_card.lay.addLayout(self.news_body)
        cards.addWidget(self.news_card, 2)
        scroll.lay.addLayout(cards)
        scroll.lay.addStretch(1)

        # ----- нижняя панель запуска
        bar = QFrame()
        bar.setObjectName("launchbar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(10)
        info = QVBoxLayout()
        info.setSpacing(0)
        self.cur_name = QLabel("")
        self.cur_name.setStyleSheet("font-size: 16px; font-weight: 800; background: transparent;")
        info.addWidget(self.cur_name)
        self.info = label(app, None, "muted")
        info.addWidget(self.info)
        row.addLayout(info, 1)
        self.server_combo = QComboBox()
        self.server_combo.setMinimumWidth(200)
        self.server_wrap = self.server_combo
        row.addWidget(self.server_combo)
        row.addWidget(button(app, "Моды", "ghost", lambda: self.app.show_page("installed")))
        row.addWidget(button(app, "Логи", "ghost", self._open_console))
        row.addWidget(button(app, "Папка", "ghost", self._open_folder))
        row.addWidget(button(app, "Настройки", "ghost", lambda: self.app.show_page("profiles")))
        self.play = button(app, "Играть", "play", self.start)
        row.addWidget(self.play)
        bl.addLayout(row)
        self.status = label(app, None, "muted", wrap=True)
        bl.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        bl.addWidget(self.bar)
        root.addWidget(bar)

        app.profiles_changed.connect(self.refresh)
        app.settings_changed.connect(lambda _s: self._fill_info())
        app.event.connect(self._on_event)
        self.refresh()
        QTimer.singleShot(1500, self.load_news)

    # ---------- события ядра ----------
    def _on_event(self, channel: str, payload):
        if channel == "game:status":
            self.status.setText(self.app.t(str(payload or "")))
        elif channel == "game:progress" and isinstance(payload, dict):
            total = int(payload.get("total") or 0)
            if total > 0:
                self.bar.show()
                self.bar.setValue(int(100 * int(payload.get("task") or 0) / total))
                lab = payload.get("label") or payload.get("type") or ""
                self.status.setText(f"{self.app.t('Загрузка...')} {lab} {payload.get('task', 0)}/{total}")
        elif channel == "game:closed" and isinstance(payload, dict):
            self._finished(payload)
        elif channel == "server:last":
            self.app.refresh_profiles()
        elif channel == "tray:play":
            self.start()

    def _finished(self, payload: dict) -> None:
        self.launching = False
        self.play.setEnabled(True)
        self.bar.hide()
        self.status.setText("")
        self.app.bind(self.play, "Играть")
        self.load_stats()
        code = payload.get("code")
        if code not in (0, None):
            self._offer_crash(payload)

    def _offer_crash(self, payload: dict) -> None:
        try:
            from ..dialogs.crash import CrashDialog
            CrashDialog(self.app, payload.get("profileId"), payload.get("code")).show()
        except Exception as e:  # noqa: BLE001
            self.app.ctx.diag(f"crash dialog: {e}")

    # ---------- профили ----------
    def refresh(self) -> None:
        app = self.app
        clear_layout(self.grid)
        has = bool(app.profiles)
        ordered = recent_first(app.profiles)
        # выбранная сборка всегда в списке, остальные — самые недавние
        shown = [p for p in ordered if p["id"] == app.current_id][:1] + [p for p in ordered if p["id"] != app.current_id]
        for i, p in enumerate(shown[:6]):
            c = BuildCard(app, p, selected=p["id"] == app.current_id)
            c.chosen.connect(self._choose)
            c.play.connect(lambda _pid: self.start())
            self.grid.addWidget(c, i // 2, i % 2)
            c.load_status()
        self.empty.setVisible(not has)
        self.btn_create.setVisible(not has)
        self.server_combo.setVisible(has)
        self.play.setEnabled(has and not self.launching)
        self._fill_info()
        self.load_servers()

    def _choose(self, pid: str) -> None:
        if pid and pid != self.app.current_id:
            self.app.call("profiles:select", pid, lambda _r: self.app.refresh_profiles(), lambda m: self.app.toast(m, "err"))

    def _open_folder(self) -> None:
        self.app.call("folder:open", {"which": "instance"}, None, lambda m: self.app.toast(m, "err"))

    def _fill_info(self) -> None:
        p = self.app.current_profile()
        if not p:
            self.cur_name.setText("")
            self.info.setText("")
            return
        self.cur_name.setText(str(p.get("name") or ""))
        self.info.setText(f"{p.get('version', '')} · {loader_name(p.get('loader', 'vanilla'))}")

    def load_servers(self) -> None:
        p = self.app.current_profile()
        self.server_combo.clear()
        self.server_combo.addItem(self.app.t("Не заходить на сервер"), None)
        self._servers = []
        if not p:
            return

        def ok(r):
            if not isinstance(r, dict) or not r.get("ok"):
                return
            self._servers = r.get("servers") or []
            last = r.get("last")
            self.server_combo.clear()
            self.server_combo.addItem(self.app.t("Не заходить на сервер"), None)
            if last:
                self.server_combo.addItem(f"{self.app.t('Последний сервер')}: {last['host']}:{last['port']}", {"host": last["host"], "port": last["port"]})
            for s in self._servers:
                self.server_combo.addItem(f"{'★ ' if s.get('favorite') else ''}{s['name']} ({s['host']}:{s['port']})", {"host": s["host"], "port": s["port"]})
        self.app.call("servers:list", {"profileId": p["id"]}, ok, lambda m: None)

    # ---------- запуск ----------
    def _open_create(self) -> None:
        self.app.show_page("profiles")
        page = get_page(self.app, "profiles")
        fn = getattr(page, "open_create", None)
        if callable(fn):
            fn()

    def start(self) -> None:
        if self.launching:
            return
        p = self.app.current_profile()
        if not p:
            self.app.toast("Сначала создай профиль", "warn")
            self._open_create()
            return
        try:
            from ..dialogs.compat import pre_launch_check
        except Exception:  # noqa: BLE001
            pre_launch_check = None
        if pre_launch_check is None:
            self._do_launch(p)
        else:
            pre_launch_check(self.app, p, lambda: self._do_launch(p))

    def _do_launch(self, p: dict) -> None:
        if self.launching:
            return
        if os.environ.get("DLAUNCHER_SELFTEST"):
            return self._do_launch_checked(p)
        self.play.setEnabled(False)

        def got(r):
            self.play.setEnabled(True)
            warns = (r or {}).get("warnings") or [] if isinstance(r, dict) else []
            if warns:
                from ..dialogs.extras import preflight_ok
                if not preflight_ok(self.app, warns):
                    return
            self._do_launch_checked(p)
        self.app.call("launch:preflight", {"profileId": p["id"]}, got, lambda m: (self.play.setEnabled(True), self._do_launch_checked(p)))

    def _do_launch_checked(self, p: dict) -> None:
        if self.launching:
            return
        self.launching = True
        self.play.setEnabled(False)
        if self.app.settings.get("autoUpdateMods") is True:  # сначала обновляем моды, потом запускаем
            self.app.bind(self.play, "Обновляю моды...")

            def done(r):
                if isinstance(r, dict) and r.get("ok") and r.get("updated"):
                    self.app.toast(self.app.t("Моды обновлены: {n}", n=r["updated"]), "ok")
                self._launch_now(p)
            self.app.call("installed:autoupdate", {"profileId": p["id"]}, done, lambda m: self._launch_now(p))
            return
        self._launch_now(p)

    def _launch_now(self, p: dict) -> None:
        self.app.bind(self.play, "Запуск...")
        self.bar.hide()
        payload = {"profileId": p["id"]}
        server = self.server_combo.currentData()
        if server:
            payload.update(quickJoin=True, server=server)

        def ok(r):
            if isinstance(r, dict) and r.get("ok"):
                self.app.bind(self.play, "Игра запущена")
                self.bar.hide()
                self.app.refresh_profiles()
                return
            self._failed((r or {}).get("error") or "Не удалось запустить игру")

        self.app.call("game:launch", payload, ok, self._failed)

    def _failed(self, msg: str) -> None:
        self.launching = False
        self.play.setEnabled(bool(self.app.profiles))
        self.app.bind(self.play, "Играть")
        self.bar.hide()
        self.status.setText("")
        self.app.toast(msg, "err")

    # ---------- статистика ----------
    def on_show(self) -> None:
        self.load_stats()

    def load_stats(self) -> None:
        def ok(r):
            clear_layout(self.stats_body)
            if not isinstance(r, dict) or not r.get("ok"):
                return
            total = r.get("total") or {}
            if not total.get("launches") and not total.get("ms"):
                self.stats_body.addWidget(label(self.app, "Нет данных", "muted"))
                return
            self.stats_body.addWidget(self._kv("Всего сыграно", fmt_dur(self.app, total.get("ms"))))
            self.stats_body.addWidget(self._kv("Запусков", str(total.get("launches", 0))))
            top = next((i for i in r.get("items") or [] if i["id"] == r.get("top")), None)
            if top:
                self.stats_body.addWidget(self._kv("Любимый профиль", str(top["name"])))
        self.app.call("stats:get", None, ok, lambda m: None)

    def _kv(self, k_ru: str, v: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(label(self.app, k_ru, "muted"))
        h.addStretch(1)
        vl = QLabel(v)
        vl.setProperty("kind", "accent")
        h.addWidget(vl)
        return w

    # ---------- новости ----------
    def load_news(self, force: bool = False) -> None:
        clear_layout(self.news_body)
        self.news_body.addWidget(label(self.app, "Загрузка...", "muted"))

        def ok(r):
            clear_layout(self.news_body)
            if not isinstance(r, dict) or not r.get("ok"):
                lb = label(self.app, None, "muted", wrap=True)
                lb.setText(self.app.t((r or {}).get("error") or "Не удалось загрузить новости."))
                self.news_body.addWidget(lb)
                return
            self._news_items = r["items"]
            for it in self._news_items[:8]:
                self.news_body.addWidget(self._news_row(it))

        def err(m):
            clear_layout(self.news_body)
            lb = label(self.app, None, "muted", wrap=True)
            lb.setText(m)
            self.news_body.addWidget(lb)
        self.app.call("news:list", {"force": force}, ok, err)

    def _news_row(self, it: dict) -> QWidget:
        w = Card("soft", margins=(12, 8, 12, 8), spacing=2)
        t = ClickLabel(it["title"])
        t.setProperty("kind", "accent")
        t.setCursor(Qt.PointingHandCursor)
        t.setWordWrap(True)
        t.clicked.connect(lambda i=it: self._read_news(i))
        w.lay.addWidget(t)
        if it.get("text"):
            d = QLabel(it["text"][:140])
            d.setProperty("kind", "muted")
            d.setWordWrap(True)
            w.lay.addWidget(d)
        return w

    def _read_news(self, it: dict) -> None:
        from ..widgets import Modal

        def ok(r):
            dlg = Modal(self.app, it["title"], width=640, height=480)
            dlg.title.setText(it["title"])
            from PySide6.QtWidgets import QPlainTextEdit
            te = QPlainTextEdit()
            te.setReadOnly(True)
            te.setPlainText((r or {}).get("body") or (r or {}).get("error") or "")
            dlg.body.addWidget(te, 1)
            dlg.add_button("Закрыть", "primary", close=True)
            dlg.exec()
        self.app.call("news:read", {"id": it["id"]}, ok, lambda m: self.app.toast(m, "err"))

    def _open_console(self) -> None:
        from ..dialogs.console import ConsoleDialog
        dlg = ConsoleDialog(self.app)
        dlg.show()
        self._console = dlg

    def retranslate(self) -> None:
        self.refresh()
        self.load_news()
        self.load_stats()

    def selftest(self) -> None:
        from ..dialogs.console import ConsoleDialog
        ConsoleDialog(self.app)
        try:
            from ..dialogs.crash import CrashDialog
            CrashDialog(self.app, None, 1)
        except ImportError:
            raise
