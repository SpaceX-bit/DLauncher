@echo off
chcp 65001 >nul
title Сборка DLauncher
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js не найден. Установи его с https://nodejs.org ^(версия LTS^) и запусти этот файл снова.
  pause
  exit /b 1
)

rem Репозиторий GitHub для автообновления (спрашиваем один раз, ответ сохраняется в update-config.json)
node -e "process.exit(require('./update-config.json').repo?0:1)" >nul 2>nul
if not errorlevel 1 goto haverepo
echo.
echo Автообновление: впиши свой репозиторий GitHub в виде ник/репозиторий.
echo Лаунчер сам скачает новую версию, как только ты выложишь её в Releases этого репозитория.
echo Если автообновление не нужно, просто нажми Enter.
set "UPD_REPO="
set /p UPD_REPO=Репозиторий: 
if "%UPD_REPO%"=="" goto haverepo
node -e "require('fs').writeFileSync('update-config.json',JSON.stringify({repo:process.argv[1]},null,2)+'\n')" "%UPD_REPO%"
:haverepo
echo.

echo [1/2] Установка зависимостей...
call npm install
if errorlevel 1 goto fail

echo [2/2] Сборка .exe ^(первый раз может занять несколько минут^)...
call npm run build
if errorlevel 1 goto retry
goto built

:retry
rem Если сборка упала из-за дополнительного шага мастера установки, пробуем со стандартным мастером
if not exist "build\installer.nsh" goto fail
echo.
echo Сборка не удалась. Пробую ещё раз со стандартным мастером установки ^(без шага с ярлыком^)...
ren "build\installer.nsh" installer.nsh.off
call npm run build
if errorlevel 1 (
  ren "build\installer.nsh.off" installer.nsh
  goto fail
)
echo ^(Установщик собран без дополнительного шага; ярлык на рабочем столе он создаёт сам.^)

:built

echo.
echo Готово! Файлы лежат в папке dist:
echo   DLauncher-<версия>-x64-portable.exe  - один файл, запускается без установки
echo   DLauncher-<версия>-x64-nsis.exe      - мастер установки: выбор диска и папки, ярлык на рабочем столе, запуск после установки; обновляется сам
start "" "%~dp0dist"
pause
exit /b 0

:fail
echo.
echo Сборка не удалась. Если в ошибке есть "symbolic link" - включи Режим разработчика
echo ^(Параметры Windows - Для разработчиков^) или запусти этот файл от имени администратора.
pause
exit /b 1
