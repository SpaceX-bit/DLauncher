"""Достижения в интерфейсе: плашка-поздравление (как в Steam) и общие функции для значков."""
from __future__ import annotations

import time

import os

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from . import i18n, mcicons
from ..resources import asset

# английские названия и описания (ключ — русский текст из core/achievements.py)
i18n.register({
    "Коллекция": "Collection", "Создай 5 сборок": "Create 5 builds",
    "Близнецы": "Twins", "Сделай копию сборки": "Make a copy of a build",
    "Машина времени": "Time machine", "Откати моды после обновления": "Roll mods back after an update",
    "Код в кармане": "Code in your pocket", "Получи код сборки, чтобы поделиться": "Get a build code to share",
    "Ловкость рук": "Sleight of hand", "Перетащи файл в окно лаунчера": "Drag a file into the launcher window",
    "Свой цвет": "Your color", "Выбери цвет лаунчера": "Pick the launcher color",
})
i18n.register({
    "Достижения": "Achievements",
    "Достижение получено": "Achievement unlocked",
    "Секретное достижение": "Secret achievement",
    "Первая сборка": "First build", "Создай свой первый профиль": "Create your first profile",
    "Поехали!": "Let's go!", "Запусти игру из лаунчера": "Launch the game from the launcher",
    "Первый мод": "First mod", "Установи мод из каталога": "Install a mod from the catalog",
    "Коллекционер": "Collector", "Установи 10 модов": "Install 10 mods",
    "Готовая сборка": "Ready-made pack", "Установи сборку из каталога": "Install a modpack from the catalog",
    "Новый стиль": "New style", "Установи ресурспак": "Install a resource pack",
    "Красота!": "Gorgeous!", "Установи шейдеры": "Install shaders",
    "Оптимизатор": "Optimizer", "Установи мод для оптимизации": "Install an optimization mod",
    "Поделиться": "Share", "Экспортируй сборку в .mrpack": "Export a build to .mrpack",
    "Переезд": "Moving in", "Импортируй сборку или профиль из другого лаунчера": "Import a build or profile from another launcher",
    "Страховка": "Insurance", "Сделай резервную копию мира": "Make a world backup",
    "Сетевой игрок": "Online player", "Добавь сервер в список": "Add a server to the list",
    "Новый облик": "New look", "Примени скин": "Apply a skin",
    "Лицензионный": "Licensed", "Войди через аккаунт Microsoft": "Sign in with a Microsoft account",
    "Проверено": "Checked", "Проверь моды на совместимость": "Check your mods for compatibility",
    "Всегда свежие": "Always fresh", "Обнови моды до новых версий": "Update mods to newer versions",
    "Свой стиль": "Own style", "Поставь свой фон лаунчера": "Set your own launcher background",
    "Прилежный ученик": "Diligent student", "Дослушай тему обучения до конца": "Listen to a tutorial topic to the end",
    "Завсегдатай": "Regular", "Запусти игру 10 раз": "Launch the game 10 times",
    "Час в игре": "An hour in game", "Наиграй 1 час": "Play for 1 hour",
    "Заядлый игрок": "Avid player", "Наиграй 10 часов": "Play for 10 hours",
    "Ночная смена": "Night shift", "Запусти игру глубокой ночью": "Launch the game in the dead of night",
    "Нашёл секрет": "Found a secret", "Найди пасхалку в лаунчере": "Find an easter egg in the launcher",
    "Получено": "Unlocked", "ч": "h",
    "Получено достижений": "Achievements unlocked",
})


def tile_pixmap(ctx, aid: str, unlocked: bool, size: int = 66, known: bool = True) -> QPixmap:
    """Значок достижения в рамке-слоте в стиле Minecraft. Свой PNG: <данные лаунчера>/achievements/<id>.png."""
    img = QImage(mcicons.TILE, mcicons.TILE, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    for (x, y), col in mcicons.tile_cells(aid, unlocked, known).items():
        p.fillRect(QRect(x, y, 1, 1), QColor(col))
    p.end()
    pm = QPixmap.fromImage(img).scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)
    custom = None
    try:
        f = os.path.join(ctx.user_data, "achievements", f"{aid}.png")
        custom = f if os.path.isfile(f) else None
    except Exception:  # noqa: BLE001
        pass
    if custom and (known or unlocked):
        icon = QPixmap(custom)
        if not icon.isNull():
            inner = int(size * 16 / mcicons.TILE)
            icon = icon.scaled(inner, inner, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            q = QPainter(pm)
            if not unlocked:
                q.setOpacity(0.3)
            q.drawPixmap((size - icon.width()) // 2, (size - icon.height()) // 2, icon)
            q.end()
    return pm


def fmt_when(ms) -> str:
    try:
        return time.strftime("%d.%m.%Y", time.localtime(float(ms) / 1000))
    except Exception:  # noqa: BLE001
        return ""


def play_chime(enabled: bool = True) -> bool:
    """Короткий звук получения достижения (только Windows; в остальных системах и при ошибках — тишина)."""
    if not enabled:
        return False
    try:
        import winsound  # type: ignore[import-not-found]
        path = asset("achievement.wav")
        if not os.path.exists(path):
            return False
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:  # noqa: BLE001
        return False


class AchievementToast(QFrame):
    """Плашка «Достижение получено» выезжает справа сверху, висит несколько секунд и уезжает. Очередь — по одной."""
    W, H = 340, 72
    HOLD_MS = 4500

    def __init__(self, app, parent):
        super().__init__(parent)
        self.app = app
        self.queue: list[dict] = []
        self.stage = ""
        self.setObjectName("achtoast")
        self.setFixedSize(self.W, self.H)
        self.setStyleSheet("QFrame#achtoast { background: #1d1d1d; border: 2px solid #8b8b8b; border-radius: 0px; }")
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 12, 8)
        row.setSpacing(12)
        self.badge = QLabel("")
        self.badge.setFixedSize(52, 52)
        self.badge.setAlignment(Qt.AlignCenter)
        row.addWidget(self.badge)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.head = QLabel("")
        self.head.setStyleSheet("color: #ffff55; font-size: 13px; font-weight: 800; background: transparent; border: none;")
        self.title = QLabel("")
        self.title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 700; background: transparent; border: none;")
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color: #9b9ba7; font-size: 12px; background: transparent; border: none;")
        for w in (self.head, self.title, self.desc):
            col.addWidget(w)
        col.addStretch(1)
        row.addLayout(col, 1)
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(380)
        self.anim.finished.connect(self._anim_done)
        self.hold = QTimer(self)
        self.hold.setSingleShot(True)
        self.hold.setInterval(self.HOLD_MS)
        self.hold.timeout.connect(self._slide_out)
        self.hide()

    def _fill(self, info: dict) -> None:
        t = self.app.t
        self.badge.setPixmap(tile_pixmap(self.app.ctx, info.get("id", ""), True, 52))
        self.head.setText(t("Достижение получено") + "!")
        self.title.setText(t(info.get("title", "")))
        self.desc.setText(t(info.get("desc", "")))
        self.desc.setVisible(False)  # как в игре: только жёлтая строка и название

    def _pos(self, out: bool) -> QPoint:
        par = self.parentWidget()
        pw = par.width() if par is not None else 1000
        return QPoint(pw + 10 if out else pw - self.W - 16, 66)

    def push(self, info: dict) -> None:
        self.queue.append(info)
        if not self.stage:
            self._next()

    def _next(self) -> None:
        if not self.queue:
            self.stage = ""
            self.hide()
            return
        self._fill(self.queue.pop(0))
        sound = getattr(self.app, "settings", None)
        play_chime(not isinstance(sound, dict) or sound.get("achSound") is not False)
        self.stage = "in"
        self.move(self._pos(True))
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.setStartValue(self._pos(True))
        self.anim.setEndValue(self._pos(False))
        self.anim.start()

    def _slide_out(self) -> None:
        self.stage = "out"
        self.anim.stop()
        self.anim.setEasingCurve(QEasingCurve.InCubic)
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(self._pos(True))
        self.anim.start()

    def _anim_done(self) -> None:
        if self.stage == "in":
            self.stage = "hold"
            self.hold.start()
        elif self.stage == "out":
            self.stage = ""
            self.hide()
            self._next()

    def preview(self, info: dict) -> None:
        """Показывает плашку сразу на месте, без анимации (для проверки и снимков экрана)."""
        self._fill(info)
        self.stage = "hold"
        self.move(self._pos(False))
        self.show()
        self.raise_()

    def reposition(self) -> None:
        if self.stage == "hold":
            self.move(self._pos(False))
