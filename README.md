# DLauncher

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/SpaceX-bit/DLauncher)](https://github.com/SpaceX-bit/DLauncher/releases)
[![Issues](https://img.shields.io/github/issues/SpaceX-bit/DLauncher)](https://github.com/SpaceX-bit/DLauncher/issues)

**DLauncher** — лёгкий лаунчер для Minecraft на Electron.

> ⚠️ **Поддерживается только Windows (10/11).** Linux и macOS не поддерживаются.

## ✨ Возможности

- 🚀 Быстрый запуск Minecraft [укажи версии]
- 🧩 Поддержка **[Forge / Fabric / Quilt / NeoForge]**
- 📦 Установка модпаков в один клик
- 👤 Управление несколькими профилями игроков
- 🔄 Автообновление лаунчера

## 💻 Поддерживаемые ОС

| Платформа | Статус | Файл релиза |
|-----------|--------|-------------|
| 🪟 Windows 10/11 | ✅ Поддерживается | `DLauncher-Setup-x.x.x.exe` |
| 🐧 Linux | ❌ Не поддерживается | — |
| 🍎 macOS | ❌ Не поддерживается | — |

## 📥 Скачать

Готовые сборки — в разделе [**Releases**](https://github.com/SpaceX-bit/DLauncher/releases).

1. Скачай `DLauncher-Setup-x.x.x.exe` из последнего релиза
2. Запусти установщик и следуй инструкциям
3. Если Windows SmartScreen показывает предупреждение (файл без цифровой подписи) — нажми **«Подробнее» → «Выполнить в любом случае»**

> 💡 Java устанавливать не нужно — она встроена в лаунчер.

## 🛠️ Сборка из исходников

Требуется **Node.js 18+** ([скачать](https://nodejs.org/)).

```bash
git clone https://github.com/SpaceX-bit/DLauncher.git
cd DLauncher
npm install
npm start          # запуск в режиме разработки
