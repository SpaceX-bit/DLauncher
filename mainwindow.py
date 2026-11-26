"""Главное окно: фон, панель вкладок, страницы, уведомления, значок в трее."""
from __future__ import annotations

import importlib
import os
import traceback

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QIcon, QLinearGradient, QMovie, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
                               QMenu, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from ..resources import asset
from . import theme
from .widgets import button

# (ключ, подпись, модуль, класс) — страницы лежат в ui/pages/*.py и подгружаются по одной:
# если одна упадёт при создании, остальные работают, а ошибка попадает в launcher.log и в самопроверку.
PAGE_SPECS = [
    ("play", "Играть", "dlauncher.ui.pages.play", "PlayPage"),
    ("profiles", "Профили", "dlauncher.ui.pages.profiles", "ProfilesPage"),
    ("mods", "Моды", "dlauncher.ui.pages.mods", "ModsPage"),
    ("installed", "Установлено", "dlauncher.ui.pages.installed", "InstalledPage"),
    ("worlds", "Миры", "dlauncher.ui.pages.worlds", "WorldsPage"),
    ("skins", "Скины", "dlauncher.ui.pages.skins", "SkinsPage"),
    ("achievements", "Достижения", "dlauncher.ui.pages.achievements", "AchievementsPage"),
    ("settings", "Настройки", "dlauncher.ui.pages.settings", "SettingsPage"),
]


# значки боковой панели (обычные символы Windows — работают без картинок)
RAIL_ICONS = {"play": "\u25B6", "profiles": "\u25A6", "mods": "\u2726", "installed": "\u2611",
              "worlds": "\u25CE", "skins": "\u263A", "achievements": "\u265B", "settings": "\u2699"}


class BackgroundWidget(QWidget):
    """Фон окна: своя картинка/GIF/видео или background.jpg + затемнение."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._pix: QPixmap | None = None
        self._movie: QMovie | None = None
        self._player = None
        self._frame = None
        self._scaled_key = None
        self._scaled: QPixmap | None = None
        self._dim = 0
        self.reload()

    def reload(self) -> None:
        s = self.app.settings
        self._dim = int(s.get("bgDim") or 0)
        self._stop_media()
        path = s.get("bgUrl") or ""
        typ = s.get("bgType") or ""
        if path and os.path.exists(path):
            if typ == "video":
                self._start_video(path)
            elif path.lower().endswith(".gif"):
                self._movie = QMovie(path)
                self._movie.frameChanged.connect(lambda _=0: self.update())
                self._movie.start()
            else:
                self._pix = QPixmap(path)
        self._scaled_key = None
        self.update()

    def _has_media(self) -> bool:
        return self._movie is not None or self._player is not None

    def _stop_media(self) -> None:
        self._pix = None
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:  # noqa: BLE001
                pass
            self._player = None
        self._frame = None

    def _start_video(self, path: str) -> None:
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
            self._player = QMediaPlayer(self)
            sink = QVideoSink(self)
            self._player.setVideoSink(sink)
            sink.videoFrameChanged.connect(self._on_frame)
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.setLoops(QMediaPlayer.Loops.Infinite)
            self._player.play()
        except Exception as e:  # noqa: BLE001
            self.app.ctx.diag(f"video background unavailable: {e}")
            self._player = None

    def _on_frame(self, frame) -> None:
        try:
            self._frame = frame.toImage()
            self.update()
        except Exception:  # noqa: BLE001
            pass

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # основной фон — градиент от чёрного к тёмно-синему (виден, если не выбрана своя картинка)
        base = QLinearGradient(0, 0, self.width(), self.height())
        base.setColorAt(0.0, QColor(theme.GRAD_A))
        base.setColorAt(0.5, QColor(theme.GRAD_B))
        base.setColorAt(1.0, QColor(theme.GRAD_C))
        p.fillRect(self.rect(), base)
        src = None
        if self._movie is not None:
            src = self._movie.currentPixmap()
        elif self._frame is not None:
            src = QPixmap.fromImage(self._frame)
        elif self._pix is not None:
            src = self._pix
        if src is not None and not src.isNull():
            w, h = self.width(), self.height()
            scaled = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled)
        if self._dim:
            p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self._dim / 100)))
        if src is not None:  # поверх картинки — лёгкое затемнение, чтобы текст читался
            g = QLinearGradient(0, 0, 0, self.height())
            g.setColorAt(0.0, QColor(8, 8, 10, 150))
            g.setColorAt(1.0, QColor(8, 8, 10, 215))
            p.fillRect(self.rect(), g)
        p.end()


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text: str, kind: str) -> None:
        color = {"ok": theme.OK, "err": theme.ERR, "warn": theme.WARN}.get(kind, theme.ACCENT)
        self.setStyleSheet(
            f"background: rgba(22,19,38,240); color: {theme.TEXT}; border: 1px solid {color};"
            "border-radius: 12px; padding: 10px 18px; font-weight: 600;")
        self.setText(text)
        self.setFixedWidth(min(560, max(240, self.parent().width() - 80)))
        self.adjustSize()
        self.move((self.parent().width() - self.width()) // 2, self.parent().height() - self.height() - 28)
        self.raise_()
        self.show()
        self._timer.start(4200 if kind != "err" else 7000)


class MainWindow(QMainWindow):
    def __init__(self, app, start_hidden: bool = False):
        super().__init__()
        self.setAcceptDrops(True)  # .mrpack, .jar, .zip и картинки можно бросить в окно
        self.app = app
        app.window = self
        self.pages: dict[str, QWidget] = {}
        self.page_errors: dict[str, str] = {}
        self._nav: dict[str, QPushButton] = {}
        self._quitting = False
        self.setWindowTitle("DLauncher")
        self.setWindowIcon(QIcon(asset("icon.png")))
        self.resize(1280, 760)
        self.setMinimumSize(1000, 600)

        self.bg = BackgroundWidget(app)
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)

        # верхняя панель: название, быстрый запуск выбранной сборки, аккаунт
        top = QHBoxLayout()
        top.setSpacing(10)
        logo = QLabel("DLauncher")
        logo.setStyleSheet("font-size: 15px; font-weight: 800; color: #fff;")
        top.addWidget(logo)
        ver = QLabel("v" + app.ctx.app_version)
        ver.setProperty("kind", "muted")
        top.addWidget(ver)
        top.addStretch(1)
        self.pill = QFrame()
        self.pill.setObjectName("pill")
        pl = QHBoxLayout(self.pill)
        pl.setContentsMargins(6, 3, 6, 3)
        pl.setSpacing(2)
        self.pill_name = QPushButton("—")
        self.pill_name.setProperty("kind", "pill")
        self.pill_name.setCursor(Qt.PointingHandCursor)
        self.pill_name.clicked.connect(lambda: self.show_page("profiles"))
        pl.addWidget(self.pill_name)
        self.pill_play = QPushButton("\u25B6")
        self.pill_play.setProperty("kind", "pill")
        self.pill_play.setCursor(Qt.PointingHandCursor)
        self.pill_play.clicked.connect(lambda: self.app.event.emit("tray:play", None))
        pl.addWidget(self.pill_play)
        top.addWidget(self.pill)
        top.addStretch(1)
        self.account_btn = QPushButton("")
        self.account_btn.setProperty("kind", "pill")
        self.account_btn.setCursor(Qt.PointingHandCursor)
        self.account_btn.clicked.connect(lambda: self.show_page("settings"))
        top.addWidget(self.account_btn)
        self.others_btn = QPushButton(app.t("Другие лаунчеры"))
        self.others_btn.setProperty("kind", "pill")
        self.others_btn.setCursor(Qt.PointingHandCursor)
        self.others_btn.clicked.connect(self._other_launchers)
        top.addWidget(self.others_btn)
        root.addLayout(top)
        self.tour = None

        # левая панель с иконками + страницы
        body = QHBoxLayout()
        body.setSpacing(10)
        root.addLayout(body, 1)
        rail = QFrame()
        rail.setObjectName("rail")
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(6, 8, 6, 8)
        rl.setSpacing(2)
        body.addWidget(rail)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        for key, ru, mod, cls in PAGE_SPECS:
            b = button(app, "", "rail", checkable=True)
            b.setText(f"{RAIL_ICONS.get(key, '•')}\n{app.t(ru)}")
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            b.setToolTip(app.t(ru))
            rl.addWidget(b)
            self._nav[key] = b
            self.stack.addWidget(self._make_page(key, mod, cls))
        rl.addStretch(1)
        # кнопка «Обучение»: Стив-помощник рассказывает про весь лаунчер, потом даёт выбрать тему
        self.tour_btn = button(app, "", "rail")
        self.tour_btn.setText("\u2605\n" + app.t("Обучение"))
        self.tour_btn.clicked.connect(lambda _=False: self.start_tour("overview"))
        rl.addWidget(self.tour_btn)

        self.toast_label = Toast(self.bg)
        from .achievements_ui import AchievementToast
        self.achv_toast = AchievementToast(app, self.bg)
        app.lang_changed.connect(self._on_lang)
        app.settings_changed.connect(self._on_settings)
        app.profiles_changed.connect(self._sync_top)
        self._sync_top()
        self._apply_style()
        self._make_tray()
        app.event.connect(self._on_event)
        self.show_page("play")
        if start_hidden and self.tray is not None:
            self.hide()
        else:
            QTimer.singleShot(1500, self._offer_import)
            QTimer.singleShot(3500, self._auto_tour)
            QTimer.singleShot(7000, self._show_changelog)

    # ---------- перетаскивание файлов в окно ----------
    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        e.acceptProposedAction()
        try:
            from .dialogs.extras import handle_drop
            QTimer.singleShot(0, lambda: handle_drop(self.app, paths))
        except Exception:  # noqa: BLE001
            self.app.ctx.diag(f"drop: {traceback.format_exc()}")

    def _offer_import(self) -> None:
        """Через пару секунд после старта предлагает импорт сборок из других лаунчеров (один раз)."""
        if os.environ.get("DLAUNCHER_SELFTEST"):
            return
        try:
            from .dialogs.importer import maybe_show_on_start
            maybe_show_on_start(self.app)
        except Exception:  # noqa: BLE001
            self.app.ctx.diag(f"offer_import: {traceback.format_exc()}")

    def _show_changelog(self) -> None:
        """После обновления один раз показывает «Что нового». Новая установка версию просто запоминает."""
        if os.environ.get("DLAUNCHER_SELFTEST") or not self.isVisible():
            return
        try:
            from .. import __version__
            from .dialogs.changelog import ChangelogDialog, should_show
            action = should_show(self.app.settings, __version__)
            if not action:
                return
            if action == "show":
                for w in QApplication.topLevelWidgets():  # идёт другое окно или обучение — подождём
                    if w is not self and w.isVisible() and w.__class__.__name__ in ("ImportDialog", "Modal"):
                        QTimer.singleShot(6000, self._show_changelog)
                        return
                if self.tour is not None:
                    QTimer.singleShot(6000, self._show_changelog)
                    return
                self.app.save_settings({"lastSeenVersion": __version__})
                ChangelogDialog(self.app, self).exec()
            else:
                self.app.save_settings({"lastSeenVersion": __version__})
        except Exception:  # noqa: BLE001
            self.app.ctx.diag(f"changelog: {traceback.format_exc()}")

    # ---------- обучение ----------
    def _auto_tour(self) -> None:
        """Первый запуск: окно «Не хотите пройти обучение?» (Не надо / Да). Да — на главном окне появляется Стив."""
        if os.environ.get("DLAUNCHER_SELFTEST") or not self.isVisible():
            return
        if self.app.settings.get("tourDone") is True or self.tour is not None:
            return
        for w in QApplication.topLevelWidgets():  # окно импорта ещё открыто — подождём
            if w is not self and w.isVisible() and w.__class__.__name__ == "ImportDialog":
                QTimer.singleShot(4000, self._auto_tour)
                return
        try:
            from . import guides
            dlg, answer = guides.build_ask_dialog(self.app)
            dlg.exec()
            self.app.save_settings({"tourDone": True})  # спросили один раз, больше сами не предлагаем
            if answer and answer[0]:
                self.start_tour()
        except Exception:  # noqa: BLE001
            self.app.ctx.diag(f"tour ask: {traceback.format_exc()}")

    def start_tour(self, topic: str | None = None) -> None:
        """Показывает Стива с меню тем (или сразу выбранную тему)."""
        from . import guides
        if self.tour is not None:
            try:
                self.tour.finish()
            except Exception:  # noqa: BLE001
                pass
        self.tour = guides.TourPanel(self.app, self.bg, topic, on_close=self._tour_closed)

    def _other_launchers(self) -> None:
        from .dialogs.launchers import LaunchersDialog
        LaunchersDialog(self.app).exec()

    _upd_dialog = False
    _upd_offered = ""

    def _offer_update(self, info: dict) -> None:
        """Вышла новая версия: окно «Скачать / Позже». Один раз за запуск на каждую версию."""
        ver = str(info.get("version") or "")
        if os.environ.get("DLAUNCHER_SELFTEST") or not ver or ver == self._upd_offered or self._upd_dialog:
            return
        if not self.isVisible() or self.app.ctx.launching or self.tour is not None:
            QTimer.singleShot(60000, lambda: self._offer_update(info))  # занят — предложим чуть позже
            return
        self._upd_offered = ver
        self._upd_dialog = True
        try:
            from .dialogs.update import UpdateDialog
            UpdateDialog(self.app, ver, str(info.get("notes") or ""), self).exec()
        except Exception:  # noqa: BLE001
            self.app.ctx.diag(f"update dialog: {traceback.format_exc()}")
        finally:
            self._upd_dialog = False

    def _tour_closed(self) -> None:
        self.tour = None

    def _on_event(self, channel: str, payload) -> None:
        if channel == "app:quit":
            self.quit_app()
        elif channel == "achievement:unlocked" and isinstance(payload, dict):
            self.achv_toast.push(payload)
        elif channel == "update:status" and isinstance(payload, dict):
            self.app.last_update = payload
            if payload.get("state") == "available" and payload.get("ask"):
                QTimer.singleShot(0, lambda p=payload: self._offer_update(p))
            elif payload.get("state") == "ready" and not self._upd_dialog:
                from .pages.settings import update_text
                self.app.toast(update_text(self.app, payload), "ok")

    # ---------- страницы ----------
    def _make_page(self, key: str, mod: str, cls: str) -> QWidget:
        try:
            m = importlib.import_module(mod)
            page = getattr(m, cls)(self.app)
            self.pages[key] = page
            return page
        except Exception:  # noqa: BLE001
            tb = traceback.format_exc()
            self.page_errors[key] = tb
            self.app.ctx.diag(f"page {key} failed: {tb}")
            ph = QLabel(f"Не удалось открыть вкладку «{key}».\nПодробности записаны в launcher.log.\n\n{tb.strip().splitlines()[-1]}")
            ph.setWordWrap(True)
            ph.setAlignment(Qt.AlignCenter)
            ph.setProperty("kind", "err")
            return ph

    def show_page(self, key: str) -> None:
        keys = [k for k, *_ in PAGE_SPECS]
        if key not in keys:
            return
        self.stack.setCurrentIndex(keys.index(key))
        for k, b in self._nav.items():
            b.setChecked(k == key)
        page = self.stack.currentWidget()
        fn = getattr(page, "on_show", None)
        if callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                self.app.ctx.diag(f"on_show {key}: {traceback.format_exc()}")

    def current_key(self) -> str:
        return [k for k, *_ in PAGE_SPECS][self.stack.currentIndex()]

    # ---------- оформление ----------
    def _apply_style(self) -> None:
        s = self.app.settings
        tone, accent = s.get("tone") or "dark", s.get("accent") or ""
        theme.look(tone, accent)
        QApplication.instance().setStyleSheet(theme.qss(bool(s.get("glass", True)), int(s.get("glassStrength", 60)), tone, accent))
        self.bg.update()

    def _on_settings(self, _s) -> None:
        self._apply_style()
        self.bg.reload()
        self._sync_tray()
        self._sync_top()

    def _sync_top(self) -> None:
        """Верхняя панель: выбранная сборка и аккаунт."""
        p = self.app.current_profile()
        self.pill_name.setText(p["name"] if p else self.app.t("Нет профилей"))
        s = self.app.settings
        if s.get("accountMode") == "microsoft":
            self.account_btn.setText("Microsoft")
        else:
            self.account_btn.setText(str(s.get("nickname") or "Player"))

    def _on_lang(self) -> None:
        for key, ru, _m, _c in PAGE_SPECS:
            b = self._nav.get(key)
            if b is not None:
                b.setText(f"{RAIL_ICONS.get(key, '•')}\n{self.app.t(ru)}")
                b.setToolTip(self.app.t(ru))
        self.tour_btn.setText("\u2605\n" + self.app.t("Обучение"))
        self.others_btn.setText(self.app.t("Другие лаунчеры"))
        self._sync_top()
        for page in self.pages.values():
            fn = getattr(page, "retranslate", None)
            if callable(fn):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    self.app.ctx.diag(f"retranslate: {traceback.format_exc()}")

    def show_toast(self, text: str, kind: str = "info") -> None:
        self.toast_label.show_text(text, kind)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if getattr(self, "tour", None) is not None:
            self.tour.reposition()
        if getattr(self, "achv_toast", None) is not None:
            self.achv_toast.reposition()
        if self.toast_label.isVisible():
            self.toast_label.move((self.width() - self.toast_label.width()) // 2,
                                  self.height() - self.toast_label.height() - 28)

    # ---------- трей ----------
    def _make_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        t = QSystemTrayIcon(QIcon(asset("icon.png")), self)
        t.setToolTip("DLauncher")
        menu = QMenu()
        self._act_play = QAction(self.app.t("Играть"), menu)
        self._act_play.triggered.connect(lambda: (self.bring_to_front(), self.app.event.emit("tray:play", None)))
        self._act_show = QAction(self.app.t("Показать лаунчер"), menu)
        self._act_show.triggered.connect(self.bring_to_front)
        self._act_quit = QAction(self.app.t("Выход"), menu)
        self._act_quit.triggered.connect(self.quit_app)
        menu.addAction(self._act_play)
        menu.addAction(self._act_show)
        menu.addSeparator()
        menu.addAction(self._act_quit)
        t.setContextMenu(menu)
        t.activated.connect(lambda reason: self.bring_to_front() if reason in (
            QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray = t
        self._tray_menu = menu
        self._sync_tray()
        self.app.lang_changed.connect(lambda: (
            self._act_play.setText(self.app.t("Играть")), self._act_show.setText(self.app.t("Показать лаунчер")),
            self._act_quit.setText(self.app.t("Выход"))))

    def _sync_tray(self) -> None:
        if self.tray is None:
            return
        s = self.app.settings
        self.tray.setVisible(bool(s.get("closeToTray") or s.get("autoStart")))

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, e):  # noqa: N802
        if (not self._quitting and self.tray is not None and self.app.settings.get("closeToTray")):
            e.ignore()
            self.hide()
            return
        self._quitting = True
        super().closeEvent(e)
        QApplication.quit()
