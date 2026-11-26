"""Единая точка входа для интерфейса: api.call('канал:имя', payload) -> результат.

Каждый модуль core может определять:
  handlers(ctx) -> {канал: функция(payload)}   — обработчики (как ipcMain.handle в Electron-версии)
  setup(ctx)                                  — запуск при старте (подключает сервисы: ctx.msauth, ctx.stats, …)
  shutdown(ctx)                               — остановка при выходе
  on_settings_changed(ctx)                    — вызывается после settings:set
Отсутствующий модуль пропускается (так можно собирать и проверять лаунчер по частям).
"""
from __future__ import annotations

import importlib
import threading
from typing import Any

from .core.ctx import Ctx

# Порядок важен: сервисы раньше launch
MODULES = [
    "base", "gamelog", "stats", "achievements", "discord", "msauth", "worlds", "servers", "autostart",
    "loaders", "java", "launch",
    "mods", "modsmgr", "modpacks", "profileio", "compat", "importer",
    "updater", "news", "crash", "shots", "skins",
]


class Api:
    def __init__(self, ctx: Ctx | None = None, modules: list[str] | None = None):
        self.ctx = ctx or Ctx()
        self.handlers: dict[str, Any] = {}
        self.modules: dict[str, Any] = {}
        self.missing: list[str] = []
        self._lock = threading.Lock()
        for name in (modules or MODULES):
            full = f"dlauncher.core.{name}"
            try:
                mod = importlib.import_module(full)
            except ModuleNotFoundError as e:
                if e.name == full:
                    self.missing.append(name)
                    continue
                raise
            self.modules[name] = mod
        for name, mod in self.modules.items():
            setup = getattr(mod, "setup", None)
            if callable(setup):
                setup(self.ctx)
        for name, mod in self.modules.items():
            h = getattr(mod, "handlers", None)
            if callable(h):
                self.handlers.update(h(self.ctx))
        self.ctx.on_settings_changed = self._settings_changed

    def _settings_changed(self) -> None:
        for name, mod in self.modules.items():
            fn = getattr(mod, "on_settings_changed", None)
            if callable(fn):
                try:
                    fn(self.ctx)
                except Exception as e:  # noqa: BLE001
                    self.ctx.diag(f"{name}.on_settings_changed: {e}")

    def has(self, channel: str) -> bool:
        return channel in self.handlers

    def call(self, channel: str, payload: Any = None) -> Any:
        fn = self.handlers.get(channel)
        if fn is None:
            raise KeyError(f"Неизвестный канал: {channel}")
        result = fn(payload)
        ach = self.modules.get("achievements")
        if ach is not None:
            try:
                ach.observe(self.ctx, channel, payload, result)
            except Exception as e:  # noqa: BLE001 — достижения не должны ломать вызов
                self.ctx.diag(f"achievements.observe({channel}): {e}")
        return result

    def shutdown(self) -> None:
        for name, mod in reversed(list(self.modules.items())):
            fn = getattr(mod, "shutdown", None)
            if callable(fn):
                try:
                    fn(self.ctx)
                except Exception as e:  # noqa: BLE001
                    self.ctx.diag(f"{name}.shutdown: {e}")
