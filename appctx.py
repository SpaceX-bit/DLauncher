"""AppContext — общий объект, который получает каждая страница интерфейса.

    app.call("mods:search", {...}, on_ok, on_err)   # вызов ядра в фоне; колбэки — в потоке интерфейса
    app.t("Русский текст {n}", n=5)                  # перевод (ключ — русский текст)
    app.bind(widget, "Русский текст")                # подпись, которая переключается вместе с языком
    app.settings / app.profiles / app.current_id     # кеш публичных настроек и профилей
    app.event(channel, payload)                      # сигнал: все события ядра (game:status, game:progress, …)
    app.toast("Готово", "ok") / app.confirm("Удалить?")
"""
from __future__ import annotations

import threading
import traceback
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog

from ..core.ctx import UiBridge
from . import i18n


class _Dispatcher(QObject):
    """Живёт в потоке интерфейса; emit из любого потока -> вызов в потоке интерфейса."""
    run = Signal(object)

    def __init__(self):
        super().__init__()
        self.run.connect(self._do, Qt.QueuedConnection)

    @Slot(object)
    def _do(self, fn):
        try:
            fn()
        except Exception:  # noqa: BLE001
            _log_exc("callback")


_LOG = {"ctx": None}


def _log_exc(where: str) -> None:
    tb = traceback.format_exc()
    c = _LOG["ctx"]
    if c is not None:
        c.diag(f"{where}: {tb.strip().splitlines()[-1]}\n{tb}")


class QtBridge(UiBridge):
    """Диалоги и браузер для ядра. Вызывается из рабочих потоков — переходим в поток интерфейса."""

    def __init__(self, app: "AppContext"):
        self.app = app

    def _gui(self, fn):
        return self.app.run_gui(fn)

    @staticmethod
    def _filter(filters):
        if not filters:
            return ""
        return ";;".join(f"{n} ({' '.join('*.' + e for e in exts)})" for n, exts in filters)

    def open_file(self, title="", filters=None, multiple=False):
        def go():
            if multiple:
                files, _ = QFileDialog.getOpenFileNames(self.app.window, title, "", self._filter(filters))
                return files or None
            f, _ = QFileDialog.getOpenFileName(self.app.window, title, "", self._filter(filters))
            return f or None
        return self._gui(go)

    def save_file(self, title="", default_name="", filters=None):
        def go():
            f, _ = QFileDialog.getSaveFileName(self.app.window, title, default_name, self._filter(filters))
            return f or None
        return self._gui(go)

    def open_dir(self, title=""):
        def go():
            d = QFileDialog.getExistingDirectory(self.app.window, title)
            return d or None
        return self._gui(go)

    def set_clipboard_text(self, text):
        self._gui(lambda: QApplication.clipboard().setText(text))

    def set_clipboard_image(self, path):
        from PySide6.QtGui import QImage

        def go():
            img = QImage(path)
            if not img.isNull():
                QApplication.clipboard().setImage(img)
        self._gui(go)

    def open_url(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        self._gui(lambda: QDesktopServices.openUrl(QUrl(url)))

    def open_path(self, path):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        self._gui(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))


class AppContext(QObject):
    settings_changed = Signal(dict)
    profiles_changed = Signal()
    lang_changed = Signal()
    event = Signal(str, object)

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.ctx = api.ctx
        _LOG["ctx"] = self.ctx
        self.window = None            # главное окно (QMainWindow), ставит MainWindow
        self.settings: dict = {}
        self.profiles: list[dict] = []
        self.current_id: str | None = None
        self._pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="dl-call")
        self._disp = _Dispatcher()
        self._gui_thread = threading.current_thread()
        self._bound: list[tuple] = []
        self.ctx.ui = QtBridge(self)
        self.ctx.on("*", self._core_event)
        try:
            self.settings = api.call("settings:get")
            lst = api.call("profiles:list")
            self.profiles, self.current_id = lst["profiles"], lst["current"]
        except Exception:  # noqa: BLE001
            _log_exc("AppContext init")

    # ---------- потоки ----------
    def post(self, fn: Callable[[], None]) -> None:
        """Выполнить fn в потоке интерфейса (можно вызывать из любого потока)."""
        self._disp.run.emit(fn)

    def run_gui(self, fn: Callable[[], Any]) -> Any:
        """Выполнить fn в потоке интерфейса и дождаться результата (для диалогов из рабочих потоков)."""
        if threading.current_thread() is self._gui_thread:
            return fn()
        fut: Future = Future()

        def go():
            try:
                fut.set_result(fn())
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)
        self._disp.run.emit(go)
        return fut.result()

    def call(self, channel: str, payload: Any = None, on_ok: Callable | None = None,
             on_err: Callable[[str], None] | None = None) -> None:
        """Вызов ядра в фоновом потоке. on_ok(result) и on_err(текст) вызываются в потоке интерфейса."""
        def work():
            try:
                res = self.api.call(channel, payload)
            except Exception as e:  # noqa: BLE001
                msg = str(e) or e.__class__.__name__
                self.ctx.diag(f"call {channel}: {msg}")
                if on_err is not None:
                    self.post(lambda: on_err(msg))
                return
            if on_ok is not None:
                self.post(lambda: on_ok(res))
        self._pool.submit(work)

    def call_sync(self, channel: str, payload: Any = None) -> Any:
        """Только для быстрых локальных вызовов (чтение настроек). Сетевые — только через call()."""
        return self.api.call(channel, payload)

    def _core_event(self, channel: str, payload: Any) -> None:
        self.post(lambda: self.event.emit(channel, payload))

    # ---------- настройки и профили ----------
    @property
    def lang(self) -> str:
        return "en" if self.settings.get("lang") == "en" else "ru"

    def refresh_settings(self, cb: Callable[[dict], None] | None = None) -> None:
        def ok(s):
            self._set_settings(s)
            if cb:
                cb(s)
        self.call("settings:get", None, ok)

    def save_settings(self, patch: dict, on_ok: Callable[[dict], None] | None = None,
                      on_err: Callable[[str], None] | None = None) -> None:
        def ok(s):
            self._set_settings(s)
            if on_ok:
                on_ok(s)
        self.call("settings:set", patch, ok, on_err or (lambda m: self.toast(m, "err")))

    def _set_settings(self, s: dict) -> None:
        old = self.lang
        self.settings = s
        self.settings_changed.emit(s)
        if self.lang != old:
            self._rebind()
            self.lang_changed.emit()

    def refresh_profiles(self, cb: Callable[[], None] | None = None) -> None:
        def ok(r):
            self.profiles, self.current_id = r["profiles"], r["current"]
            self.profiles_changed.emit()
            if cb:
                cb()
        self.call("profiles:list", None, ok)

    def current_profile(self) -> dict | None:
        for p in self.profiles:
            if p.get("id") == self.current_id:
                return p
        return None

    def find_profile(self, pid: str | None) -> dict | None:
        for p in self.profiles:
            if p.get("id") == pid:
                return p
        return None

    # ---------- перевод ----------
    def t(self, text: str, **kw) -> str:
        out = i18n.translate(text, self.lang)
        if kw:
            try:
                out = out.format(**kw)
            except Exception:  # noqa: BLE001
                pass
        return out

    def L(self, ru: str, en: str) -> str:
        return en if self.lang == "en" else ru

    def locale(self) -> str:
        return "en-US" if self.lang == "en" else "ru-RU"

    _PROPS = {
        "text": "setText", "placeholder": "setPlaceholderText", "tooltip": "setToolTip",
        "windowTitle": "setWindowTitle", "title": "setTitle",
    }

    def bind(self, widget, ru: str, prop: str = "text") -> None:
        """Поставить подпись и запомнить, чтобы пересчитать при смене языка."""
        getattr(widget, self._PROPS[prop])(self.t(ru))
        self._bound.append((weakref.ref(widget), ru, prop))

    def _rebind(self) -> None:
        alive = []
        for ref, ru, prop in self._bound:
            w = ref()
            if w is None:
                continue
            try:
                getattr(w, self._PROPS[prop])(self.t(ru))
                alive.append((ref, ru, prop))
            except RuntimeError:
                pass  # Qt-объект уже удалён
        self._bound = alive

    # ---------- окна и уведомления ----------
    def toast(self, text: str, kind: str = "info") -> None:
        if self.window is not None and hasattr(self.window, "show_toast"):
            self.window.show_toast(self.t(text), kind)

    def show_page(self, key: str) -> None:
        if self.window is not None and hasattr(self.window, "show_page"):
            self.window.show_page(key)

    def confirm(self, text_ru: str, ok_ru: str = "Да", cancel_ru: str = "Отмена", danger: bool = False, **kw) -> bool:
        from .widgets import Modal, label
        dlg = Modal(self, "Подтверждение", width=420)
        lb = label(self, None, wrap=True)
        lb.setText(self.t(text_ru, **kw))
        dlg.body.addWidget(lb)
        dlg.add_button(cancel_ru, "ghost", close=False).clicked.connect(dlg.reject)
        dlg.add_button(ok_ru, "danger" if danger else "primary").clicked.connect(dlg.accept)
        return dlg.exec() == dlg.Accepted

    def info(self, title_ru: str, text: str) -> None:
        from .widgets import Modal, label
        dlg = Modal(self, title_ru, width=460)
        lb = label(self, None, wrap=True, selectable=True)
        lb.setText(text)
        dlg.body.addWidget(lb)
        dlg.add_button("Закрыть", "primary").clicked.connect(dlg.accept)
        dlg.exec()

    def ask_text(self, title_ru: str, label_ru: str, default: str = "", placeholder_ru: str = "") -> str | None:
        from PySide6.QtWidgets import QLineEdit
        from .widgets import Modal, label
        dlg = Modal(self, title_ru, width=420)
        dlg.body.addWidget(label(self, label_ru, "muted", wrap=True))
        ed = QLineEdit(default)
        if placeholder_ru:
            self.bind(ed, placeholder_ru, "placeholder")
        dlg.body.addWidget(ed)
        dlg.add_button("Отмена", "ghost").clicked.connect(dlg.reject)
        dlg.add_button("OK", "primary").clicked.connect(dlg.accept)
        ed.returnPressed.connect(dlg.accept)
        ed.setFocus()
        return ed.text().strip() if dlg.exec() == dlg.Accepted else None
