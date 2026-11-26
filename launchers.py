"""Окно «Другие лаунчеры»: короткий список хороших лаунчеров, ссылка на сайт и на видео-обзоры (поиск на YouTube)."""
from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from .. import i18n
from ..widgets import Card, Modal, VScroll, button

# (название, сайт, описание по-русски). Видео ищется по названию, конкретных роликов не зашито — ссылки не протухнут.
LAUNCHERS = [
    ("Prism Launcher", "https://prismlauncher.org/",
     "Открытый лаунчер: каждая сборка живёт отдельно, удобно держать много версий и модов. Вход через Microsoft."),
    ("Modrinth App", "https://modrinth.com/app",
     "Лаунчер от Modrinth: каталог модов, ресурспаков и сборок прямо внутри, простой современный интерфейс."),
    ("ATLauncher", "https://atlauncher.com/about",
     "Большой выбор готовых сборок из нескольких каталогов и установка в один клик."),
    ("CurseForge App", "https://www.curseforge.com/download/app",
     "Приложение каталога CurseForge: моды и сборки оттуда, с обновлением из одного места."),
    ("GDLauncher", "https://gdlauncher.com/",
     "Современный лаунчер с профилями и встроенным каталогом модов."),
    ("Официальный лаунчер Minecraft", "https://www.minecraft.net/download",
     "Лаунчер от Mojang: нужна лицензия, всегда свежие версии игры."),
]

i18n.register({
    "Другие лаунчеры": "Other launchers",
    "Хорошие лаунчеры, которые стоит знать. «Видео» открывает в браузере поиск обзоров на YouTube.":
        "Good launchers worth knowing. “Video” opens a YouTube search for reviews in your browser.",
    "Сайт": "Website",
    "Видео": "Video",
    "Закрыть": "Close",
    "Открытый лаунчер: каждая сборка живёт отдельно, удобно держать много версий и модов. Вход через Microsoft.":
        "An open-source launcher: every instance lives separately, handy for many versions and mods. Microsoft sign-in.",
    "Лаунчер от Modrinth: каталог модов, ресурспаков и сборок прямо внутри, простой современный интерфейс.":
        "The launcher from Modrinth: a catalog of mods, resource packs and modpacks inside, a simple modern interface.",
    "Большой выбор готовых сборок из нескольких каталогов и установка в один клик.":
        "A large choice of ready-made modpacks from several catalogs, installed in one click.",
    "Приложение каталога CurseForge: моды и сборки оттуда, с обновлением из одного места.":
        "The CurseForge catalog app: its mods and modpacks, updated from one place.",
    "Современный лаунчер с профилями и встроенным каталогом модов.":
        "A modern launcher with profiles and a built-in mod catalog.",
    "Официальный лаунчер Minecraft": "The official Minecraft launcher",
    "Лаунчер от Mojang: нужна лицензия, всегда свежие версии игры.":
        "The launcher from Mojang: a license is required, always the latest game versions.",
})


def video_url(name: str, lang: str = "ru") -> str:
    """Ссылка на поиск видео-обзоров этого лаунчера на YouTube."""
    word = "review" if lang == "en" else "обзор"
    return "https://www.youtube.com/results?search_query=" + quote(f"{name} {word}")


def _open(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class LaunchersDialog(Modal):
    def __init__(self, app, parent=None):
        super().__init__(app, "Другие лаунчеры", width=640, parent=parent, height=520)
        hint = QLabel(app.t("Хорошие лаунчеры, которые стоит знать. «Видео» открывает в браузере поиск обзоров на YouTube."))
        hint.setProperty("kind", "muted")
        hint.setWordWrap(True)
        self.body.addWidget(hint)
        scroll = VScroll()
        for name, site, desc in LAUNCHERS:
            c = Card(layout="h", margins=(12, 10, 12, 10), spacing=12)
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(app.t(name))
            t.setProperty("kind", "h2")
            col.addWidget(t)
            d = QLabel(app.t(desc))
            d.setWordWrap(True)
            d.setProperty("kind", "muted")
            col.addWidget(d)
            c.lay.addLayout(col, 1)
            btns = QVBoxLayout()
            btns.addWidget(button(app, "Видео", "primary", lambda n=name: _open(video_url(n, app.settings.get("lang", "ru")))))
            btns.addWidget(button(app, "Сайт", "small", lambda u=site: _open(u)))
            btns.addStretch(1)
            c.lay.addLayout(btns)
            scroll.lay.addWidget(c)
        scroll.lay.addStretch(1)
        self.body.addWidget(scroll, 1)
        self.add_button("Закрыть", "ghost", close=True)
