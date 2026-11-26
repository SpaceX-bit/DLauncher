"""Точка входа DLauncher (Python + PySide6).

    python main.py               — обычный запуск
    python main.py --hidden      — запуск свёрнутым в трей (автозапуск)
    python main.py --selftest    — самопроверка интерфейса без показа окна (для CI), код выхода 0/1
"""
from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _log_crash(text: str) -> None:
    try:
        from dlauncher.core.ctx import default_user_data
        d = default_user_data()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "launcher.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:  # noqa: BLE001
        pass


def _utf8_streams() -> None:
    """В Windows при выводе в трубу (CI) кодировка cp1252 — русские буквы роняют print(). Включаем UTF-8."""
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str]) -> int:
    _utf8_streams()
    selftest = "--selftest" in argv
    hidden = "--hidden" in argv
    if selftest:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if sys.platform == "win32":  # без шрифтов в offscreen все буквы на снимках — квадраты
            os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
        print("selftest: start", flush=True)
    try:
        from dlauncher.ui.app import run
        return run(argv, selftest=selftest, hidden=hidden)
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        tb = traceback.format_exc()
        _log_crash("FATAL: " + tb)
        if selftest:  # в самопроверке окно с сообщением никто не закроет — просто печатаем ошибку
            print("SELFTEST FATAL:", tb, flush=True)
            return 1
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(argv)
            QMessageBox.critical(None, "DLauncher", "Не удалось запустить DLauncher.\n\n" + tb[-1500:])
        except Exception:  # noqa: BLE001
            print(tb, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
