"""Запуск приложения Qt: одна копия, окно, самопроверка."""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from ..api import Api
from ..resources import asset

SERVER_NAME = "DLauncher-single-instance"


def _single_instance(app: QApplication):
    """Возвращает (lock, server) для первой копии или None, если уже запущена другая (ей отправлен сигнал)."""
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "dlauncher.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(150):
        s = QLocalSocket()
        s.connectToServer(SERVER_NAME)
        if s.waitForConnected(800):
            s.write(b"show")
            s.waitForBytesWritten(500)
            s.disconnectFromServer()
        return None
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)
    return lock, server


def _hard_exit(code: int) -> None:
    """Завершаем процесс сразу: фоновые сетевые вызовы не должны держать закрытый лаунчер в памяти."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(int(code or 0))


def _exit_watchdog(seconds: float = 6.0) -> None:
    """Если завершение (остановка служб) зависнет — всё равно выходим."""
    import threading
    t = threading.Timer(seconds, lambda: os._exit(0))
    t.daemon = True
    t.start()


def run(argv: list[str], selftest: bool = False, hidden: bool = False) -> int:
    def say(msg: str) -> None:
        if selftest:
            print("selftest:", msg, flush=True)

    say("qapplication")
    app = QApplication(sys.argv[:1] + [a for a in argv if a.startswith("-platform")])
    app.setApplicationName("DLauncher")
    app.setWindowIcon(QIcon(asset("icon.png")))
    app.setQuitOnLastWindowClosed(False)

    holder = None
    if selftest:
        os.environ["DLAUNCHER_SELFTEST"] = "1"
    if not selftest:
        holder = _single_instance(app)
        if holder is None:
            return 0

    ud = os.environ.get("DLAUNCHER_DATA")
    from ..core.ctx import Ctx
    say("core")
    ctx = Ctx(user_data=ud) if ud else Ctx()
    api = Api(ctx)
    say("core ready")

    def hook(et, ev, tb):
        ctx.diag("UNCAUGHT: " + "".join(traceback.format_exception(et, ev, tb))[-1800:])
    sys.excepthook = hook

    from .appctx import AppContext
    from .mainwindow import MainWindow
    say("window")
    actx = AppContext(api)
    win = MainWindow(actx, start_hidden=hidden)
    say("window ready")
    ctx.diag("started" + (" (selftest)" if selftest else ""))

    if selftest:
        from .selftest import run_selftest
        code = run_selftest(app, actx, win, api)
        _hard_exit(code)  # без api.shutdown(): в самопроверке не нужно, а фоновые вызовы могут держать процесс
        return code

    if holder is not None:
        _lock, server = holder

        def on_conn():
            sock = server.nextPendingConnection()
            if sock is not None:
                sock.readyRead.connect(win.bring_to_front)
        server.newConnection.connect(on_conn)

    if not hidden or win.tray is None:
        win.show()
    app.aboutToQuit.connect(lambda: (_exit_watchdog(), api.shutdown()))
    code = app.exec()
    if holder is not None:
        holder[0].unlock()
    _hard_exit(code)
    return code
