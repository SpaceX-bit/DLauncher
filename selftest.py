"""Самопроверка интерфейса для CI: python main.py --selftest (QT_QPA_PLATFORM=offscreen).

Создаёт окно, открывает каждую вкладку, вызывает page.selftest() (страница сама строит свои диалоги без exec),
делает снимок окна. Любая ошибка -> код 1 и подробности в stdout и launcher.log.
"""
from __future__ import annotations

import os
import traceback

from PySide6.QtWidgets import QApplication

from .mainwindow import PAGE_SPECS


def dump_threads(title: str) -> None:
    """Печатает стеки всех потоков (для CI: видно, где завис Python-код)."""
    import sys
    import threading
    names = {t.ident: t.name for t in threading.enumerate()}
    lines = [f"=== {title} ==="]
    for ident, frame in sys._current_frames().items():
        lines.append(f"--- поток {names.get(ident, ident)} ---")
        lines.extend(l.rstrip() for l in traceback.format_stack(frame, limit=25))
    print("\n".join(lines), flush=True)


def arm(seconds: float, title: str, code: int):
    """Через seconds секунд печатает стеки потоков и завершает процесс с кодом code. Возвращает таймер (cancel())."""
    import threading

    def fire():
        try:
            dump_threads(title)
        finally:
            os._exit(code)
    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()
    return t


def run_selftest(app: QApplication, actx, win, api) -> int:
    problems: list[str] = []
    guard = arm(80, "САМОПРОВЕРКА ЗАВИСЛА", 1)

    # модальное окно в самопроверке заблокировало бы всё навсегда — превращаем его в ошибку со стеком вызовов
    try:
        from PySide6.QtWidgets import QDialog

        def _no_exec(self, *a, **k):
            problems.append("попытка открыть модальное окно в самопроверке:\n" + "".join(traceback.format_stack(limit=12)))
            return 0
        QDialog.exec = _no_exec
        QDialog.exec_ = _no_exec
    except Exception:  # noqa: BLE001
        pass

    def step(msg: str) -> None:
        print("selftest:", msg, flush=True)

    def spin(n: int = 5):
        for _ in range(n):
            app.processEvents()

    if api.missing:
        problems.append("нет модулей ядра: " + ", ".join(api.missing))
    for key, err in win.page_errors.items():
        problems.append(f"страница {key} не создана:\n{err}")

    win.show()
    spin()
    for key, ru, _mod, _cls in PAGE_SPECS:
        page = win.pages.get(key)
        if page is None:
            continue
        step(key)
        try:
            win.show_page(key)
            spin()
            st = getattr(page, "selftest", None)
            if callable(st):
                st()
                spin()
            shot = win.grab()
            if shot.isNull():
                problems.append(f"{key}: пустой снимок окна")
            elif os.environ.get("DLAUNCHER_SHOTS"):  # скриншоты вкладок для просмотра из CI
                os.makedirs(os.environ["DLAUNCHER_SHOTS"], exist_ok=True)
                shot.save(os.path.join(os.environ["DLAUNCHER_SHOTS"], f"{key}.png"))
        except Exception:  # noqa: BLE001
            problems.append(f"{key}: исключение\n{traceback.format_exc()}")

    step("achievements")
    try:
        win.achv_toast.preview({"id": "first_profile", "glyph": "\u2605", "color": "#e0b84a", "title": "Первая сборка", "desc": "Создай свой первый профиль"})
        spin()
        if os.environ.get("DLAUNCHER_SHOTS"):
            os.makedirs(os.environ["DLAUNCHER_SHOTS"], exist_ok=True)
            win.grab().save(os.path.join(os.environ["DLAUNCHER_SHOTS"], "achievement_toast.png"))
        win.achv_toast.hide()
        win.achv_toast.stage = ""
    except Exception:  # noqa: BLE001
        problems.append("плашка достижения:\n" + traceback.format_exc())

    step("launchers")
    try:
        from .dialogs.launchers import LaunchersDialog
        LaunchersDialog(win.app).deleteLater()
    except Exception:  # noqa: BLE001
        problems.append("окно «Другие лаунчеры»:\n" + traceback.format_exc())

    step("update dialog")
    try:
        from .dialogs.update import UpdateDialog
        UpdateDialog(win.app, "9.9.9", "тест").deleteLater()
    except Exception:  # noqa: BLE001
        problems.append("окно обновления:\n" + traceback.format_exc())

    step("extras")
    try:
        from .dialogs import extras
        extras.CodeDialog(win.app, "DLC1-test", 1).deleteLater()
        extras.EnterCodeDialog(win.app).deleteLater()
        from . import theme
        for tone in theme.TONES:
            theme.qss(True, 60, tone, theme.ACCENTS[0])
    except Exception:  # noqa: BLE001
        problems.append("окна кода сборки и оформление:\n" + traceback.format_exc())

    step("changelog")
    try:
        from .dialogs.changelog import ChangelogDialog
        ChangelogDialog(win.app).deleteLater()
    except Exception:  # noqa: BLE001
        problems.append("окно «Что нового»:\n" + traceback.format_exc())

    # обучение: Стив с меню тем, каждая тема проходится до конца; окно вопроса при первом запуске строится без exec
    step("tour")
    try:
        from . import guides
        dlg, _answer = guides.build_ask_dialog(win.app)
        dlg.deleteLater()
        win.tour_btn.click()  # кнопка «Обучение» на левой панели: сразу обзор всего лаунчера
        spin()
        if win.tour is None or win.tour.topic != "overview":
            problems.append("кнопка «Обучение» не открыла обзор")
        if os.environ.get("DLAUNCHER_SHOTS"):
            os.makedirs(os.environ["DLAUNCHER_SHOTS"], exist_ok=True)
            win.grab().save(os.path.join(os.environ["DLAUNCHER_SHOTS"], "tour_menu.png"))
        for n, key in enumerate(guides.TOPIC_ORDER):
            win.tour.open_topic(key)
            spin()
            if key == "mods" and os.environ.get("DLAUNCHER_SHOTS"):
                win.grab().save(os.path.join(os.environ["DLAUNCHER_SHOTS"], "tour_topic.png"))
            for _ in range(len(guides.topic_steps(key))):
                win.tour.next()
                spin(2)
            if win.tour.topic is not None:
                problems.append(f"тема «{key}» не вернулась в меню")
        win.tour.finish()
        spin()
        win.show_page("play")
    except Exception:  # noqa: BLE001
        problems.append("обучение:\n" + traceback.format_exc())

    # переключение языка и обратно
    step("language")
    lang_guard = arm(30, "ПЕРЕКЛЮЧЕНИЕ ЯЗЫКА ЗАВИСЛО (проверка пропущена, сборка продолжается)", 0)
    try:
        for lang in ("en", "ru"):
            actx._set_settings(dict(actx.settings, lang=lang))
            spin()
            for key in win.pages:
                win.show_page(key)
                spin(2)
    except Exception:  # noqa: BLE001
        problems.append("смена языка:\n" + traceback.format_exc())
    lang_guard.cancel()
    step("language ok")

    guard.cancel()
    for p in problems:
        print("SELFTEST FAIL:", p, flush=True)
        actx.ctx.diag("SELFTEST FAIL: " + p)
    if not problems:
        print(f"SELFTEST OK: {len(win.pages)} страниц, {len(api.handlers)} каналов ядра", flush=True)
    return 1 if problems else 0
