"""Мелкие окна и помощники: код сборки, обновление сборки, предупреждения перед запуском, файлы, брошенные в окно."""
from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

from ...core.base import BG_IMAGE, BG_VIDEO
from .. import i18n
from ..widgets import Modal

i18n.register({
    "Код сборки": "Build code",
    "Отправь этот код другу: он вставит его в «Импорт → Ввести код сборки» и получит такую же сборку.":
        "Send this code to a friend: they paste it into “Import → Enter build code” and get the same build.",
    "Не вошло в код: {n} (файлы не с Modrinth). Для полной копии лучше .mrpack.":
        "Left out of the code: {n} (files not from Modrinth). For a full copy use .mrpack.",
    "Копировать": "Copy", "Скопировано": "Copied", "Закрыть": "Close", "Отмена": "Cancel",
    "Ввести код сборки": "Enter build code",
    "Вставь код сборки, который тебе прислали:": "Paste the build code you were sent:",
    "Создать сборку": "Create build",
    "Сборка создана: {n}": "Build created: {n}",
    "Не скачалось файлов: {n}": "Files not downloaded: {n}",
    "Дублировать": "Duplicate",
    "Копия сборки «{n}» готова": "A copy of “{n}” is ready",
    "Копировать с мирами": "Copy with worlds",
    "Копировать без миров": "Copy without worlds",
    "Копировать сборку «{n}»? Миры можно взять с собой — тогда копирование дольше.":
        "Copy the build “{n}”? You can take the worlds along — it takes longer.",
    "Код сборки": "Build code",
    "Обновить сборку": "Update build",
    "У сборки есть обновление: {v}. Моды и файлы сборки обновятся, миры и настройки останутся. Старые файлы можно вернуть кнопкой «Откатить» на вкладке «Установлено». Обновить?":
        "A build update is available: {v}. Mods and pack files will be updated; worlds and settings stay. Old files can be restored with “Roll back” on the Installed tab. Update?",
    "У сборки последняя версия": "The build is up to date",
    "Сборка обновлена до {v}": "Build updated to {v}",
    "Обновить": "Update",
    "Эта сборка не с Modrinth — автоматически её не обновить": "This build is not from Modrinth, so it can't be updated automatically",
    "Проверка перед запуском": "Pre-launch check",
    "Запустить всё равно": "Launch anyway",
    "Мало места на диске: {n} ГБ. Игре и модам нужно несколько гигабайт.": "Low disk space: {n} GB. The game and mods need a few gigabytes.",
    "Почти нет места на диске: {n} ГБ. Игра может не запуститься.": "Almost no disk space: {n} GB. The game may fail to start.",
    "Указанная Java не найдена: {path}. Очисти путь в настройках — лаунчер скачает нужную сам.":
        "The Java you specified was not found: {path}. Clear the path in settings and the launcher will download the right one.",
    "Выделено {n} ГБ из {total} ГБ памяти компьютера — системе не хватит. Нажми «Подобрать» в настройках сборки.":
        "{n} GB of your {total} GB RAM is allocated — the system will run short. Press “Suggest” in the build settings.",
    "Что это за архив?": "What is this archive?",
    "Файл «{n}» — это ресурспак или шейдеры?": "Is the file “{n}” a resource pack or shaders?",
    "Ресурспак": "Resource pack", "Шейдеры": "Shaders",
    "Файл «{n}» добавлен в «{p}» ({f})": "File “{n}” added to “{p}” ({f})",
    "моды": "mods", "ресурспаки": "resource packs", "шейдеры": "shaders",
    "Поставить «{n}» фоном лаунчера?": "Set “{n}” as the launcher background?",
    "Фон лаунчера изменён": "Launcher background changed",
    "Такой файл не подходит: {n}": "This file doesn't fit: {n}",
    "Установка...": "Installing...",
    "Откатить": "Roll back",
    "Откатить последнее обновление модов? Новые версии удалятся, старые вернутся.":
        "Roll back the last mod update? New versions will be removed and the old ones restored.",
    "Откат выполнен: вернули {n}": "Rolled back: restored {n}",
    "Откатывать нечего": "Nothing to roll back",
    "Откатить обновление ({n})": "Roll back update ({n})",
})


class CodeDialog(Modal):
    def __init__(self, app, code: str, skipped: int = 0, parent=None):
        super().__init__(app, "Код сборки", width=520, parent=parent)
        hint = QLabel(app.t("Отправь этот код другу: он вставит его в «Импорт → Ввести код сборки» и получит такую же сборку."))
        hint.setWordWrap(True)
        hint.setProperty("kind", "muted")
        self.body.addWidget(hint)
        self.box = QPlainTextEdit(code)
        self.box.setReadOnly(True)
        self.box.setMinimumHeight(130)
        self.body.addWidget(self.box)
        if skipped:
            warn = QLabel(app.t("Не вошло в код: {n} (файлы не с Modrinth). Для полной копии лучше .mrpack.", n=skipped))
            warn.setWordWrap(True)
            warn.setProperty("kind", "warn")
            self.body.addWidget(warn)
        self.code = code
        self.btn_copy = self.add_button("Копировать", "primary", self._copy)
        self.add_button("Закрыть", "ghost", self.accept)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.code)
        self.btn_copy.setText(self.app.t("Скопировано"))


class EnterCodeDialog(Modal):
    def __init__(self, app, parent=None):
        super().__init__(app, "Ввести код сборки", width=520, parent=parent)
        self.body.addWidget(QLabel(app.t("Вставь код сборки, который тебе прислали:")))
        self.box = QPlainTextEdit()
        self.box.setMinimumHeight(120)
        self.body.addWidget(self.box)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setProperty("kind", "muted")
        self.body.addWidget(self.status)
        self.btn = self.add_button("Создать сборку", "primary", self._go)
        self.add_button("Отмена", "ghost", self.reject)
        app.event.connect(self._on_event)

    def _on_event(self, ch: str, payload) -> None:
        if ch in ("profile:progress", "pack:progress") and isinstance(payload, dict) and payload.get("text"):
            try:
                self.status.setText(self.app.t(str(payload["text"])))
            except RuntimeError:
                pass

    def _go(self) -> None:
        code = self.box.toPlainText().strip()
        if not code:
            return
        self.btn.setEnabled(False)
        self.status.setText(self.app.t("Установка..."))

        def ok(r):
            self.btn.setEnabled(True)
            if isinstance(r, dict) and r.get("ok"):
                miss = r.get("missing") or []
                self.app.toast(self.app.t("Сборка создана: {n}", n=r["profile"]["name"]) +
                               (" · " + self.app.t("Не скачалось файлов: {n}", n=len(miss)) if miss else ""), "ok")
                self.app.refresh_profiles()
                self.accept()
            else:
                self.status.setText(self.app.t(str((r or {}).get("error") or "?")))
        self.app.call("profile:code_import", {"code": code}, ok, lambda m: (self.btn.setEnabled(True), self.status.setText(m)))


def show_code(app, profile: dict) -> None:
    def ok(r):
        if isinstance(r, dict) and r.get("ok"):
            CodeDialog(app, r["code"], int(r.get("skipped") or 0)).exec()
        else:
            app.toast(app.t(str((r or {}).get("error") or "?")), "err")
    app.call("profile:code", {"profileId": profile["id"]}, ok, lambda m: app.toast(m, "err"))


def duplicate(app, profile: dict) -> None:
    from ..widgets import label
    dlg = Modal(app, "Дублировать", width=440)
    lb = label(app, None, wrap=True)
    lb.setText(app.t("Копировать сборку «{n}»? Миры можно взять с собой — тогда копирование дольше.", n=profile["name"]))
    dlg.body.addWidget(lb)
    choice = {}

    def pick(w):
        choice["w"] = w
        dlg.accept()
    dlg.add_button("Отмена", "ghost", dlg.reject)
    dlg.add_button("Копировать без миров", "primary", lambda: pick(False))
    dlg.add_button("Копировать с мирами", "ghost", lambda: pick(True))
    if dlg.exec() != dlg.Accepted:
        return

    def ok(r):
        if isinstance(r, dict) and r.get("ok"):
            app.toast(app.t("Копия сборки «{n}» готова", n=profile["name"]), "ok")
            app.refresh_profiles()
        else:
            app.toast(app.t(str((r or {}).get("error") or "?")), "err")
    app.call("profiles:duplicate", {"id": profile["id"], "withWorlds": bool(choice.get("w"))}, ok, lambda m: app.toast(m, "err"))


def update_pack(app, profile: dict) -> None:
    pack = profile.get("pack") or {}
    if pack.get("source") != "modrinth":
        app.toast(app.t("Эта сборка не с Modrinth — автоматически её не обновить"), "warn")
        return

    def got(r):
        if not (isinstance(r, dict) and r.get("ok")):
            app.toast(app.t(str((r or {}).get("error") or "?")), "err")
            return
        if not r.get("available"):
            app.toast(app.t("У сборки последняя версия"), "ok")
            return
        if not app.confirm("У сборки есть обновление: {v}. Моды и файлы сборки обновятся, миры и настройки останутся. "
                           "Старые файлы можно вернуть кнопкой «Откатить» на вкладке «Установлено». Обновить?",
                           "Обновить", v=r.get("version") or ""):
            return

        def done(r2):
            if isinstance(r2, dict) and r2.get("ok"):
                app.toast(app.t("Сборка обновлена до {v}", v=r2.get("version") or ""), "ok")
                app.refresh_profiles()
            else:
                app.toast(app.t(str((r2 or {}).get("error") or "?")), "err")
        app.call("pack:update", {"profileId": profile["id"]}, done, lambda m: app.toast(m, "err"))
    app.call("pack:updates", {"profileId": profile["id"]}, got, lambda m: app.toast(m, "err"))


def warning_text(app, w: dict) -> str:
    k = w.get("key")
    if k == "disk":
        return app.t("Почти нет места на диске: {n} ГБ. Игра может не запуститься." if w.get("level") == "err"
                     else "Мало места на диске: {n} ГБ. Игре и модам нужно несколько гигабайт.", n=w.get("n"))
    if k == "java":
        return app.t("Указанная Java не найдена: {path}. Очисти путь в настройках — лаунчер скачает нужную сам.", path=w.get("path"))
    if k == "ram":
        return app.t("Выделено {n} ГБ из {total} ГБ памяти компьютера — системе не хватит. Нажми «Подобрать» в настройках сборки.",
                     n=w.get("n"), total=w.get("total"))
    return str(k or "")


def preflight_ok(app, warnings: list) -> bool:
    """Показывает предупреждения; True — запускать всё равно."""
    dlg = Modal(app, "Проверка перед запуском", width=480)
    for w in warnings:
        lb = QLabel("•  " + warning_text(app, w))
        lb.setWordWrap(True)
        lb.setProperty("kind", "err" if w.get("level") == "err" else "warn")
        dlg.body.addWidget(lb)
    dlg.add_button("Отмена", "ghost", dlg.reject)
    dlg.add_button("Запустить всё равно", "primary", dlg.accept)
    return dlg.exec() == dlg.Accepted


def _ask_zip(app, name: str):
    dlg = Modal(app, "Что это за архив?", width=440)
    lb = QLabel(app.t("Файл «{n}» — это ресурспак или шейдеры?", n=name))
    lb.setWordWrap(True)
    dlg.body.addWidget(lb)
    pick = {}

    def go(k):
        pick["k"] = k
        dlg.accept()
    dlg.add_button("Отмена", "ghost", dlg.reject)
    dlg.add_button("Ресурспак", "primary", lambda: go("resourcepack"))
    dlg.add_button("Шейдеры", "ghost", lambda: go("shader"))
    return pick.get("k") if dlg.exec() == dlg.Accepted else None


def handle_drop(app, paths: list[str]) -> None:
    """Файлы, брошенные в окно лаунчера: .mrpack — новая сборка, .jar — мод, .zip — ресурспак/шейдеры, картинка/видео — фон."""
    for path in paths[:20]:
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if not os.path.isfile(path):
            continue
        if ext == ".mrpack":
            def done(r, n=name):
                if isinstance(r, dict) and r.get("ok"):
                    app.toast(app.t("Сборка создана: {n}", n=r["profile"]["name"]), "ok")
                    app.refresh_profiles()
                else:
                    app.toast(app.t(str((r or {}).get("error") or "?")), "err")
            app.call("profile:import", {"path": path}, done, lambda m: app.toast(m, "err"))
        elif ext in (".jar", ".zip"):
            kind = _ask_zip(app, name) if ext == ".zip" else None
            if ext == ".zip" and not kind:
                continue

            def done2(r, n=name):
                if isinstance(r, dict) and r.get("ok"):
                    app.toast(app.t("Файл «{n}» добавлен в «{p}» ({f})", n=n, p=r.get("profile"),
                                    f=app.t({"mods": "моды", "resourcepacks": "ресурспаки", "shaderpacks": "шейдеры"}.get(r.get("folder"), ""))), "ok")
                    app.refresh_profiles()
                else:
                    app.toast(app.t(str((r or {}).get("error") or "?")), "err")
            app.call("files:drop", {"path": path, "kind": kind}, done2, lambda m: app.toast(m, "err"))
        elif ext in BG_IMAGE or ext in BG_VIDEO:
            if app.confirm("Поставить «{n}» фоном лаунчера?", "Да", n=name):
                def done3(r):
                    if isinstance(r, dict) and r.get("ok"):
                        app.toast(app.t("Фон лаунчера изменён"), "ok")
                        app.refresh_settings()
                    else:
                        app.toast(app.t(str((r or {}).get("error") or "?")), "err")
                app.call("bg:choose", {"path": path}, done3, lambda m: app.toast(m, "err"))
        else:
            app.toast(app.t("Такой файл не подходит: {n}", n=name), "warn")
