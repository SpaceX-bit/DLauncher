"""Окно «Что нового»: список изменений по версиям. Показывается один раз после обновления и по кнопке в настройках."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ... import __version__
from .. import i18n
from ..widgets import Card, Modal, VScroll, button

# (версия, [пункты по-русски]); новые версии — сверху
CHANGES: list[tuple[str, list[str]]] = [
    ("2.0.24", [
        "Файлы можно бросать прямо в окно лаунчера: .mrpack создаст сборку, .jar станет модом, .zip — ресурспаком или шейдерами, картинка — фоном",
        "Сборку можно дублировать (меню «⋯» у сборки), с мирами или без",
        "Сборки с Modrinth обновляются на месте, не трогая миры и твои настройки",
        "Кнопка «Откатить» на вкладке «Установлено» возвращает старые моды после обновления",
        "Код сборки: короткая строка вместо файла, друг вставляет её в «Импорт → Ввести код сборки»",
        "Выбор оформления (Тёмная, Полночь, Лес, Закат) и цвета лаунчера в настройках",
        "Перед запуском лаунчер предупреждает, если мало места на диске, не найдена Java или слишком много памяти",
        "Шесть новых достижений",
    ]),
    ("2.0.23", [
        "Когда выходит новая версия, лаунчер сам предлагает обновиться: «Скачать» или «Позже»",
        "После «Скачать» обновление ставится само, лаунчер перезапускается уже новым",
    ]),
    ("2.0.22", [
        "Сборки можно раскрасить: свой цвет и значок на карточке, а ещё объединять в группы",
        "На карточке сборки виден сервер (избранный или последний): онлайн, пинг и сколько игроков",
        "Кнопка «Подобрать» в настройках сборки сама советует, сколько памяти выделить",
        "Звук при получении достижения (можно выключить в настройках)",
        "Вкладки «Установлено», «Миры» и «Скины» в том же стиле, что и «Мои сборки»",
        "Появилось это окно «Что нового»",
    ]),
    ("2.0.21", [
        "Достижения как в Minecraft: значки, плашка в углу и отдельная вкладка",
        "Автообновление модов и экспорт сборки в .mrpack",
        "Обучение с героями и кнопка «Другие лаунчеры»",
        "Новый внешний вид: карточки сборок и боковая панель",
    ]),
]

i18n.register({
    "Файлы можно бросать прямо в окно лаунчера: .mrpack создаст сборку, .jar станет модом, .zip — ресурспаком или шейдерами, картинка — фоном":
        "You can drop files right into the launcher window: .mrpack creates a build, .jar becomes a mod, .zip a resource pack or shaders, an image the background",
    "Сборку можно дублировать (меню «⋯» у сборки), с мирами или без":
        "A build can be duplicated (the “⋯” menu of a build), with or without worlds",
    "Сборки с Modrinth обновляются на месте, не трогая миры и твои настройки":
        "Modrinth builds update in place without touching worlds and your settings",
    "Кнопка «Откатить» на вкладке «Установлено» возвращает старые моды после обновления":
        "The “Roll back” button on the Installed tab restores old mods after an update",
    "Код сборки: короткая строка вместо файла, друг вставляет её в «Импорт → Ввести код сборки»":
        "Build code: a short string instead of a file; a friend pastes it into “Import → Enter build code”",
    "Выбор оформления (Тёмная, Полночь, Лес, Закат) и цвета лаунчера в настройках":
        "Choose a look (Dark, Midnight, Forest, Sunset) and the launcher color in settings",
    "Перед запуском лаунчер предупреждает, если мало места на диске, не найдена Java или слишком много памяти":
        "Before launch the launcher warns about low disk space, a missing Java or too much memory",
    "Шесть новых достижений": "Six new achievements",
    "Что нового": "What's new",
    "Что нового в DLauncher": "What's new in DLauncher",
    "Версия {n}": "Version {n}",
    "Закрыть": "Close",
    "Сборки можно раскрасить: свой цвет и значок на карточке, а ещё объединять в группы":
        "Builds can be colored: your own color and icon on the card, and you can put them in groups",
    "На карточке сборки виден сервер (избранный или последний): онлайн, пинг и сколько игроков":
        "The card shows a server (favorite or last used): online status, ping and player count",
    "Кнопка «Подобрать» в настройках сборки сама советует, сколько памяти выделить":
        "The “Suggest” button in build settings recommends how much memory to give",
    "Звук при получении достижения (можно выключить в настройках)":
        "A sound when you unlock an achievement (can be turned off in settings)",
    "Вкладки «Установлено», «Миры» и «Скины» в том же стиле, что и «Мои сборки»":
        "The Installed, Worlds and Skins tabs now match the My builds look",
    "Когда выходит новая версия, лаунчер сам предлагает обновиться: «Скачать» или «Позже»":
        "When a new version is out, the launcher offers to update: “Download” or “Later”",
    "После «Скачать» обновление ставится само, лаунчер перезапускается уже новым":
        "After “Download” the update installs itself and the launcher restarts already updated",
    "Появилось это окно «Что нового»": "This “What's new” window is new",
    "Достижения как в Minecraft: значки, плашка в углу и отдельная вкладка":
        "Minecraft-style achievements: icons, a corner toast and a separate tab",
    "Автообновление модов и экспорт сборки в .mrpack": "Automatic mod updates and export of a build to .mrpack",
    "Обучение с героями и кнопка «Другие лаунчеры»": "A tutorial with characters and an “Other launchers” button",
    "Новый внешний вид: карточки сборок и боковая панель": "A new look: build cards and a side rail",
})


class ChangelogDialog(Modal):
    def __init__(self, app, parent=None):
        super().__init__(app, "Что нового в DLauncher", width=560, parent=parent, height=480)
        scroll = VScroll()
        for ver, items in CHANGES:
            c = Card("build", margins=(14, 10, 14, 12), spacing=4)
            head = QLabel(app.t("Версия {n}", n=ver))
            head.setProperty("kind", "h3")
            c.lay.addWidget(head)
            for it in items:
                row = QLabel("•  " + app.t(it))
                row.setWordWrap(True)
                c.lay.addWidget(row)
            scroll.lay.addWidget(c)
        scroll.lay.addStretch(1)
        self.body.addWidget(scroll, 1)
        self.add_button("Закрыть", "primary", self.accept)


def should_show(settings: dict, version: str = __version__) -> str:
    """'show' — показать окно; 'mark' — молча запомнить версию (новая установка); '' — ничего не делать."""
    last = settings.get("lastSeenVersion")
    if last == version:
        return ""
    if not last and settings.get("tourDone") is not True:
        return "mark"
    return "show"
