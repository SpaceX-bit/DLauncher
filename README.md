# DLauncher 2.0 (Python + Qt)

Лаунчер Minecraft, переписанный с Electron на **Python + PySide6 (Qt)**. Сама игра не изменяется: лаунчер только скачивает
файлы Mojang (клиент, библиотеки, ресурсы), загрузчики (Fabric, Quilt, Forge, NeoForge) и Java, и запускает игру.

## Как собрать установщик (всё делается с телефона)

1. В репозитории замени файл **`.github/workflows/build.yml`** на тот, что лежит в этом архиве
   (GitHub → файл → значок карандаша → вставить текст → Commit). Старый файл ищет `package.json` и со словом «Electron» уже не подходит.
2. Загрузи **zip этого проекта** в корень репозитория (Add file → Upload files). Старые zip можно удалить или оставить —
   берётся тот, где в `dlauncher/__init__.py` версия новее.
3. Actions → **Build Windows installer** → **Run workflow**.
4. Когда рядом с запуском появится зелёная галочка, открой запуск → внизу **Artifacts → DLauncher-windows** → скачай.
   Внутри `DLauncher-Setup-2.0.27.exe`. Если сборка красная, открой её, найди красный шаг и пришли мне текст ошибки.

Сборка сама проверяет программу: шаг **Interface self-test** открывает все вкладки без окна и падает, если где-то ошибка.

## Установка

Мастер установки спрашивает: **в какую папку и на какой диск** поставить, ставить ли **ярлык на рабочий стол**,
и **запустить ли DLauncher** после установки. Права администратора не нужны.

Настройки, профили, миры и моды из прошлой версии (Electron) подхватываются сами: папка данных `%APPDATA%\DLauncher`
и корневая папка `~/.dlauncher` те же. Не переносится только вход Microsoft — войди заново (Настройки → Аккаунт).

## Возможности

Профили (версия, загрузчик, память, JVM-аргументы, окно, серверы), автоматическая Java, моды / модпаки / ресурспаки / шейдеры
из Modrinth и CurseForge с выбором версии и значками загрузчиков, проверка совместимости модов, аккаунты Microsoft
(несколько), Ely.by и офлайн, Discord Rich Presence, резервные копии миров, скины и плащи, скриншоты, статистика, новости,
разбор вылетов, консоль игры, трей и автозапуск, темы и стекло, русский/английский, импорт из TLauncher, Prism/MultiMC,
CurseForge и Modrinth App, автообновление через GitHub, достижения (всплывающие поздравления и вкладка со всеми значками), автообновление модов перед запуском (включается в настройках), экспорт сборки в .mrpack (меню «⋯» у сборки), обучение: при первом запуске спрашивает «Не хотите пройти обучение?», дальше Стив даёт выбрать тему, а про каждую тему рассказывает свой герой (кнопка «Обучение» внизу левой панели открывает его снова и рассказывает про весь лаунчер), свой цвет, значок и группа для каждой сборки, статус избранного сервера (онлайн, пинг, игроки) на карточке, кнопка «Подобрать» память, звук достижения (выключается в настройках), окно «Что нового» после обновления, окно «Вышло обновление» (Скачать / Позже), перетаскивание файлов в окно, дублирование сборки, обновление сборок Modrinth на месте, откат модов, код сборки, оформления и цвет лаунчера, проверка места/Java/памяти перед запуском.

## Вход через Ely.by

Настройки → Аккаунт → режим **Ely.by** → «Войти через Ely.by». Нужны логин (или почта) и пароль с ely.by; если включена
двухфакторная защита, лаунчер попросит код. Пароль не сохраняется — хранится только токен входа. При первом запуске скачивается
authlib-injector (маленький .jar, который подключает игру к серверам Ely.by). Скин меняется на сайте ely.by.

## Вход через Microsoft

Нужно один раз завести своё приложение Azure:

1. [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Тип аккаунтов — **Personal Microsoft accounts only** (или «…and organizations»).
3. **Authentication** → включи **Allow public client flows** → Save.
4. Скопируй **Application (client) ID** → Настройки → Аккаунт → «Client ID приложения Azure» → «Добавить аккаунт».
5. Если после входа ошибка 403 — приложение ещё не одобрено Mojang (форма: https://aka.ms/AppRegInfo). Пока — офлайн-режим.

## Code signing policy

*Политика подписи кода (для SignPath Foundation и тех, кто хочет знать, что подписывается и кем).*

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).

**What is signed.** Only the Windows installer `DLauncher-Setup-<version>.exe`, built by the GitHub Actions workflow
[`.github/workflows/build.yml`](.github/workflows/build.yml) from the source code in this repository (the build scripts and CI
configuration are part of the source). Every build uses the product name "DLauncher", and the product version is taken from
`dlauncher/__init__.py`. Nothing built anywhere else is signed. No third-party or proprietary binaries are added by the project;
the installer contains the Python runtime and Qt (PySide6, LGPL), packaged with PyInstaller.

**License.** MIT (see [LICENSE](LICENSE)); all dependencies are under OSI-approved licenses.

**Team roles.**
- Authors, committers and reviewers: [SpaceX-bit](https://github.com/SpaceX-bit) (repository owner).
- Approvers: [SpaceX-bit](https://github.com/SpaceX-bit). Every signing request is approved manually before it is signed.
- All team members use multi-factor authentication on GitHub and SignPath.

**Privacy policy.** DLauncher has no telemetry, analytics or advertising, and nothing is sent to the developers. The program connects
to other networked systems only to do what the user asks of it:
- game files, libraries, assets and Java: Mojang (`launchermeta.mojang.com`, `libraries.minecraft.net`, `resources.download.minecraft.net`) and Adoptium;
- mod loaders: Fabric, Quilt, Forge and NeoForge servers;
- mods, resource packs, shaders and modpacks: Modrinth and CurseForge (search terms and file requests only);
- sign-in, only if the user chooses it: Microsoft/Xbox/Minecraft services, or Ely.by (with authlib-injector downloaded from its official site);
- update check: GitHub (the public releases of this repository);
- sharing a log, only when the user presses "Share log" and confirms: mclo.gs (tokens and the user-folder name are removed first);
- mod icons: Modrinth/CurseForge CDNs, or the public image proxy wsrv.nl if a CDN is unreachable (only the public icon address is sent);
- server status: only the servers the user added to a build.

Sign-in tokens are stored on the user's computer (encrypted with Windows DPAPI); passwords are never stored.

## Подпись установщика

Без подписи Windows показывает «Неизвестный издатель» и SmartScreen. Подпись включается в workflow сама, когда в репозитории
есть нужные настройки (Settings → Secrets and variables → Actions). Без них сборка идёт как раньше, без подписи.

**Вариант А: свой сертификат подписи кода (.pfx).** Секреты (вкладка Secrets): `CODESIGN_PFX` (файл .pfx, закодированный в base64)
и `CODESIGN_PASSWORD`. Подписываются `DLauncher.exe` и установщик.

**Вариант Б: бесплатный SignPath Foundation** (только для открытых проектов, нужна заявка на signpath.org/apply и OSI-лицензия
у проекта). Секрет `SIGNPATH_API_TOKEN` и переменные (вкладка Variables) `SIGNPATH_ORG_ID`, `SIGNPATH_PROJECT`, `SIGNPATH_POLICY`.
В SignPath в «Artifact configuration» нужен такой файл:

```xml
<artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
  <zip-file>
    <pe-file path="DLauncher-Setup-*.exe">
      <authenticode-sign/>
    </pe-file>
  </zip-file>
</artifact-configuration>
```

В логе сборки шаг «Show installer signature» показывает, подписан ли установщик. Даже с подписью SmartScreen
может некоторое время предупреждать: репутация набирается по числу скачиваний.

## Запуск из исходников (для разработчиков)

```
pip install -r requirements.txt
python main.py              # обычный запуск
python main.py --selftest   # проверка интерфейса без окна (код выхода 0 — всё хорошо)
python -m pytest -q         # тесты ядра (Linux/macOS)
```

## Что изменилось по сравнению с 1.7.5

* Нет Electron/Chromium: окно рисует Qt, ядро — на Python. Игра запускается собственным движком (`dlauncher/core/minecraft.py`).
* Только Windows x64 (32-битной сборки нет).
* «Liquid Glass» упрощён (полупрозрачные панели без размытия фона), 3D-просмотр скина заменён плоским видом спереди/сзади.
* Рамка окна системная.
* Скрытая картинка: 5 нажатий подряд на «Разработчик» в Настройках → «О программе». «Тестировщик» — там же.
