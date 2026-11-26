# DLauncher

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Electron](https://img.shields.io/badge/Electron-%E2%9C%94-47848F?logo=electron&logoColor=white)](https://www.electronjs.org/)

Современный лаунчер Minecraft с поддержкой Microsoft-аккаунтов, сборок, импорта из других лаунчеров и кастомизацией интерфейса.

## ✨ Возможности

- 🔐 Вход через Microsoft-аккаунт (OAuth, шифрование refresh-токена через `safeStorage`)
- 📦 Импорт сборок из Prism, CurseForge, официального лаунчера и др.
- ☕ Автоматическая загрузка Temurin Java под нужную версию
- 🎮 Профили с настройкой памяти и аргументов Java
- 🖼️ Кастомизация интерфейса: видео-фон, темы
- 💬 Discord Rich Presence
- 🏆 Собственные звуки достижений

## 📥 Установка

1. Скачай последний релиз со страницы [Releases](https://github.com/SpaceX-bit/DLauncher/releases).
2. Запусти `DLauncher.exe` (Windows).
3. Войди через Microsoft-аккаунт и выбери версию/сборку.

> **Сборка из исходников** — инструкция в разделе [Разработка](#-разработка).

## 🚀 Использование

1. Запусти лаунчер и авторизуйся через Microsoft (требуется владение Minecraft: Java Edition).
2. Создай профиль: выбери версию, память, при необходимости — аргументы Java.
3. Нажми «Играть». Лаунчер сам подтянет нужную Java и зависимости.

## 🛠️ Разработка

```bash
git clone https://github.com/SpaceX-bit/DLauncher.git
cd DLauncher
npm install
npm start
