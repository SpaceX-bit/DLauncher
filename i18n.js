// Перевод интерфейса. Исходный язык — русский: русский текст служит ключом.
// Для английского переводятся статический HTML, динамически вставленные элементы,
// атрибуты (placeholder/title) и сообщения из главного процесса — на лету, через MutationObserver.
// Ключ не найден — остаётся русский текст (ничего не ломается).
(function (root) {
  'use strict';

  const CYR = /[А-Яа-яЁё]/;

  const DC_HINT_RU =
    'Создай приложение на discord.com/developers/applications и скопируй его Application ID. ' +
    'В разделе Rich Presence → Art Assets загрузи картинку с именем logo — она станет значком. ' +
    'Discord должен быть запущен на этом компьютере.';
  const DC_HINT_EN =
    'Create an application at discord.com/developers/applications and copy its Application ID. ' +
    'Under Rich Presence → Art Assets upload an image named logo — it becomes the icon. ' +
    'Discord must be running on this computer.';

  // ---------- Точные соответствия ----------
  const EXACT = {
    // Навигация и главный экран
    'Играть': 'Play',
    'ИГРАТЬ': 'PLAY',
    'Профили': 'Profiles',
    'Моды': 'Mods',
    'Установлено': 'Installed',
    'Настройки': 'Settings',
    'Готов к игре': 'Ready to play',
    'Создай первый профиль, чтобы начать игру': 'Create your first profile to start playing',
    'Нет профилей': 'No profiles',
    'Профиль': 'Profile',
    'Корневая папка': 'Root folder',
    'Папка модов': 'Mods folder',
    'Оптимизация': 'Optimization',
    'Серверы': 'Servers',
    'Зайти на сервер, где ты играл в прошлый раз': 'Join the server you played on last time',

    // Профили
    'Импорт из других лаунчеров': 'Import from other launchers',
    'Новый профиль': 'New profile',
    'У каждого профиля своя версия игры, свой загрузчик и своя папка: моды, миры и настройки не смешиваются.':
      'Each profile has its own game version, mod loader and folder: mods, worlds and settings never mix.',
    'Профилей пока нет. Нажми «Новый профиль» или установи готовую сборку во вкладке «Моды» → «Сборки».':
      'No profiles yet. Click “New profile” or install a ready-made modpack in the “Mods” tab → “Modpacks”.',
    'Окно: весь экран': 'Window: fullscreen',
    'Выбран': 'Selected',
    'Выбрать': 'Select',
    'Настроить': 'Configure',
    'Папка': 'Folder',
    'Удалить': 'Delete',
    'Точно удалить?': 'Really delete?',
    'Точно?': 'Sure?',
    'Сборка': 'Modpack',
    'релиз': 'release',
    'снапшот': 'snapshot',
    'бета': 'beta',
    'альфа': 'alpha',

    // Статусы игры
    'Запуск...': 'Starting...',
    'Загрузка': 'Loading',
    'Загрузка...': 'Loading...',
    'Игра закрыта': 'Game closed',
    'Игра запущена': 'Game started',
    'Загрузка файлов игры...': 'Downloading game files...',
    'Не удалось загрузить список версий: проверь интернет': 'Could not load the version list: check your internet connection',
    'Игра уже запускается': 'The game is already starting',
    'Сначала создай профиль (вкладка «Профили»).': 'Create a profile first (the “Profiles” tab).',
    'Не удалось запустить игру. Проверь путь к Java в настройках.': 'Could not start the game. Check the Java path in settings.',
    'Неверный адрес сервера': 'Invalid server address',
    'Скачивание Forge...': 'Downloading Forge...',
    'Скачивание NeoForge...': 'Downloading NeoForge...',
    'Установка NeoForge (это займёт несколько минут)...': 'Installing NeoForge (this takes a few minutes)...',
    'NeoForge установлен, но версия не найдена в папке versions.': 'NeoForge is installed, but its version was not found in the versions folder.',
    'Эта система не поддерживается для автоматической загрузки Java': 'This system is not supported for automatic Java download',
    'Java скачана, но java не найдена в архиве': 'Java was downloaded, but the java executable was not found in the archive',

    // Моды
    'Ресурспаки': 'Resource packs',
    'Шейдеры': 'Shaders',
    'Сборки': 'Modpacks',
    'Поиск...': 'Search...',
    'Найти': 'Search',
    'Ищу...': 'Searching...',
    'Ничего не найдено': 'Nothing found',
    'Скачать': 'Download',
    'Установить': 'Install',
    'Готово': 'Done',
    'Ошибка': 'Error',
    'Сборка ставится как новый профиль: игра, загрузчик, моды и настройки скачаются сами.':
      'A modpack is installed as a new profile: the game, loader, mods and settings are downloaded automatically.',
    'Сначала создай профиль во вкладке «Профили» — моды ставятся в выбранный профиль.':
      'Create a profile in the “Profiles” tab first — mods are installed into the selected profile.',
    'Подготовка...': 'Preparing...',
    'Не удалось установить сборку': 'Could not install the modpack',
    'Все файлы сборки скачаны. Выбери профиль и нажми «ИГРАТЬ» — загрузчик установится при первом запуске.':
      'All modpack files are downloaded. Select the profile and press “PLAY” — the loader is installed on first launch.',
    'Установка сборки': 'Installing modpack',
    'Закрыть': 'Close',

    // Установленные моды
    'Установленные моды': 'Installed mods',
    'Открыть папку': 'Open folder',
    'Проверить обновления': 'Check for updates',
    'Обновить все': 'Update all',
    'Выключить': 'Disable',
    'Включить': 'Enable',
    'выключен': 'disabled',
    'В папке модов этого профиля пока пусто. Скачай моды во вкладке «Моды».':
      'This profile’s mods folder is empty. Download mods in the “Mods” tab.',
    'Сначала создай профиль во вкладке «Профили».': 'Create a profile in the “Profiles” tab first.',
    'проверяю обновления...': 'checking for updates...',
    'все моды актуальны': 'all mods are up to date',
    'нет связи с Modrinth — показаны только файлы': 'no connection to Modrinth — showing files only',
    'без модов': 'no mods',

    // Настройки
    'Аккаунт': 'Account',
    'Режим': 'Mode',
    'Офлайн (только ник)': 'Offline (nickname only)',
    'Microsoft (лицензия)': 'Microsoft (licensed)',
    'Ник (для офлайн-режима)': 'Nickname (offline mode)',
    'Client ID приложения Azure': 'Azure app Client ID',
    'Не выполнен вход': 'Not signed in',
    'Жду подтверждения входа...': 'Waiting for sign-in confirmation...',
    'Войти через Microsoft': 'Sign in with Microsoft',
    'Выйти': 'Sign out',
    'Для входа нужно своё приложение Azure — инструкция в README (раздел «Вход через Microsoft»).':
      'Signing in requires your own Azure app — see the README (section “Sign in with Microsoft”).',
    'Игра': 'Game',
    'Выделенная память:': 'Allocated memory:',
    'Путь к Java': 'Java path',
    'Пусто — Java скачается автоматически': 'Empty — Java will be downloaded automatically',
    'Нужная версия Java подбирается под версию Minecraft и скачивается сама при первом запуске.':
      'The right Java version is picked for your Minecraft version and downloaded automatically on first launch.',
    'Оформление': 'Appearance',
    'Язык / Language': 'Language',
    'Фон лаунчера': 'Launcher background',
    'Сейчас: стандартный фон': 'Now: default background',
    'Выбрать картинку или видео': 'Choose an image or video',
    'Сбросить фон': 'Reset background',
    'Затемнение фона:': 'Background dimming:',
    'Копирую файл...': 'Copying the file...',
    'Не удалось воспроизвести видео. Лучше всего подходят MP4 (H.264) и WEBM.': 'Could not play the video. MP4 (H.264) and WEBM work best.',
    'Не удалось открыть картинку. Попробуй PNG, JPG или WEBP.': 'Could not open the image. Try PNG, JPG or WEBP.',
    'Не удалось выбрать файл': 'Could not choose the file',
    'Файл уже копируется': 'The file is already being copied',
    'Это не файл': 'This is not a file',
    'Этот формат не поддерживается. Подходят: PNG, JPG, WEBP, GIF, BMP, AVIF, MP4, WEBM, M4V, OGV, MOV.': 'This format is not supported. Use PNG, JPG, WEBP, GIF, BMP, AVIF, MP4, WEBM, M4V, OGV or MOV.',
    'Файл слишком большой: картинки до 100 МБ, видео до 1 ГБ.': 'The file is too large: images up to 100 MB, videos up to 1 GB.',
    'видео': 'video',
    'картинка': 'image',
    'Liquid Glass — стеклянные панели с размытием и бликами': 'Liquid Glass — glass panels with blur and highlights',
    'Сила эффекта:': 'Effect strength:',
    'Предметы для Minecraft': 'Minecraft items',
    'Папки текущего профиля и быстрый переход к скачиванию с Modrinth / CurseForge.':
      'Folders of the current profile and quick links to download from Modrinth / CurseForge.',
    'Миры': 'Worlds',
    'Скриншоты': 'Screenshots',
    'Скачать ресурспаки': 'Download resource packs',
    'Скачать шейдеры': 'Download shaders',
    'Discord': 'Discord',
    'Показывать в Discord, во что я играю (Rich Presence)': 'Show in Discord what I’m playing (Rich Presence)',
    'Application ID приложения Discord': 'Discord application ID',
    'Выключено': 'Off',
    'Укажи Application ID': 'Enter an Application ID',
    'Жду запуска Discord...': 'Waiting for Discord to start...',
    'Подключено': 'Connected',
    'Discord не принял Application ID': 'Discord rejected the Application ID',
    [DC_HINT_RU]: DC_HINT_EN,
    'Обновление лаунчера': 'Launcher updates',
    'Адрес обновлений': 'Update address',
    'https://github.com/ник/репозиторий  или  https://мой-сайт/обновления/':
      'https://github.com/username/repository  or  https://my-site/updates/',
    'Проверяю обновления...': 'Checking for updates...',
    'Проверяю...': 'Checking...',
    'У тебя последняя версия': 'You have the latest version',
    'Работает в установленной версии (файл …-nsis.exe). Как это настроить — в README.':
      'Works in the installed version (the …-nsis.exe file). See the README for setup.',
    'Дополнительно': 'Advanced',
    'CurseForge API-ключ': 'CurseForge API key',
    'Получить: console.curseforge.com': 'Get it at: console.curseforge.com',
    'Сохранить': 'Save',
    'Сохранено ✓': 'Saved ✓',
    'ГБ': 'GB',
    'ГБ)': 'GB)',
    'Не выделяй больше, чем половину памяти компьютера.': 'Don’t allocate more than half of the computer’s memory.',

    // О разработчике
    'О разработчике': 'About the developer',
    'Тестировщик': 'Tester',
    'Разработчик': 'Developer',
    'DLauncher · версия': 'DLauncher · version',

    // Модальные окна
    'Название': 'Name',
    'Например: Выживание': 'e.g. Survival',
    'Тип версии': 'Version type',
    'Релизы': 'Releases',
    'Снапшоты': 'Snapshots',
    'Бета': 'Beta',
    'Альфа': 'Alpha',
    'Все': 'All',
    'Версия': 'Version',
    'Загрузчик модов': 'Mod loader',
    'Версия загрузчика': 'Loader version',
    'Отмена': 'Cancel',
    'Создать': 'Create',
    'Сборки в других лаунчерах': 'Modpacks in other launchers',
    'Выбери, что добавить в DLauncher. Файлы копируются в новые профили, а в старых лаунчерах ничего не меняется.':
      'Choose what to add to DLauncher. Files are copied into new profiles; nothing changes in the other launchers.',
    'Копировать миры (папка saves, может занять много места)': 'Copy worlds (the saves folder, may take a lot of space)',
    'Больше не спрашивать': 'Don’t ask again',
    'Позже': 'Later',
    'Импортировать': 'Import',
    'Импортировать ещё': 'Import more',
    'Отметь хотя бы одну сборку': 'Select at least one modpack',
    'Копирую...': 'Copying...',
    'Готово: профиль создан': 'Done: profile created',
    'уже импортирована': 'already imported',
    'Версия для импорта:': 'Version to import:',
    'Сборок в других лаунчерах не найдено. Поддерживаются Prism Launcher, PolyMC, MultiMC, приложение CurseForge, Modrinth App и официальный лаунчер Minecraft.':
      'No modpacks found in other launchers. Supported: Prism Launcher, PolyMC, MultiMC, the CurseForge app, Modrinth App and the official Minecraft launcher.',
    'Настройки профиля': 'Profile settings',
    'Память:': 'Memory:',
    'Как в общих настройках (': 'Same as general settings (',
    'Аргументы Java': 'Java arguments',
    'Ширина окна': 'Window width',
    'Высота окна': 'Window height',
    'авто': 'auto',
    'Запускать на весь экран': 'Launch in fullscreen',
    'Путь к Java (необязательно)': 'Java path (optional)',
    'Пусто — общий путь из настроек или автоматическая Java': 'Empty — the global path from settings, or automatic Java',
    'Память не нужно указывать в аргументах — для неё есть ползунок.': 'Don’t set memory in the arguments — use the slider for that.',
    'Название (необязательно)': 'Name (optional)',
    'Адрес: play.example.net или play.example.net:25566': 'Address: play.example.net or play.example.net:25566',
    'Добавить': 'Add',
    'Импорт из игры': 'Import from game',
    'Обновить статус': 'Refresh status',
    'Последний сервер:': 'Last server:',
    'Добавить в список': 'Add to list',
    'Зайти': 'Join',
    'проверяю...': 'checking...',
    'избранное': 'favorite',
    'Убрать из избранного': 'Remove from favorites',
    'В избранное': 'Add to favorites',
    'Серверов пока нет. Добавь адрес выше или нажми «Импорт из игры» — подтянутся серверы, которые ты добавил в самой игре.':
      'No servers yet. Add an address above or click “Import from game” to pull in the servers you added in the game itself.',
    'Вход через Microsoft': 'Sign in with Microsoft',
    'Открой страницу и введи этот код:': 'Open the page and enter this code:',
    'Страница откроется в браузере сама. Окно закроется, когда вход завершится.':
      'The page opens in your browser automatically. This window closes when sign-in completes.',
    'Копировать код': 'Copy code',
    'Скопировано': 'Copied',
    'Ищет моды для повышения FPS на Modrinth, а если там нет — на CurseForge (нужен API-ключ в Настройках) и скачивает их в папку модов выбранного профиля. Нужные зависимости (например, Fabric API) подтянутся сами.':
      'Looks for FPS-boosting mods on Modrinth and, if they’re not there, on CurseForge (needs an API key in Settings) and downloads them into the selected profile’s mods folder. Required dependencies (such as Fabric API) are fetched automatically.',
    'Установить всё': 'Install all',
    'Повторить': 'Retry',
    'Скачиваю...': 'Downloading...',
    'Для Vanilla оптимизация модами недоступна. Создай профиль с Fabric, Forge, NeoForge или Quilt.':
      'Mod optimization isn’t available for Vanilla. Create a profile with Fabric, Forge, NeoForge or Quilt.',
    'Перезапустить': 'Restart',

    // Описания модов оптимизации (главный процесс)
    'Новый движок отрисовки — главный буст FPS': 'A new rendering engine — the main FPS boost',
    'Оптимизация игровой логики и сервера': 'Optimizes game logic and the server',
    'Меньше потребление памяти': 'Lower memory usage',
    'Не рисует мобов, которых не видно': 'Doesn’t render mobs you can’t see',
    'Быстрее интерфейс и текст': 'Faster interface and text',
    'Быстрый запуск и меньше памяти': 'Faster startup and less memory',
    'Оптимизация сети': 'Network optimization',
    'Снижает нагрузку, когда окно не в фокусе': 'Reduces load when the window is out of focus',
    'Доп. настройки Sodium: облака, анимации, частицы': 'Extra Sodium options: clouds, animations, particles',
    'Ещё больше отсечения невидимых объектов': 'Even more culling of invisible objects',
    'Быстрое освещение мира': 'Fast world lighting',
    'Быстрее генерация новых территорий': 'Faster generation of new terrain',
    'Исправляет утечки памяти': 'Fixes memory leaks',
    'Движок отрисовки (аналог Sodium) — буст FPS': 'A rendering engine (a Sodium equivalent) — an FPS boost',

    // Ошибки и сообщения главного процесса
    'Не выбрана версия Minecraft': 'No Minecraft version selected',
    'Профиль не найден': 'Profile not found',
    'Память задаётся ползунком выше, а не в аргументах (-Xmx/-Xms)': 'Memory is set with the slider above, not in the arguments (-Xmx/-Xms)',
    'Название не может быть пустым': 'The name can’t be empty',
    'Память: нужно число': 'Memory: a number is required',
    'Ширина': 'Width',
    'Высота': 'Height',
    'Укажи ширину и высоту вместе (или оставь оба поля пустыми)': 'Specify width and height together (or leave both fields empty)',
    'Нельзя удалять профиль, пока запускается игра': 'You can’t delete a profile while the game is starting',
    'Для CurseForge нужен API-ключ: вставь его в Настройках (console.curseforge.com).':
      'CurseForge needs an API key: paste it in Settings (console.curseforge.com).',
    'В профиле выбран Vanilla — моды ставятся только на Fabric, Forge, NeoForge или Quilt. Создай профиль с загрузчиком.':
      'The profile uses Vanilla — mods can only be installed on Fabric, Forge, NeoForge or Quilt. Create a profile with a loader.',
    'Для Vanilla оптимизация модами недоступна — создай профиль с Fabric, Forge, NeoForge или Quilt.':
      'Mod optimization isn’t available for Vanilla — create a profile with Fabric, Forge, NeoForge or Quilt.',
    'не найден на CurseForge': 'not found on CurseForge',
    'файл не найден на CurseForge': 'file not found on CurseForge',
    'не картинка': 'not an image',
    'слишком большая': 'too large',
    'не совпала контрольная сумма': 'checksum mismatch',
    'не удалось определить версию игры': 'could not determine the game version',
    'Официальный лаунчер': 'Official launcher',
    'У этого аккаунта Microsoft нет профиля Xbox. Создай его на xbox.com и повтори вход.':
      'This Microsoft account has no Xbox profile. Create one at xbox.com and sign in again.',
    'Xbox Live недоступен в стране этого аккаунта.': 'Xbox Live isn’t available in this account’s country.',
    'Аккаунту нужна проверка возраста на xbox.com.': 'This account needs age verification at xbox.com.',
    'Это детский аккаунт: добавь его в семейную группу Microsoft.': 'This is a child account: add it to a Microsoft family group.',
    'Minecraft отклонил вход (403). Приложение Azure с этим Client ID, скорее всего, не одобрено Mojang для Minecraft API — см. README.':
      'Minecraft rejected the sign-in (403). The Azure app with this Client ID is probably not approved by Mojang for the Minecraft API — see the README.',
    'На этом аккаунте нет Minecraft: Java Edition.': 'This account doesn’t own Minecraft: Java Edition.',
    'Вход уже выполняется': 'Sign-in is already in progress',
    'Укажи Client ID приложения Azure в Настройках (см. README).': 'Enter the Azure app Client ID in Settings (see the README).',
    'Вход отменён': 'Sign-in cancelled',
    'Время на ввод кода истекло': 'The time to enter the code has run out',
    'Вход отклонён': 'Sign-in declined',
    'Войди через Microsoft в Настройках или переключись на офлайн-режим.': 'Sign in with Microsoft in Settings or switch to offline mode.',
    'Не указан Client ID приложения Azure (Настройки).': 'The Azure app Client ID is not set (Settings).',
    'Сессия Microsoft истекла — войди заново в Настройках.': 'The Microsoft session has expired — sign in again in Settings.',
    'Некорректный ответ сервера': 'Invalid server response',
    'нет ответа': 'no response',
    'адрес не найден': 'address not found',
    'не отвечает': 'not responding',
    'соединение закрыто': 'connection closed',
    'слишком большой ответ': 'response too large',
    'странный ответ сервера': 'unexpected server response',
    'обрыв файла': 'file truncated',
    'слишком глубокая вложенность': 'nesting too deep',
    'плохой список': 'bad list',
    'неизвестный тип NBT': 'unknown NBT type',
    'не NBT-файл': 'not an NBT file',
    'Неверный адрес. Пример: play.example.net или play.example.net:25566': 'Invalid address. Example: play.example.net or play.example.net:25566',
    'Такой сервер уже есть в списке': 'This server is already in the list',
    'Сервер не найден': 'Server not found',
    'Неверный адрес': 'Invalid address',
    'неверный адрес': 'invalid address',
    'Файл servers.dat не найден: сначала добавь сервер в самой игре и выйди из неё.':
      'servers.dat not found: add a server in the game first and exit it.',
    'недоступен': 'unavailable',
    'Получаю версию сборки...': 'Getting the modpack version...',
    'У сборки нет доступных версий': 'The modpack has no available versions',
    'Скачиваю сборку...': 'Downloading the modpack...',
    'В архиве нет modrinth.index.json — это не сборка Modrinth': 'The archive has no modrinth.index.json — this is not a Modrinth modpack',
    'В архиве нет manifest.json — это не сборка CurseForge': 'The archive has no manifest.json — this is not a CurseForge modpack',
    'В сборке не указана версия Minecraft': 'The modpack doesn’t specify a Minecraft version',
    'Копирую настройки сборки...': 'Copying modpack settings...',
    'У сборки нет доступных файлов': 'The modpack has no available files',
    'Получаю список файлов...': 'Getting the file list...',
    'Другая сборка уже устанавливается': 'Another modpack is already being installed',
    'Неверный файл': 'Invalid file',
    'Файл не найден': 'File not found',
    'Недопустимый адрес загрузки': 'Download address not allowed',
    'Импорт уже выполняется': 'An import is already in progress',
    'Сборка больше не найдена': 'The modpack is no longer found',
    'Автообновление работает только в собранной программе (.exe), не при запуске через npm start.':
      'Auto-update works only in the built program (.exe), not when started with npm start.',
    'Портативная версия не обновляется сама. Поставь версию с установщиком (…-nsis.exe).':
      'The portable version doesn’t update itself. Install the installer version (…-nsis.exe).',
    'Модуль electron-updater не найден. Выполни npm install и пересобери программу.':
      'The electron-updater module was not found. Run npm install and rebuild the program.',
    'Укажи адрес обновлений в Настройках.': 'Enter the update address in Settings.',
    'Это не ZIP-архив': 'This is not a ZIP archive',
    'Слишком большой архив (ZIP64) не поддерживается': 'Archives this large (ZIP64) are not supported',
    'Повреждённый ZIP': 'Corrupted ZIP',
    'Архив зашифрован': 'The archive is encrypted',
    'Неподдерживаемый способ сжатия в ZIP': 'Unsupported ZIP compression method',
  };

  const KINDS = { 'моды': 'mods', 'сборки': 'modpacks', 'ресурспаки': 'resource packs', 'шейдеры': 'shaders' };
  const REASONS = [
    'не совпала контрольная сумма', 'файл не найден на CurseForge', 'не найден на CurseForge',
    'не удалось определить версию игры', 'слишком большая', 'не картинка',
  ];

  // Перевод вложенного фрагмента; если его нет в словаре — как есть
  const T = (s) => translate(s) ?? s;
  const reasons = (s) => {
    let out = s;
    for (const r of REASONS) out = out.split(r).join(EXACT[r]);
    return out;
  };

  // ---------- Шаблоны для строк с подставленными значениями ----------
  // Каждое правило: [регулярка по тексту без крайних пробелов, функция(…группы) → строка]
  const RULES = [
    [/^Не удалось прочитать servers\.dat: ([\s\S]*)$/, (e) => 'Could not read servers.dat: ' + T(e)],
    [/^Не удалось прочитать: ([\s\S]+)$/, (e) => 'Could not read: ' + reasons(e)],
    [/^Не удалось распаковать Java: ([\s\S]*)$/, (e) => 'Could not unpack Java: ' + e],
    [/^Не удалось скачать \((.+?)\): ([\s\S]+)$/, (c, u) => `Download failed (${c}): ${u}`],
    [/^Ошибка обновления: ([\s\S]*)$/, (e) => 'Update error: ' + T(e)],
    [/^Ошибка входа \(([\s\S]+)\)$/, (e) => `Sign-in error (${e})`],
    [/^Ошибка: ([\s\S]+)$/, (e) => 'Error: ' + T(e)],
    [/^Xbox отклонил вход \(([\s\S]+)\)$/, (e) => `Xbox rejected the sign-in (${e})`],
    [/^Minecraft отклонил вход \((\d+)\)$/, (c) => `Minecraft rejected the sign-in (${c})`],
    [/^Установщик NeoForge завершился с ошибкой \((.*?)\)\. ([\s\S]*)$/, (c, t) => `The NeoForge installer failed (${c}). ${t}`.trim()],
    [/^Аргумент «(.+)» должен начинаться с «-»$/, (a) => `Argument “${a}” must start with “-”`],
    [/^(.+): число от 320 до 7680$/, (l) => `${T(l)}: a number from 320 to 7680`],
    [/^Не больше (\d+) серверов в профиле$/, (n) => `No more than ${n} servers per profile`],
    [/^Небезопасный путь: ([\s\S]+)$/, (p) => 'Unsafe path: ' + p],
    [/^Нет версии для (.+)$/, (v) => 'No version for ' + v],
    [/^Нет файла для (.+)$/, (v) => 'No file for ' + v],

    // Профили
    [/^Зайти на (.+)$/, (h) => 'Join ' + h],
    [/^На сервер: (.+)$/, (h) => 'Join: ' + h],
    [/^Сервер: (.+)$/, (h) => 'Server: ' + h],
    [/^Память: ([\d.,]+) ГБ$/, (n) => `Memory: ${n} GB`],
    [/^Окно: (\d+)×(\d+)$/, (w, h) => `Window: ${w}×${h}`],
    [/^Серверов: (\d+)$/, (n) => 'Servers: ' + n],
    [/^Сборка (.+)$/, (v) => 'Modpack ' + v],
    [/^Модов: (\d+)$/, (n) => 'Mods: ' + n],
    [/^Миров: (\d+)$/, (n) => 'Worlds: ' + n],
    [/^Запуск: (.+)$/, (d) => 'Last played: ' + d],
    [/^Профиль «(.+)» — Vanilla\. Для модов создай профиль с Fabric \/ Forge \/ NeoForge \/ Quilt\.$/,
      (n) => `Profile “${n}” is Vanilla. For mods, create a profile with Fabric / Forge / NeoForge / Quilt.`],
    [/^Профиль «(.+)»$/, (n) => `Profile “${n}”`],
    [/^Настройки профиля: (.+)$/, (n) => 'Profile settings: ' + n],

    // Моды
    [/^Моды для профиля «(.+)»: Minecraft (.+)$/, (n, v) => `Mods for profile “${n}”: Minecraft ${v}`],
    [/^Шейдеры для профиля «(.+)» \(Minecraft (.+)\)\. Нужен мод Iris \(Fabric\/Quilt\) или Oculus \(Forge\) — найди его во вкладке «Моды»\.$/,
      (n, v) => `Shaders for profile “${n}” (Minecraft ${v}). You need the Iris mod (Fabric/Quilt) or Oculus (Forge) — find it in the “Mods” tab.`],
    [/^Ресурспаки для профиля «(.+)» \(Minecraft (.+)\)$/, (n, v) => `Resource packs for profile “${n}” (Minecraft ${v})`],
    [/^Поиск: (.+)\.\.\.$/, (k) => `Search: ${KINDS[k] || k}...`],
    [/^Установка: (.+)$/, (t) => 'Installing: ' + t],
    [/^Готово: создан профиль «(.+)»$/, (n) => `Done: profile “${n}” created`],
    [/^Не скачалось файлов: (\d+) \(([\s\S]*)\)\. Часть модов можно докачать вручную\.$/,
      (n, list) => `Files not downloaded: ${n} (${reasons(list)}). Some mods can be downloaded manually.`],
    [/^Установлено: (.+?)(?: \(\+(\d+) необходимых зависимостей\))?$/,
      (f, n) => `Installed: ${f}` + (n ? ` (+${n} required dependencies)` : '')],
    [/^Показать ещё \(осталось (.+)\)$/, (n) => `Show more (${n} left)`],
    [/^Обновить все \((\d+)\)$/, (n) => `Update all (${n})`],
    [/^Обновить до (.+)$/, (v) => 'Update to ' + v],
    [/^доступно обновлений: (\d+)$/, (n) => 'updates available: ' + n],
    [/^Обновляю (\d+)\/(\d+): ([\s\S]+)$/, (a, b, t) => `Updating ${a}/${b}: ${t}`],
    [/^Обновлено модов: (\d+) из (\d+)$/, (a, b) => `Mods updated: ${a} of ${b}`],

    // Импорт
    [/^Создаю профиль «(.+)» \((\d+)\/(\d+)\)$/, (n, a, b) => `Creating profile “${n}” (${a}/${b})`],
    [/^«(.+)»: копирую (.+)$/, (n, i) => `“${n}”: copying ${i}`],
    [/^Импортировано сборок: (\d+) из (\d+)\. Они появились во вкладке «Профили»\.$/,
      (a, b) => `Modpacks imported: ${a} of ${b}. They now appear in the “Profiles” tab.`],

    // Серверы
    [/^Найдено в игре: (\d+), добавлено новых: (\d+)$/, (a, b) => `Found in game: ${a}, new added: ${b}`],
    [/^· (\d+) мс(.*)$/, (n, rest) => `· ${n} ms${rest}`],
    [/^недоступен \(([\s\S]+)\)$/, (e) => `unavailable (${T(e)})`],

    // Оптимизация
    [/^Готово: установлено (\d+) \(Modrinth: (\d+), CurseForge: (\d+)\)(?:, недоступно для этой версии: (\d+))?(?:, ошибок: (\d+))?(\. Чтобы искать и на CurseForge, добавь API-ключ в Настройках\.)?$/,
      (n, m, c, sk, f, key) =>
        `Done: ${n} installed (Modrinth: ${m}, CurseForge: ${c})` +
        (sk ? `, unavailable for this version: ${sk}` : '') +
        (f ? `, errors: ${f}` : '') +
        (key ? '. To search CurseForge too, add an API key in Settings.' : '')],

    // Microsoft и обновления
    [/^Сейчас: (.+)$/, (n) => 'Now: ' + (T(n))],
    [/^Не удалось скопировать файл: ([\s\S]*)$/, (e) => 'Could not copy the file: ' + e],
    [/^Вход выполнен: (.+)$/, (n) => 'Signed in: ' + n],
    [/^Подключено: (.+)$/, (n) => 'Connected: ' + n],
    [/^Найдена версия (.*) — скачиваю\.\.\.$/, (v) => `Found version ${v} — downloading...`.replace('  ', ' ')],
    [/^Скачиваю обновление: (\d+)%$/, (n) => `Downloading update: ${n}%`],
    [/^Обновление (.*) готово — перезапусти лаунчер$/, (v) => `Update ${v} is ready — restart the launcher`.replace('  ', ' ')],
    [/^Версия лаунчера: (.+)$/, (v) => 'Launcher version: ' + v],
    [/^Всего в системе: (\d+) ГБ\. Для Vanilla хватит 2–4 ГБ, для модов обычно 4–8 ГБ\. Не выделяй больше, чем половину памяти компьютера\.$/,
      (n) => `Total in system: ${n} GB. 2–4 GB is enough for Vanilla, mods usually need 4–8 GB. Don’t allocate more than half of the computer’s memory.`],

    // Запуск, скачивание
    [/^Игра завершилась с кодом (-?\d+)$/, (c) => `The game exited with code ${c}`],
    [/^Скачивание Java (\d+)\.\.\.$/, (v) => `Downloading Java ${v}...`],
    [/^Распаковка Java (\d+)\.\.\.$/, (v) => `Unpacking Java ${v}...`],
    [/^Подготовка (.+)\.\.\.$/, (l) => `Preparing ${l}...`],
    [/^Скачиваю файлы сборки: (\d+)\/(\d+)$/, (a, b) => `Downloading modpack files: ${a}/${b}`],
    [/^Скачиваю сборку: (\d+)%$/, (n) => `Downloading the modpack: ${n}%`],
    [/^(.+): (\d+)%$/, (l, n) => (translate(l) ? `${translate(l)}: ${n}%` : null)],

    // Единицы
    [/^([\d.,]+) ГБ$/, (n) => `${n} GB`],
    [/^([\d.,]+) МБ$/, (n) => `${n} MB`],
    [/^([\d.,]+) КБ$/, (n) => `${n} KB`],
  ];

  function translate(str) {
    if (typeof str !== 'string' || !CYR.test(str)) return null;
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(str);
    const core = m[2];
    if (!core) return null;
    let out = EXACT[core];
    if (out === undefined) {
      for (const [re, fn] of RULES) {
        const r = re.exec(core);
        if (!r) continue;
        const v = fn(...r.slice(1));
        if (v != null) { out = v; break; }
      }
    }
    // Составные строки «a · b · c»: переводим части по отдельности
    if (out === undefined && core.includes(' · ')) {
      let any = false;
      const parts = core.split(' · ').map((p) => {
        const t = translate(p);
        if (t != null) any = true;
        return t != null ? t : p;
      });
      if (any) out = parts.join(' · ');
    }
    if (out === undefined) return null;
    return m[1] + out + m[3];
  }

  // ---------- DOM ----------
  const ATTRS = ['placeholder', 'title', 'aria-label'];
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA']);
  let observer = null;
  let lang = 'ru';

  function tx(node) {
    const t = translate(node.nodeValue);
    if (t != null && t !== node.nodeValue) node.nodeValue = t;
  }
  function txAttrs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute && el.getAttribute(a);
      if (!v) continue;
      const t = translate(v);
      if (t != null && t !== v) el.setAttribute(a, t);
    }
  }
  function walk(node) {
    if (node.nodeType === 3) return tx(node);
    if (node.nodeType !== 1 || SKIP.has(node.tagName)) return;
    txAttrs(node);
    for (let c = node.firstChild; c; c = c.nextSibling) walk(c);
  }

  function start() {
    if (observer || typeof document === 'undefined') return;
    document.documentElement.lang = 'en';
    walk(document.documentElement);
    observer = new MutationObserver((list) => {
      for (const m of list) {
        if (m.type === 'childList') m.addedNodes.forEach(walk);
        else if (m.type === 'characterData') { if (!SKIP.has(m.target.parentNode && m.target.parentNode.tagName)) tx(m.target); }
        else if (m.type === 'attributes') txAttrs(m.target);
      }
    });
    observer.observe(document.documentElement, {
      subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS,
    });
  }

  function setLang(l) {
    lang = l === 'en' ? 'en' : 'ru';
    try { localStorage.setItem('dl-lang', lang); } catch { /* без хранилища язык берётся из настроек */ }
    api.lang = lang;
    if (lang === 'en') start();
  }

  const api = {
    lang,
    translate,
    setLang,
    // L('русский', 'english') — выбрать текст по языку (для чисел, дат и т. п.)
    L: (ru, en) => (lang === 'en' ? en : ru),
    locale: () => (lang === 'en' ? 'en-US' : 'ru-RU'),
  };

  // Язык запоминаем в localStorage, чтобы окно сразу открывалось на нужном языке, без мелькания русского
  if (typeof document !== 'undefined') {
    let saved = 'ru';
    try { saved = localStorage.getItem('dl-lang') === 'en' ? 'en' : 'ru'; } catch { /* ru */ }
    setLang(saved);
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { translate, EXACT, RULES };
  root.I18N = api;
})(typeof window !== 'undefined' ? window : globalThis);
