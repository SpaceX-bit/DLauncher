<div align="center">

# 🚀 DLauncher

**Современный лаунчер Minecraft: Microsoft-аккаунты, сборки, кастомизация — всё в одном месте.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Electron](https://img.shields.io/badge/Electron-%E2%9C%94-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](#)
[![Release](https://img.shields.io/github/v/release/SpaceX-bit/DLauncher?include_prereleases&label=latest)](https://github.com/SpaceX-bit/DLauncher/releases)
[![Downloads](https://img.shields.io/github/downloads/SpaceX-bit/DLauncher/total)](https://github.com/SpaceX-bit/DLauncher/releases)
[![Issues](https://img.shields.io/github/issues/SpaceX-bit/DLauncher)](https://github.com/SpaceX-bit/DLauncher/issues)

[Возможности](#-возможности) • [Установка](#-установка) • [Использование](#-использование) • [Сборка](#-сборка-из-исходников) • [FAQ](#-faq) • [Помощь](#-проблемы-и-их-решение)

</div>

---

## 📖 О проекте

**DLauncher** — это лёгкий и функциональный лаунчер для Minecraft: Java Edition, написанный на Electron с нуля. Он решает главные боли игроков: сложную авторизацию Microsoft, ручную установку Java, перенос сборок из других лаунчеров и скучный интерфейс.

Проект полностью авторский — весь код написан с нуля, без форков чужих лаунчеров. Все звуки и ассеты созданы автором.

> ⚠️ **Важно:** для игры требуется приобретённая копия Minecraft: Java Edition. Лаунчер не обходит лицензию и не поддерживает пиратские аккаунты.

---

## ✨ Возможности

### 🔐 Аккаунты и авторизация
- Вход через **Microsoft-аккаунт** (официальный OAuth-флоу)
- Безопасное хранение refresh-токена — шифрование через Electron `safeStorage` (Windows DPAPI)
- Поддержка **нескольких аккаунтов** с быстрым переключением
- Автоматическое обновление сессии без повторного входа

### 📦 Сборки и версии
- Импорт сборок из **Prism Launcher**, **CurseForge**, **официального лаунчера** и других
- Поддержка **Forge**, **Fabric**, **Quilt**, **NeoForge**
- Управление профилями: версия, моды, ресурспаки, шейдеры
- Быстрое переключение между профилями

### ☕ Java и окружение
- **Автоматическая загрузка Temurin JDK** под нужную версию Minecraft
- Выбор конкретной версии Java вручную (если нужно)
- Настройка объёма памяти (Xmx/Xms) и JVM-аргументов на профиль

### 🎨 Интерфейс
- Видео-фон и настраиваемые темы
- Собственные звуки достижений
- Плавные анимации и адаптивная вёрстка

### 💬 Интеграции
- **Discord Rich Presence** — статус в Discord («Играет в Minecraft», версия, профиль)
- Автообновление лаунчера (проверка новых версий через GitHub Releases)

---

## 📥 Установка

### Готовый бинарник (рекомендуется)

1. Перейди на страницу [**Releases**](https://github.com/SpaceX-bit/DLauncher/releases).
2. Скачай последний `DLauncher-Setup-x.x.x.exe` (или portable-версию).
3. Запусти установщик и следуй инструкциям.
4. Открой DLauncher → войди через Microsoft → выбери версию → играй.

**Требования:**
- Windows 10/11 (x64)
- 4 ГБ ОЗУ (рекомендуется 8+ ГБ для сборок с модами)
- Интернет для первого запуска (загрузка Java и библиотек)

---

## 🚀 Использование

### Первый запуск

1. **Авторизация.** Нажми «Войти через Microsoft» → откроется браузер → введи данные аккаунта → разреши доступ → вернись в лаунчер.
2. **Создание профиля.** Выбери версию Minecraft (например, `1.20.4`), при необходимости — модлоадер (Fabric/Forge), выдели память.
3. **Запуск.** Нажми «Играть» — лаунчер сам скачает нужную Java, библиотеки и ассеты.

### Импорт сборки

1. Открой меню **«Сборки» → «Импорт»**.
2. Укажи путь к папке сборки (например, из Prism: `instances/ИмяСборки`) или к `.zip`-архиву.
3. Лаунчер распознает моды, версию и модлоадер автоматически.

### Настройка профиля

- **Память:** от 2 ГБ для ваниллы, 4–8 ГБ для сборок с модами.
- **JVM-аргументы:** например, `-XX:+UseG1GC -XX:MaxGCPauseMillis=50` для стабильного FPS.
- **Java:** оставь «Авто», если не уверен.

---

## 🛠️ Сборка из исходников

### Требования
- [Node.js](https://nodejs.org/) **18+**
- [Git](https://git-scm.com/)
- Windows (для сборки `.exe`)

### Шаги

```bash
# 1. Клонируй репозиторий
git clone https://github.com/SpaceX-bit/DLauncher.git
cd DLauncher

# 2. Установи зависимости
npm install

# 3. Запусти в режиме разработки
npm start

# 4. Собери .exe (Windows)
npm run build
