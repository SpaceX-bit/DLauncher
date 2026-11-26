"""Консоль игры: последние строки вывода Minecraft и лаунчера, отдаём окну пачками.

Токены доступа вырезаются: консоль можно копировать и показывать другим. Порт lib/gamelog.js.
События: console:lines (список {'s': 'g'|'l', 't': текст}), console:reset.
"""
from __future__ import annotations

import re
import threading

MAX_LINES = 3000
MAX_LINE = 2000
FLUSH_MS = 120

_RX = [
    (re.compile(r"""(--(?:accessToken|session|xuid|clientId|userProperties)\s+)(?:"[^"]*"|'[^']*'|\S+)""", re.I), r"\1***"),
    (re.compile(r"""("?(?:access_?token|refresh_?token|client_?token|mcToken)"?\s*[:=]\s*)"[^"]*\"""", re.I), r'\1"***"'),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{10,}"), r"\1***"),
    (re.compile(r"(accessToken[=:]\s*)[A-Za-z0-9._~+/=-]{20,}", re.I), r"\1***"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "***"),
]


def redact(text) -> str:
    """Прячет секреты (токены) из текста лога."""
    out = str(text)
    for rx, rep in _RX:
        out = rx.sub(rep, out)
    return out


class GameLog:
    def __init__(self, send, max_lines: int = MAX_LINES, flush_ms: int = FLUSH_MS):
        self._send = send
        self._max = max_lines
        self._flush_s = flush_ms / 1000.0
        self._lines: list[dict] = []
        self._batch: list[dict] = []
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def flush(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = None
            out, self._batch = self._batch, []
        if out:
            self._send("console:lines", out)

    def _flush_timer(self) -> None:
        with self._lock:
            self._timer = None
        self.flush()

    def push(self, source: str, text) -> None:
        s = "l" if source == "launcher" else "g"
        with self._lock:
            for raw in re.split(r"\r?\n", redact(text)):
                if not raw.strip():
                    continue
                item = {"s": s, "t": raw[:MAX_LINE] + "…" if len(raw) > MAX_LINE else raw}
                self._lines.append(item)
                self._batch.append(item)
            if len(self._lines) > self._max:
                self._lines = self._lines[len(self._lines) - self._max:]
            if self._timer is None:
                self._timer = threading.Timer(self._flush_s, self._flush_timer)
                self._timer.daemon = True
                self._timer.start()

    def start(self, title: str) -> None:
        with self._lock:
            self._lines = []
            self._batch = []
        self._send("console:reset", None)
        self.push("launcher", f"=== {title} ===")

    def clear(self) -> None:
        with self._lock:
            self._lines = []
            self._batch = []
        self._send("console:reset", None)

    def text(self) -> str:
        with self._lock:
            return "\n".join(l["t"] for l in self._lines)

    def lines(self) -> list[dict]:
        with self._lock:
            return list(self._lines)


def _log(ctx) -> GameLog:
    g = getattr(ctx, "gamelog", None)
    if g is None:
        g = ctx.gamelog = GameLog(ctx.send)
    return g


def setup(ctx) -> None:
    _log(ctx)


def shutdown(ctx) -> None:
    g = getattr(ctx, "gamelog", None)
    if g is not None:
        g.flush()


def handlers(ctx):
    log = _log(ctx)

    def get(_=None):
        return {"lines": log.lines()}

    def clear(_=None):
        log.clear()
        return {"ok": True}

    def copy(_=None):
        ctx.ui.set_clipboard_text(log.text())
        return {"ok": True, "lines": len(log.lines())}

    return {"console:get": get, "console:clear": clear, "console:copy": copy}
