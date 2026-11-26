"""Обучение: герои-проводники говорят, куда нажимать и что делать.

Герои нарисованы пикселями в коде (свои кубики, не персонажи Mojang). Любого героя можно заменить своей картинкой:
положи PNG в папку «guides» рядом с настройками лаунчера (Настройки → Обучение → «Папка с героями»),
имя файла = id героя (kubik.png, listik.png, ten.png, ochkarik.png, lapka.png, kapla.png).
"""
from __future__ import annotations

import os

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import i18n

# ---------------------------------------------------------------- герои
GUIDES = {
    "kubik": {"name": "Кубик", "body": "#f08a24"},
    "listik": {"name": "Листик", "body": "#4cae4f"},
    "ten": {"name": "Тень", "body": "#6b3fa0"},
    "ochkarik": {"name": "Очкарик", "body": "#9aa5b1"},
    "lapka": {"name": "Лапка", "body": "#c0392b"},
    "kapla": {"name": "Капля", "body": "#2f8fd8"},
    # герои-картинки (вырезаны без фона, лежат в assets/guides)
    "steve": {"name": "Стив", "asset": "steve.png"},
    "golem": {"name": "Голем", "asset": "golem.png"},
    "spider": {"name": "Паук", "asset": "spider.png"},
    "warden": {"name": "Хранитель", "asset": "warden.png"},
}
SIZE = 16


def shade(color: str, k: float) -> str:
    c = QColor(color)
    return QColor(int(c.red() * k), int(c.green() * k), int(c.blue() * k)).name()


def portrait_cells(gid: str) -> dict[tuple[int, int], str]:
    """Клетки картинки героя 16×16: {(x, y): '#rrggbb'}. Чистая функция — удобно проверять без Qt."""
    g = GUIDES[gid]
    if "body" not in g:  # герой-картинка, клеток нет
        return {}
    body, dark, edge = g["body"], shade(g["body"], 0.72), shade(g["body"], 0.35)
    cells: dict[tuple[int, int], str] = {}

    def put(x, y, col):
        if 0 <= x < SIZE and 0 <= y < SIZE:
            cells[(x, y)] = col

    # тело 12×12: обводка, тень снизу и справа
    for y in range(3, 15):
        for x in range(2, 14):
            col = body
            if x == 13 or y == 14:
                col = dark
            if x in (2, 13) or y in (3, 14):
                col = edge if (x, y) in {(2, 3), (13, 3), (2, 14), (13, 14)} else col
            put(x, y, col)
    for x in range(2, 14):
        put(x, 3, edge)
        put(x, 14, edge)
    for y in range(3, 15):
        put(2, y, edge)
        put(13, y, edge)
    eye, white = "#161616", "#ffffff"
    if gid == "kubik":
        for x in (5, 10):
            put(x, 7, eye), put(x, 8, eye)
        for x in range(5, 11):
            put(x, 11, eye)
        put(4, 10, eye), put(11, 10, eye)
    elif gid == "listik":
        for x in (5, 10):
            put(x, 7, eye), put(x, 8, eye)
        for x in range(6, 10):
            put(x, 11, eye)
        for xy in ((8, 2), (8, 1), (9, 0), (10, 0), (10, 1)):
            put(*xy, "#2e8b3a")
    elif gid == "ten":
        glow = "#e6c8ff"
        for x in (4, 5, 10, 11):
            put(x, 8, glow)
        for xy in ((4, 2), (4, 1), (11, 2), (11, 1)):
            put(*xy, edge)
    elif gid == "ochkarik":
        for x in range(4, 8):
            put(x, 6, edge), put(x, 9, edge)
        for x in range(8, 12):
            put(x, 6, edge), put(x, 9, edge)
        for y in (7, 8):
            put(4, y, edge), put(7, y, edge), put(8, y, edge), put(11, y, edge)
        put(5, 7, eye), put(6, 8, eye), put(9, 7, eye), put(10, 8, eye)
        for x in range(6, 10):
            put(x, 12, eye)
    elif gid == "lapka":
        for x in (5, 10):
            put(x, 7, white), put(x, 8, eye)
        for x in range(6, 10):
            put(x, 11, eye)
        for x in (2, 5, 10, 13):
            put(x, 15, edge)
        put(1, 10, dark), put(1, 11, dark), put(14, 10, dark), put(14, 11, dark)
    elif gid == "kapla":
        for xy in ((7, 2), (8, 2), (7, 1), (8, 1), (7, 0)):
            put(*xy, body)
        put(7, 0, edge), put(8, 1, dark)
        for x in (5, 10):
            put(x, 8, eye), put(x, 9, eye)
        for x in range(6, 10):
            put(x, 12, eye)
        put(4, 5, white), put(4, 6, white), put(5, 5, white)
    return cells


def custom_portrait_path(ctx, gid: str) -> str | None:
    try:
        p = os.path.join(ctx.user_data, "guides", f"{gid}.png")
        return p if os.path.isfile(p) else None
    except Exception:  # noqa: BLE001
        return None


def portrait_pixmap(ctx, gid: str, size: int = 96) -> QPixmap:
    custom = custom_portrait_path(ctx, gid)
    if not custom and GUIDES[gid].get("asset"):
        from ..resources import asset
        path = asset("guides/" + GUIDES[gid]["asset"])
        custom = path if os.path.isfile(path) else None
    if custom:
        pm = QPixmap(custom)
        if not pm.isNull():
            return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    for (x, y), col in portrait_cells(gid).items():
        p.fillRect(QRect(x, y, 1, 1), QColor(col))
    p.end()
    return QPixmap.fromImage(img).scaled(size, size, Qt.KeepAspectRatio, Qt.FastTransformation)


# ---------------------------------------------------------------- сценарий обучения
# шаг: (герой, вкладка, заголовок, текст)
CHAPTERS: dict[str, tuple[str, list[tuple[str, str, str, str]]]] = {
    "quick": ("Быстрый старт", [
        ("steve", "play", "Привет!", "Я Стив и покажу, как тут всё устроено. Слева панель вкладок, сверху выбранная сборка, а внизу большая кнопка «Играть». Нажимай «Далее»."),
        ("listik", "settings", "Аккаунт без лицензии", "Открой «Настройки» и найди блок «Аккаунт». Оставь режим «Офлайн», впиши ник (до 16 символов) и нажми внизу «Сохранить»."),
        ("ten", "profiles", "Профиль — это копия игры", "Во вкладке «Профили» нажми «Создать профиль»: задай имя, выбери версию Minecraft и загрузчик. Для модов чаще всего берут Fabric или Forge."),
        ("spider", "mods", "Моды", "Во вкладке «Моды» выбери профиль, введи название в поиск и нажми «Найти». Кнопка «Установить» ставит мод сама, а «Версии» даёт выбрать нужную."),
        ("golem", "mods", "Готовые сборки", "Над поиском переключись на «Сборки»: выбери сборку, версию, и она установится как новый профиль со всеми модами."),
        ("kapla", "play", "Запуск", "Нажми «Играть». Первый запуск долгий: лаунчер скачает файлы игры и нужную Java сам. Если игра вылетит, откроется разбор причины."),
    ]),
    "account": ("Как добавить аккаунт", [
        ("listik", "settings", "Офлайн-аккаунт", "«Настройки» → блок «Аккаунт» → режим «Офлайн (только ник)». Впиши ник и нажми «Сохранить». Этого хватает для игры на своих серверах и в одиночном мире."),
        ("steve", "settings", "Аккаунт Microsoft", "Выбери режим «Microsoft (лицензия)», вставь Client ID своего приложения Azure (инструкция в README) и нажми «Добавить аккаунт». Появится код: введи его на открывшейся странице Microsoft."),
        ("ochkarik", "settings", "Несколько аккаунтов", "Можно добавить несколько аккаунтов Microsoft. В игру заходит тот, что отмечен «Активный». Кнопки «Выбрать» и «Удалить» рядом с каждым."),
    ]),
    "profiles": ("Профили и версии", [
        ("ten", "profiles", "Создать профиль", "«Профили» → «Создать профиль». Версия, загрузчик (Vanilla, Fabric, Forge, NeoForge, Quilt) и имя. Память и параметры Java можно поменять в «Настройки» самого профиля."),
        ("golem", "profiles", "Импорт", "Есть сборки в TLauncher, Prism, CurseForge или Modrinth App? «Импорт из других лаунчеров» скопирует их сюда, а твои файлы останутся нетронутыми."),
        ("kapla", "play", "Выбор сборки", "Выбрать, во что играть, можно в «Недавних сборках» на вкладке «Играть» или в списке «Профили». Выбранная сборка видна сверху в середине."),
    ]),
    "mods": ("Моды и сборки", [
        ("spider", "mods", "Поиск модов", "«Моды» → введи название → «Найти». Переключатели вверху: Моды, Сборки, Ресурспаки, Шейдеры, а также источник Modrinth или CurseForge (для CurseForge нужен ключ в настройках)."),
        ("listik", "mods", "Подходящая версия", "Лаунчер сам берёт версию мода под твою версию игры и загрузчик. Кнопка «Версии» показывает все файлы, подходящая подсвечена зелёным."),
        ("kubik", "installed", "Установленные моды", "Во вкладке «Установлено» моды можно выключать, удалять и обновлять все сразу. «Проверить совместимость» найдёт конфликты ещё до запуска."),
        ("golem", "mods", "Готовые сборки", "Переключатель «Сборки»: найди сборку, выбери её версию, и лаунчер создаст новый профиль и скачает все моды."),
    ]),
    "worlds": ("Миры, скины, копии", [
        ("golem", "worlds", "Миры и резервные копии", "Во вкладке «Миры» видны сохранения выбранной сборки. Лаунчер делает резервные копии миров перед запуском (включается в «Настройки»), а вернуть мир можно из списка копий."),
        ("steve", "skins", "Скины", "Во вкладке «Скины» выбери файл скина, посмотри его спереди и сзади и нажми «Применить». Нужен аккаунт Microsoft."),
        ("kubik", "settings", "Память, оформление, Discord", "В «Настройки» можно задать выделенную память, язык, свой фон, статус в Discord и автозапуск. Не забудь нажать «Сохранить»."),
    ]),
    "trouble": ("Если игра не запускается", [
        ("warden", "play", "Логи", "Нажми «Логи» в нижней панели: там вся консоль игры. После вылета откроется окно с разбором причины и подсказкой, что сделать."),
        ("listik", "installed", "Проверка модов", "Часто виноваты моды. Во вкладке «Установлено» нажми «Проверить совместимость» или выключи последние добавленные моды."),
        ("lapka", "settings", "Память и Java", "В «Настройки» проверь выделенную память (для больших сборок 6–8 ГБ) и путь к Java. Пустой путь — Java скачается сама."),
    ]),
    "features": ("Все фишки лаунчера", [
        ("steve", "play", "Недавние сборки", "На вкладке «Играть» видны карточки твоих сборок. Кнопка «Играть» на карточке запускает именно её, «Выбрать» просто делает сборку текущей."),
        ("kapla", "play", "Вход на сервер", "Внизу рядом с кнопкой «Играть» есть список серверов: выбери сервер, и игра сразу зайдёт на него. Сам список задаётся в настройках профиля."),
        ("ochkarik", "play", "Статистика и новости", "Под карточками сборок лаунчер показывает твою статистику игры и свежие новости Minecraft."),
        ("lapka", "worlds", "Скриншоты", "Во вкладке «Миры» есть раздел «Скриншоты»: все снимки из игры собраны в одну галерею."),
        ("golem", "worlds", "Резервные копии", "Раздел «Резервные копии» хранит копии миров: сделай копию вручную или включи автоматические в настройках. Любой мир можно вернуть."),
        ("ten", "settings", "Фон и оформление", "В «Настройки» можно поставить свою картинку или видео как фон лаунчера, выбрать язык и настроить прозрачность панелей."),
        ("kubik", "settings", "Трей и автозапуск", "Крестик может прятать лаунчер в трей (значок у часов), а не закрывать. Ещё лаунчер умеет запускаться вместе с Windows свёрнутым."),
        ("warden", "settings", "Статус в Discord", "Включи Rich Presence, впиши Application ID своего приложения Discord, и друзья увидят, во что ты играешь."),
        ("spider", "settings", "Обновления", "Лаунчер сам проверяет новые версии на GitHub. Когда обновление скачано, появится уведомление: перезапусти лаунчер, и оно применится."),
    ]),
}
CHAPTER_ORDER = ["quick", "account", "profiles", "mods", "worlds", "features", "trouble"]

i18n.register({
    "Обучение": "Tutorial",
    "Быстрый старт": "Quick start",
    "Как добавить аккаунт": "How to add an account",
    "Профили и версии": "Profiles and versions",
    "Моды и сборки": "Mods and modpacks",
    "Миры, скины, копии": "Worlds, skins, backups",
    "Если игра не запускается": "If the game won't start",
    "Все фишки лаунчера": "All launcher features",
    "Далее": "Next",
    "Назад": "Back",
    "Готово": "Done",
    "Пропустить": "Skip",
    "Папка с героями": "Guides folder",
    "Кубик": "Cubic", "Листик": "Leafy", "Тень": "Shade", "Очкарик": "Specs", "Лапка": "Paws", "Капля": "Drop",
    "Стив": "Steve", "Голем": "Golem", "Паук": "Spider", "Хранитель": "Warden",
    # ----- тексты шагов
    "Привет!": "Hi!",
    "Я Стив и покажу, как тут всё устроено. Слева панель вкладок, сверху выбранная сборка, а внизу большая кнопка «Играть». Нажимай «Далее».":
        "I'm Steve and I'll show you around. The tabs are on the left, the selected build is at the top, and the big Play button is at the bottom. Press “Next”.",
    "Аккаунт без лицензии": "An account without a license",
    "Открой «Настройки» и найди блок «Аккаунт». Оставь режим «Офлайн», впиши ник (до 16 символов) и нажми внизу «Сохранить».":
        "Open “Settings” and find the “Account” block. Keep “Offline” mode, type a nickname (up to 16 characters) and press “Save” at the bottom.",
    "Профиль — это копия игры": "A profile is a copy of the game",
    "Во вкладке «Профили» нажми «Создать профиль»: задай имя, выбери версию Minecraft и загрузчик. Для модов чаще всего берут Fabric или Forge.":
        "On the “Profiles” tab press “Create a profile”: give it a name, pick a Minecraft version and a loader. Fabric or Forge are the usual choice for mods.",
    "Моды": "Mods",
    "Во вкладке «Моды» выбери профиль, введи название в поиск и нажми «Найти». Кнопка «Установить» ставит мод сама, а «Версии» даёт выбрать нужную.":
        "On the “Mods” tab pick a profile, type a name in the search and press “Search”. “Install” installs a mod for you, and “Versions” lets you pick a specific one.",
    "Готовые сборки": "Ready-made modpacks",
    "Над поиском переключись на «Сборки»: выбери сборку, версию, и она установится как новый профиль со всеми модами.":
        "Above the search switch to “Modpacks”: pick a pack and a version and it installs as a new profile with all its mods.",
    "Запуск": "Launching",
    "Нажми «Играть». Первый запуск долгий: лаунчер скачает файлы игры и нужную Java сам. Если игра вылетит, откроется разбор причины.":
        "Press “Play”. The first launch is slow: the launcher downloads the game files and the right Java by itself. If the game crashes, a crash analysis opens.",
    "Офлайн-аккаунт": "Offline account",
    "«Настройки» → блок «Аккаунт» → режим «Офлайн (только ник)». Впиши ник и нажми «Сохранить». Этого хватает для игры на своих серверах и в одиночном мире.":
        "“Settings” → “Account” → “Offline (nickname only)”. Type a nickname and press “Save”. That is enough for single-player and servers that allow it.",
    "Аккаунт Microsoft": "Microsoft account",
    "Выбери режим «Microsoft (лицензия)», вставь Client ID своего приложения Azure (инструкция в README) и нажми «Добавить аккаунт». Появится код: введи его на открывшейся странице Microsoft.":
        "Choose “Microsoft (licensed)”, paste the Client ID of your Azure app (see the README) and press “Add account”. A code appears: enter it on the Microsoft page that opens.",
    "Несколько аккаунтов": "Several accounts",
    "Можно добавить несколько аккаунтов Microsoft. В игру заходит тот, что отмечен «Активный». Кнопки «Выбрать» и «Удалить» рядом с каждым.":
        "You can add several Microsoft accounts. The one marked “Active” is used in the game. “Select” and “Delete” are next to each one.",
    "Создать профиль": "Create a profile",
    "«Профили» → «Создать профиль». Версия, загрузчик (Vanilla, Fabric, Forge, NeoForge, Quilt) и имя. Память и параметры Java можно поменять в «Настройки» самого профиля.":
        "“Profiles” → “Create a profile”. Version, loader (Vanilla, Fabric, Forge, NeoForge, Quilt) and name. Memory and Java options can be changed in the profile's “Settings”.",
    "Импорт": "Import",
    "Есть сборки в TLauncher, Prism, CurseForge или Modrinth App? «Импорт из других лаунчеров» скопирует их сюда, а твои файлы останутся нетронутыми.":
        "Have instances in TLauncher, Prism, CurseForge or Modrinth App? “Import from other launchers” copies them here and leaves your files untouched.",
    "Выбор сборки": "Choosing a build",
    "Выбрать, во что играть, можно в «Недавних сборках» на вкладке «Играть» или в списке «Профили». Выбранная сборка видна сверху в середине.":
        "Pick what to play in “Recent builds” on the Play tab or in the “Profiles” list. The selected build is shown at the top.",
    "Поиск модов": "Searching for mods",
    "«Моды» → введи название → «Найти». Переключатели вверху: Моды, Сборки, Ресурспаки, Шейдеры, а также источник Modrinth или CurseForge (для CurseForge нужен ключ в настройках).":
        "“Mods” → type a name → “Search”. The switches at the top: Mods, Modpacks, Resource packs, Shaders, plus the source, Modrinth or CurseForge (CurseForge needs a key in the settings).",
    "Подходящая версия": "The right version",
    "Лаунчер сам берёт версию мода под твою версию игры и загрузчик. Кнопка «Версии» показывает все файлы, подходящая подсвечена зелёным.":
        "The launcher picks the mod version for your game version and loader by itself. “Versions” lists all files, the matching one is highlighted in green.",
    "Установленные моды": "Installed mods",
    "Во вкладке «Установлено» моды можно выключать, удалять и обновлять все сразу. «Проверить совместимость» найдёт конфликты ещё до запуска.":
        "On the “Installed” tab you can disable, remove and update all mods at once. “Check compatibility” finds conflicts before launching.",
    "Переключатель «Сборки»: найди сборку, выбери её версию, и лаунчер создаст новый профиль и скачает все моды.":
        "Use the “Modpacks” switch: find a pack, choose its version, and the launcher creates a new profile and downloads all the mods.",
    "Миры и резервные копии": "Worlds and backups",
    "Во вкладке «Миры» видны сохранения выбранной сборки. Лаунчер делает резервные копии миров перед запуском (включается в «Настройки»), а вернуть мир можно из списка копий.":
        "The “Worlds” tab shows the saves of the selected build. The launcher backs worlds up before launching (enable it in “Settings”), and a world can be restored from the list of backups.",
    "Скины": "Skins",
    "Во вкладке «Скины» выбери файл скина, посмотри его спереди и сзади и нажми «Применить». Нужен аккаунт Microsoft.":
        "On the “Skins” tab choose a skin file, look at it from the front and the back and press “Apply”. A Microsoft account is required.",
    "Память, оформление, Discord": "Memory, looks, Discord",
    "В «Настройки» можно задать выделенную память, язык, свой фон, статус в Discord и автозапуск. Не забудь нажать «Сохранить».":
        "In “Settings” you can set the allocated memory, language, your own background, Discord status and autostart. Don't forget to press “Save”.",
    "Логи": "Logs",
    "Нажми «Логи» в нижней панели: там вся консоль игры. После вылета откроется окно с разбором причины и подсказкой, что сделать.":
        "Press “Logs” in the bottom bar: it shows the whole game console. After a crash a window opens with the cause and a hint on what to do.",
    "Проверка модов": "Checking mods",
    "Часто виноваты моды. Во вкладке «Установлено» нажми «Проверить совместимость» или выключи последние добавленные моды.":
        "Mods are often the cause. On the “Installed” tab press “Check compatibility” or disable the mods you added last.",
    "Недавние сборки": "Recent builds",
    "На вкладке «Играть» видны карточки твоих сборок. Кнопка «Играть» на карточке запускает именно её, «Выбрать» просто делает сборку текущей.":
        "The Play tab shows cards of your builds. “Play” on a card launches that build, “Choose” just makes it the current one.",
    "Вход на сервер": "Joining a server",
    "Внизу рядом с кнопкой «Играть» есть список серверов: выбери сервер, и игра сразу зайдёт на него. Сам список задаётся в настройках профиля.":
        "Next to the Play button at the bottom there is a server list: pick a server and the game joins it right away. The list itself is set in the profile settings.",
    "Статистика и новости": "Statistics and news",
    "Под карточками сборок лаунчер показывает твою статистику игры и свежие новости Minecraft.":
        "Below the build cards the launcher shows your play statistics and fresh Minecraft news.",
    "Скриншоты": "Screenshots",
    "Во вкладке «Миры» есть раздел «Скриншоты»: все снимки из игры собраны в одну галерею.":
        "The “Worlds” tab has a “Screenshots” section: all in-game screenshots are collected in one gallery.",
    "Резервные копии": "Backups",
    "Раздел «Резервные копии» хранит копии миров: сделай копию вручную или включи автоматические в настройках. Любой мир можно вернуть.":
        "The “Backups” section keeps copies of your worlds: make one by hand or enable automatic ones in the settings. Any world can be restored.",
    "Фон и оформление": "Background and looks",
    "В «Настройки» можно поставить свою картинку или видео как фон лаунчера, выбрать язык и настроить прозрачность панелей.":
        "In “Settings” you can set your own picture or video as the launcher background, pick the language and tune panel transparency.",
    "Трей и автозапуск": "Tray and autostart",
    "Крестик может прятать лаунчер в трей (значок у часов), а не закрывать. Ещё лаунчер умеет запускаться вместе с Windows свёрнутым.":
        "The close button can hide the launcher to the tray (the icon by the clock) instead of closing it. It can also start with Windows, minimized.",
    "Статус в Discord": "Discord status",
    "Включи Rich Presence, впиши Application ID своего приложения Discord, и друзья увидят, во что ты играешь.":
        "Turn on Rich Presence, enter your Discord app's Application ID, and friends will see what you're playing.",
    "Обновления": "Updates",
    "Лаунчер сам проверяет новые версии на GitHub. Когда обновление скачано, появится уведомление: перезапусти лаунчер, и оно применится.":
        "The launcher checks GitHub for new versions by itself. When an update is downloaded a notice appears: restart the launcher to apply it.",
    "Память и Java": "Memory and Java",
    "В «Настройки» проверь выделенную память (для больших сборок 6–8 ГБ) и путь к Java. Пустой путь — Java скачается сама.":
        "In “Settings” check the allocated memory (6–8 GB for big modpacks) and the Java path. An empty path means Java is downloaded automatically.",
})


def _pick(chapter: str, idx: int, gid: str | None = None) -> tuple[str, str, str, str]:
    g, page, title, text = CHAPTERS[chapter][1][idx]
    return (gid or g, page, title, text)


# Темы меню Стива: (ключ, название, герой на кнопке, шаги). После выбора темы приходит другой герой и рассказывает.
OVERVIEW: list[tuple[str, str, str, str]] = [
    ("kubik", "play", "Вкладка «Играть»", "Главный экран: карточки твоих недавних сборок, а внизу панель запуска. На ней выбор сервера, кнопки «Моды», «Логи», «Папка», «Настройки» и большая «Играть»."),
    ("ten", "play", "Верхняя панель", "Сверху по центру стоит выбранная сборка: нажми на название, чтобы выбрать другую, а ▶ запускает её сразу. Справа твой ник или Microsoft (ведёт в настройки аккаунта)."),
    ("ten", "profiles", "Вкладка «Профили»", "Все твои сборки в одном месте: создать новую, настроить память и Java, импортировать из других лаунчеров или скачать готовую сборку."),
    ("spider", "mods", "Вкладка «Моды»", "Поиск и установка модов, сборок, ресурспаков и шейдеров из Modrinth и CurseForge сразу в выбранную сборку."),
    ("listik", "installed", "Вкладка «Установлено»", "Всё, что уже стоит в сборке: моды можно включать и выключать, удалять, обновлять и проверять на совместимость."),
    ("lapka", "worlds", "Вкладка «Миры»", "Сохранённые миры выбранной сборки, их резервные копии и галерея скриншотов."),
    ("ochkarik", "skins", "Вкладка «Скины»", "Выбор скина и плаща с предпросмотром спереди и сзади. Нужен аккаунт Microsoft."),
    ("kapla", "achievements", "Вкладка «Достижения»", "Значки за дела в лаунчере: первая сборка, первый мод, часы игры. Когда получаешь новый, справа сверху выезжает поздравление. Есть и секретные."),
    ("golem", "settings", "Вкладка «Настройки»", "Аккаунт и ник, память, язык, фон, трей и автозапуск, Discord и обновления. Поменял что-то, нажми «Сохранить»."),
    ("kapla", "play", "Обучение всегда рядом", "Снизу на левой панели есть кнопка «Обучение». Нажми её, и я снова расскажу про лаунчер, а после обзора Стив даст выбрать любую тему. Удачной игры!"),
]

TOPICS: list[tuple[str, str, str, list[tuple[str, str, str, str]]]] = [
    ("overview", "Весь лаунчер", "kubik", OVERVIEW),
    # три шага «аккаунт → профиль → запуск», как в «Your First Launch» у других лаунчеров
    ("first", "Первые шаги", "kubik", [_pick("quick", 1), _pick("quick", 2), _pick("quick", 5)]),
    ("account", "Аккаунт", "listik", [_pick("account", 0), _pick("account", 1, "kubik"), _pick("account", 2, "ochkarik")]),
    ("profiles", "Профили", "ten", [_pick("profiles", 0), _pick("profiles", 1), _pick("profiles", 2)]),
    ("mods", "Моды", "spider", [_pick("mods", 0), _pick("mods", 1), _pick("mods", 2, "kubik"),
                                 ("listik", "settings", "Автообновление модов", "В «Настройки» включи «Обновлять моды автоматически перед запуском игры», и лаунчер сам обновит моды перед нажатием «Играть».")]),
    ("packs", "Сборки", "golem", [
        _pick("quick", 4),
        ("golem", "profiles", "Сборка из профилей", "Сборку можно скачать и во вкладке «Профили»: кнопка «Скачать сборку» найдёт нужную и создаст из неё профиль."),
        _pick("mods", 3),
        ("golem", "profiles", "Экспорт сборки", "В карточке сборки нажми «⋯» → «Экспорт .mrpack»: получится один файл, который можно отправить другу. Его понимают Modrinth App и Prism Launcher."),
    ]),
    ("achievements", "Достижения", "kapla", [
        ("kapla", "achievements", "Значки за дела", "Во вкладке «Достижения» собраны все значки. Полученные яркие, остальные серые, у некоторых видно прогресс (например, сколько модов установлено)."),
        ("kapla", "achievements", "Поздравления", "Когда получаешь достижение, справа сверху выезжает плашка с поздравлением. Есть и секретные достижения: их название скрыто, пока не получишь."),
    ]),
    ("resourcepacks", "Ресурспаки", "lapka", [
        ("lapka", "mods", "Ставим ресурспак", "Во вкладке «Моды» переключись на «Ресурспаки», найди пак по названию и нажми «Установить». Лаунчер положит его в папку ресурспаков выбранной сборки."),
        ("lapka", "mods", "Включаем в игре", "Дальше запусти игру и включи пак в самой игре: «Настройки» → «Ресурспаки». Паки можно сочетать и менять порядок."),
    ]),
    ("shaders", "Шейдеры", "kapla", [
        ("kapla", "mods", "Ставим шейдеры", "Переключись на «Шейдеры», найди нужный шейдер и нажми «Установить». Он ляжет в папку шейдеров выбранной сборки."),
        ("kapla", "mods", "Чтобы шейдеры работали", "Шейдерам нужен мод-загрузчик, например Iris (для Fabric). Установи его во вкладке «Моды», а включить шейдер потом можно в игре: «Настройки» → «Качество» → «Шейдеры»."),
    ]),
    ("skins", "Скины", "ochkarik", [_pick("worlds", 1, "ochkarik")]),
    ("worlds", "Миры и копии", "golem", [_pick("worlds", 0), _pick("features", 3), _pick("features", 4)]),
    ("play", "Запуск и серверы", "kubik", [_pick("quick", 5), _pick("features", 0, "kubik"), _pick("features", 1), _pick("features", 2)]),
    ("trouble", "Вылетает игра", "warden", [_pick("trouble", 0, "warden"), _pick("trouble", 1), _pick("trouble", 2)]),
    ("settings", "Настройки", "ten", [_pick("worlds", 2), _pick("features", 5), _pick("features", 6), _pick("features", 7), _pick("features", 8)]),
]
TOPIC_ORDER = [t[0] for t in TOPICS]

i18n.register({
    "Не хотите пройти обучение?": "Want to take a quick tour?",
    "Да": "Yes",
    "Не надо": "No thanks",
    "Привет! Я Стив": "Hi! I'm Steve",
    "О чём тебе рассказать? Выбери тему, и придёт помощник, который в ней разбирается.":
        "What should I tell you about? Pick a topic and a helper who knows it will come.",
    "Рассказать ещё о чём-нибудь?": "Want to hear about something else?",
    "Хватит": "Enough",
    "К темам": "Topics",
    "Первые шаги": "First steps",
    "Весь лаунчер": "The whole launcher",
    "Достижения": "Achievements",
    "Вкладка «Достижения»": "The “Achievements” tab",
    "Значки за дела в лаунчере: первая сборка, первый мод, часы игры. Когда получаешь новый, справа сверху выезжает поздравление. Есть и секретные.":
        "Badges for things done in the launcher: first build, first mod, hours played. When you earn one, a congratulation slides in at the top right. Some are secret.",
    "Автообновление модов": "Automatic mod updates",
    "В «Настройки» включи «Обновлять моды автоматически перед запуском игры», и лаунчер сам обновит моды перед нажатием «Играть».":
        "In “Settings” turn on “Update mods automatically before launching the game” and the launcher updates your mods before you press “Play”.",
    "Экспорт сборки": "Exporting a build",
    "В карточке сборки нажми «⋯» → «Экспорт .mrpack»: получится один файл, который можно отправить другу. Его понимают Modrinth App и Prism Launcher.":
        "On a build card press “⋯” → “Export .mrpack”: you get one file you can send to a friend. Modrinth App and Prism Launcher understand it.",
    "Значки за дела": "Badges for deeds",
    "Во вкладке «Достижения» собраны все значки. Полученные яркие, остальные серые, у некоторых видно прогресс (например, сколько модов установлено).":
        "The “Achievements” tab collects all badges. Earned ones are bright, the rest are grey, and some show progress (for example how many mods are installed).",
    "Поздравления": "Congratulations",
    "Когда получаешь достижение, справа сверху выезжает плашка с поздравлением. Есть и секретные достижения: их название скрыто, пока не получишь.":
        "When you earn an achievement a congratulation card slides in at the top right. There are secret ones too: their name stays hidden until you earn them.",
    "Вкладка «Играть»": "The “Play” tab",
    "Главный экран: карточки твоих недавних сборок, а внизу панель запуска. На ней выбор сервера, кнопки «Моды», «Логи», «Папка», «Настройки» и большая «Играть».":
        "The main screen: cards of your recent builds, and the launch bar at the bottom with the server choice, the “Mods”, “Logs”, “Folder”, “Settings” buttons and the big “Play”.",
    "Верхняя панель": "The top bar",
    "Сверху по центру стоит выбранная сборка: нажми на название, чтобы выбрать другую, а ▶ запускает её сразу. Справа твой ник или Microsoft (ведёт в настройки аккаунта).":
        "The selected build sits at the top centre: click its name to pick another, ▶ launches it at once. On the right is your nickname or Microsoft (leads to the account settings).",
    "Вкладка «Профили»": "The “Profiles” tab",
    "Все твои сборки в одном месте: создать новую, настроить память и Java, импортировать из других лаунчеров или скачать готовую сборку.":
        "All your builds in one place: create a new one, set memory and Java, import from other launchers or download a ready-made modpack.",
    "Вкладка «Моды»": "The “Mods” tab",
    "Поиск и установка модов, сборок, ресурспаков и шейдеров из Modrinth и CurseForge сразу в выбранную сборку.":
        "Search and install mods, modpacks, resource packs and shaders from Modrinth and CurseForge straight into the selected build.",
    "Вкладка «Установлено»": "The “Installed” tab",
    "Всё, что уже стоит в сборке: моды можно включать и выключать, удалять, обновлять и проверять на совместимость.":
        "Everything already in the build: mods can be disabled, removed, updated and checked for compatibility.",
    "Вкладка «Миры»": "The “Worlds” tab",
    "Сохранённые миры выбранной сборки, их резервные копии и галерея скриншотов.":
        "The saved worlds of the selected build, their backups and a screenshot gallery.",
    "Вкладка «Скины»": "The “Skins” tab",
    "Выбор скина и плаща с предпросмотром спереди и сзади. Нужен аккаунт Microsoft.":
        "Choose a skin and a cape with a front and back preview. A Microsoft account is required.",
    "Вкладка «Настройки»": "The “Settings” tab",
    "Аккаунт и ник, память, язык, фон, трей и автозапуск, Discord и обновления. Поменял что-то, нажми «Сохранить».":
        "Account and nickname, memory, language, background, tray and autostart, Discord and updates. Changed something? Press “Save”.",
    "Обучение всегда рядом": "The tutorial is always at hand",
    "Снизу на левой панели есть кнопка «Обучение». Нажми её, и я снова расскажу про лаунчер, а после обзора Стив даст выбрать любую тему. Удачной игры!":
        "There is a “Tutorial” button at the bottom of the left panel. Press it and I'll tell you about the launcher again, and after the overview Steve lets you pick any topic. Have fun!",
    "Аккаунт": "Account", "Профили": "Profiles", "Моды": "Mods", "Сборки": "Modpacks", "Ресурспаки": "Resource packs",
    "Шейдеры": "Shaders", "Скины": "Skins", "Миры и копии": "Worlds and backups", "Запуск и серверы": "Launching and servers",
    "Вылетает игра": "If the game crashes", "Настройки": "Settings",
    "Сборка из профилей": "A modpack from Profiles",
    "Сборку можно скачать и во вкладке «Профили»: кнопка «Скачать сборку» найдёт нужную и создаст из неё профиль.":
        "You can also get a modpack on the “Profiles” tab: the “Download a modpack” button finds it and creates a profile from it.",
    "Ставим ресурспак": "Installing a resource pack",
    "Во вкладке «Моды» переключись на «Ресурспаки», найди пак по названию и нажми «Установить». Лаунчер положит его в папку ресурспаков выбранной сборки.":
        "On the “Mods” tab switch to “Resource packs”, find a pack by name and press “Install”. The launcher puts it into the resource-packs folder of the selected build.",
    "Включаем в игре": "Turning it on in the game",
    "Дальше запусти игру и включи пак в самой игре: «Настройки» → «Ресурспаки». Паки можно сочетать и менять порядок.":
        "Then start the game and enable the pack there: “Options” → “Resource Packs”. Packs can be combined and reordered.",
    "Ставим шейдеры": "Installing shaders",
    "Переключись на «Шейдеры», найди нужный шейдер и нажми «Установить». Он ляжет в папку шейдеров выбранной сборки.":
        "Switch to “Shaders”, find the one you want and press “Install”. It goes into the shaders folder of the selected build.",
    "Чтобы шейдеры работали": "Making shaders work",
    "Шейдерам нужен мод-загрузчик, например Iris (для Fabric). Установи его во вкладке «Моды», а включить шейдер потом можно в игре: «Настройки» → «Качество» → «Шейдеры».":
        "Shaders need a shader loader mod such as Iris (for Fabric). Install it on the “Mods” tab, then enable the shader in the game: “Options” → “Video Settings” → “Shader Packs”.",
})


def topic_steps(key: str) -> list[tuple[str, str, str, str]]:
    return next(t[3] for t in TOPICS if t[0] == key)


def topic_title(key: str) -> str:
    return next(t[1] for t in TOPICS if t[0] == key)


def chapter_steps(chapter: str) -> list[tuple[str, str, str, str]]:
    return CHAPTERS[chapter][1]


def _mkbtn(app, ru: str, kind: str, fn) -> QPushButton:
    b = QPushButton(app.t(ru))
    b.setProperty("kind", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(lambda _=False: fn())
    return b


def build_ask_dialog(app):
    """Окно при первом запуске: «Не хотите пройти обучение?» и две кнопки. Возвращает (диалог, результат-список)."""
    from .widgets import Modal
    dlg = Modal(app, "Обучение", width=460)
    row = QHBoxLayout()
    row.setSpacing(14)
    face = QLabel()
    face.setPixmap(portrait_pixmap(app.ctx, "steve", 96))
    row.addWidget(face, 0, Qt.AlignTop)
    col = QVBoxLayout()
    who = QLabel(app.t("Стив"))
    who.setStyleSheet("font-weight: 800;")
    q = QLabel(app.t("Не хотите пройти обучение?"))
    q.setStyleSheet("font-size: 16px; font-weight: 700;")
    q.setWordWrap(True)
    col.addWidget(who)
    col.addWidget(q)
    col.addStretch(1)
    row.addLayout(col, 1)
    dlg.body.addLayout(row)
    answer: list[bool] = []
    dlg.add_button("Не надо", "ghost", lambda: answer.append(False), close=True)
    dlg.add_button("Да", "primary", lambda: answer.append(True), close=True)
    return dlg, answer


class TourPanel(QFrame):
    """Помощник в правом нижнем углу окна. Сначала Стив спрашивает, о чём рассказать (меню тем);
    выбрана тема — приходит другой герой и по шагам объясняет, переключая нужные вкладки."""

    def __init__(self, app, parent: QWidget, topic: str | None = None, on_close=None):
        super().__init__(parent)
        self.app = app
        self._on_close = on_close
        self.topic: str | None = None
        self.steps: list = []
        self.i = 0
        self._asked = False
        self.setObjectName("tour")
        self.setStyleSheet("QFrame#tour { background: #17171a; border: 1px solid rgba(255,255,255,70); border-radius: 16px; }")
        self.setFixedWidth(600)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)
        self.face = QLabel()
        self.face.setFixedSize(124, 124)
        self.face.setAlignment(Qt.AlignCenter)
        row.addWidget(self.face, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        row.addLayout(col, 1)
        head = QHBoxLayout()
        self.who = QLabel("")
        self.who.setStyleSheet("font-weight: 800; font-size: 13px; background: transparent; border: none;")
        head.addWidget(self.who)
        head.addStretch(1)
        self.count = QLabel("")
        self.count.setProperty("kind", "muted")
        head.addWidget(self.count)
        col.addLayout(head)
        self.title = QLabel("")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight: 700; font-size: 15px; background: transparent; border: none;")
        col.addWidget(self.title)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.text.setStyleSheet("background: transparent; border: none;")
        col.addWidget(self.text)
        # меню тем (кнопки в сетке)
        self.menu = QWidget()
        self.grid = QGridLayout(self.menu)
        self.grid.setContentsMargins(0, 2, 0, 0)
        self.grid.setSpacing(6)
        for n, (key, ru, gid, _steps) in enumerate(TOPICS):
            b = _mkbtn(app, ru, "small", lambda k=key: self.open_topic(k))
            b.setIcon(QIcon(portrait_pixmap(app.ctx, gid, 22)))
            self.grid.addWidget(b, n // 3, n % 3)
        col.addWidget(self.menu)
        col.addStretch(1)
        self.btns = QWidget()
        bl = QHBoxLayout(self.btns)
        bl.setContentsMargins(0, 0, 0, 0)
        self.b_menu = _mkbtn(app, "К темам", "small", self.show_menu)
        self.b_back = _mkbtn(app, "Назад", "ghost", self.back)
        self.b_next = _mkbtn(app, "Далее", "primary", self.next)
        bl.addWidget(self.b_menu)
        bl.addStretch(1)
        bl.addWidget(self.b_back)
        bl.addWidget(self.b_next)
        col.addWidget(self.btns)
        self.b_close = _mkbtn(app, "Хватит", "small", self.finish)
        col.addWidget(self.b_close, 0, Qt.AlignRight)
        if topic in TOPIC_ORDER:
            self.open_topic(topic)
        else:
            self.show_menu()
        self.raise_()
        self.show()

    # ----- меню: говорит Стив
    def show_menu(self) -> None:
        t = self.app.t
        self.topic = None
        self.face.setPixmap(portrait_pixmap(self.app.ctx, "steve", 124))
        self.who.setText(t("Стив"))
        self.count.setText("")
        if self._asked:
            self.title.setText(t("Рассказать ещё о чём-нибудь?"))
            self.text.setText("")
            self.text.setVisible(False)
        else:
            self.title.setText(t("Привет! Я Стив"))
            self.text.setText(t("О чём тебе рассказать? Выбери тему, и придёт помощник, который в ней разбирается."))
            self.text.setVisible(True)
        self.menu.setVisible(True)
        self.btns.setVisible(False)
        self.b_close.setVisible(True)
        self._fit()

    # ----- тема: говорит выбранный герой
    def open_topic(self, key: str) -> None:
        self.topic = key
        self._asked = True
        self.steps = topic_steps(key)
        self.i = 0
        self.menu.setVisible(False)
        self.b_close.setVisible(False)
        self.btns.setVisible(True)
        self.text.setVisible(True)
        self.show_step()

    def show_step(self) -> None:
        gid, page, title, text = self.steps[self.i]
        t = self.app.t
        self.face.setPixmap(portrait_pixmap(self.app.ctx, gid, 124))
        self.who.setText(t(GUIDES[gid]["name"]))
        self.title.setText(t(title))
        self.text.setText(t(text))
        self.count.setText(f"{self.i + 1} / {len(self.steps)}")
        self.b_back.setVisible(self.i > 0)
        self.b_next.setText(t("Готово") if self.i == len(self.steps) - 1 else t("Далее"))
        self.app.show_page(page)
        self._fit()

    def next(self) -> None:
        if self.i >= len(self.steps) - 1:
            self.app.call("achievements:grant", {"id": "tour"}, None, None)
            self.show_menu()  # тема закончилась — снова Стив: «рассказать ещё о чём-нибудь?»
        else:
            self.i += 1
            self.show_step()

    def back(self) -> None:
        if self.i > 0:
            self.i -= 1
            self.show_step()

    def finish(self) -> None:
        self.hide()
        self.deleteLater()
        if self._on_close:
            self._on_close()

    def _fit(self) -> None:
        self.adjustSize()
        self.reposition()

    def reposition(self) -> None:
        par = self.parentWidget()
        if par is None:
            return
        self.move(max(8, par.width() - self.width() - 16), max(8, par.height() - self.height() - 110))
        self.raise_()
