"""Перевод интерфейса. Русский текст — ключ. Для английского берём словарь en.json (из Electron-версии)
плюс то, что страницы регистрируют сами через i18n.register({...}). Нет перевода — остаётся русский."""
from __future__ import annotations

import json
import os
import re

_EN: dict[str, str] = {}
_EXTRA: dict[str, str] = {}
try:
    with open(os.path.join(os.path.dirname(__file__), "en.json"), "r", encoding="utf-8") as _f:
        _EN = json.load(_f)
except Exception:  # noqa: BLE001
    _EN = {}


def register(table: dict[str, str]) -> None:
    """Страницы добавляют свои английские строки: register({'Играть': 'Play', ...})."""
    _EXTRA.update(table)


def translate(text: str, lang: str) -> str:
    if lang != "en" or not text:
        return text
    hit = _EXTRA.get(text) or _EN.get(text)
    if hit is not None:
        return hit
    m = re.match(r"^(\s*)(.*?)(\s*)$", text, re.S)
    if m and m.group(2) != text:
        hit = _EXTRA.get(m.group(2)) or _EN.get(m.group(2))
        if hit is not None:
            return m.group(1) + hit + m.group(3)
    if " · " in text:
        parts = text.split(" · ")
        out = [translate(p, lang) for p in parts]
        if out != parts:
            return " · ".join(out)
    return text
