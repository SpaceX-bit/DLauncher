"""Discord Rich Presence без внешних библиотек (порт lib/discord.js).

Говорим с клиентом Discord через локальный IPC: именованный канал на Windows, unix-сокет на Linux/macOS.
Нужен Application ID с discord.com/developers/applications.
"""
from __future__ import annotations

import json
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
ID_RE = re.compile(r"^\d{17,20}$")
NAMES = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt"}

TEXT = {
    "ru": {"idleDetails": "В лаунчере", "idleState": "Выбирает, во что поиграть",
           "launching": "Запускает Minecraft {v}", "playing": "Играет в Minecraft {v}"},
    "en": {"idleDetails": "In the launcher", "idleState": "Choosing what to play",
           "launching": "Launching Minecraft {v}", "playing": "Playing Minecraft {v}"},
}


def pipe_paths(env=None, platform=None) -> list[str]:
    """Пути, где Discord может держать канал: discord-ipc-0 … discord-ipc-9."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    out: list[str] = []
    for i in range(10):
        if platform == "win32":
            out.append(f"\\\\?\\pipe\\discord-ipc-{i}")
            continue
        dirs = [env.get("XDG_RUNTIME_DIR"), env.get("TMPDIR"), env.get("TMP"), env.get("TEMP"), "/tmp"]
        seen = []
        for d in dirs:
            if d and d not in seen:
                seen.append(d)
        for d in seen:
            out.append(os.path.join(d, f"discord-ipc-{i}"))
            out.append(os.path.join(d, "snap.discord", f"discord-ipc-{i}"))
            out.append(os.path.join(d, "app", "com.discordapp.Discord", f"discord-ipc-{i}"))
    return out


def encode(op: int, data) -> bytes:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return struct.pack("<ii", op, len(body)) + body


def _clip(s) -> str:
    return str(s or "")[:120]


class _SockConn:
    def __init__(self, path: str):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(path)
        s.settimeout(None)
        self.s = s

    def send(self, data: bytes) -> None:
        self.s.sendall(data)

    def recv(self, n: int) -> bytes:
        return self.s.recv(n)

    def close(self) -> None:
        try:
            self.s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.s.close()
        except OSError:
            pass


class _PipeConn:
    """Именованный канал Windows как файл."""

    def __init__(self, path: str):
        self.f = open(path, "r+b", buffering=0)

    def send(self, data: bytes) -> None:
        self.f.write(data)

    def recv(self, n: int) -> bytes:
        return self.f.read(n) or b""

    def close(self) -> None:
        threading.Thread(target=self._close, daemon=True).start()

    def _close(self) -> None:
        try:
            self.f.close()
        except Exception:  # noqa: BLE001
            pass


def _open(path: str, platform: str):
    if platform == "win32":
        return _PipeConn(path)
    return _SockConn(path)


class Presence:
    def __init__(self, get_settings, on_status=None, env=None, platform=None, retry_s: float = 15.0):
        self.get_settings = get_settings
        self.on_status = on_status
        self.env = env
        self.platform = platform or sys.platform
        self.retry_s = retry_s
        self.sock = None
        self.ready = False
        self.state = "off"   # off | no-id | connecting | connected | bad-id
        self.user = ""
        self.gen = 0
        self.timer: threading.Timer | None = None
        self.active_id = ""
        self.started_at = int(time.time())
        self.mode = {"kind": "idle", "profile": None, "since": self.started_at}
        self.lock = threading.RLock()

    # ---------- состояние ----------
    def status(self) -> dict:
        return {"state": self.state, "user": self.user}

    def _set_state(self, s: str, u: str = "") -> None:
        if self.state == s and self.user == u:
            return
        self.state, self.user = s, u
        if self.on_status:
            try:
                self.on_status(self.status())
            except Exception:  # noqa: BLE001
                pass

    def lang(self) -> str:
        return "en" if self.get_settings().get("lang") == "en" else "ru"

    def activity(self) -> dict:
        tx = TEXT[self.lang()]
        base = {"assets": {"large_image": "logo", "large_text": "DLauncher"}}
        p = self.mode["profile"]
        if self.mode["kind"] == "idle" or not p:
            return {**base, "details": tx["idleDetails"], "state": tx["idleState"],
                    "timestamps": {"start": self.started_at}}
        loader = NAMES.get(p.get("loader"), "Vanilla")
        key = "playing" if self.mode["kind"] == "playing" else "launching"
        act = {**base, "details": _clip(tx[key].format(v=p.get("version", ""))),
               "state": _clip(f"{loader} · {p.get('name', '')}")}
        if self.mode["kind"] == "playing":
            act["timestamps"] = {"start": self.mode["since"]}
        return act

    def _send_activity(self) -> None:
        with self.lock:
            sock, ready = self.sock, self.ready
        if not ready or sock is None:
            return
        try:
            sock.send(encode(OP_FRAME, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": self.activity()},
                                        "nonce": str(uuid.uuid4())}))
        except Exception:  # noqa: BLE001
            pass

    def _clear_timer(self) -> None:
        if self.timer:
            self.timer.cancel()
        self.timer = None

    def _stop(self) -> None:
        with self.lock:
            self.gen += 1
            self._clear_timer()
            self.ready = False
            sock, self.sock = self.sock, None
            self.active_id = ""
        if sock:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass

    def _retry(self, my_gen: int) -> None:
        with self.lock:
            if my_gen != self.gen:
                return
            self._set_state("connecting")
            self._clear_timer()
            t = threading.Timer(self.retry_s, lambda: self._connect(self.active_id))
            t.daemon = True
            self.timer = t
            t.start()

    def _fatal_bad_id(self, my_gen: int) -> None:
        if my_gen != self.gen:
            return
        self._stop()
        self._set_state("bad-id")

    # ---------- соединение ----------
    def _connect(self, cid: str) -> None:
        with self.lock:
            self.gen += 1
            my_gen = self.gen
            self._clear_timer()
            self.active_id = cid
            self._set_state("connecting")
        threading.Thread(target=self._run, args=(my_gen, cid), daemon=True).start()

    def _run(self, my_gen: int, cid: str) -> None:
        conn = None
        for path in pipe_paths(self.env, self.platform):
            if my_gen != self.gen:
                return
            try:
                conn = _open(path, self.platform)
                break
            except Exception:  # noqa: BLE001
                continue
        if conn is None:
            self._retry(my_gen)
            return
        with self.lock:
            if my_gen != self.gen:
                conn.close()
                return
            self.sock = conn
        try:
            conn.send(encode(OP_HANDSHAKE, {"v": 1, "client_id": cid}))
            buf = b""
            while True:
                d = conn.recv(4096)
                if not d:
                    break
                if my_gen != self.gen:
                    return
                buf += d
                while len(buf) >= 8:
                    op, ln = struct.unpack("<ii", buf[:8])
                    if ln < 0 or ln > 1024 * 1024:
                        raise ValueError("bad frame")
                    if len(buf) < 8 + ln:
                        break
                    try:
                        msg = json.loads(buf[8:8 + ln].decode("utf-8"))
                    except Exception:  # noqa: BLE001
                        msg = {}
                    buf = buf[8 + ln:]
                    self._handle(my_gen, conn, op, msg if isinstance(msg, dict) else {})
        except Exception:  # noqa: BLE001
            pass
        if my_gen != self.gen:
            return
        with self.lock:
            self.ready = False
            self.sock = None
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        self._retry(my_gen)

    def _handle(self, my_gen: int, conn, op: int, msg: dict) -> None:
        if op == OP_PING:
            conn.send(encode(OP_PONG, msg))
            return
        if op == OP_CLOSE:
            if msg.get("code") == 4000:
                self._fatal_bad_id(my_gen)
            return
        if op != OP_FRAME:
            return
        if msg.get("evt") == "READY":
            self.ready = True
            u = ((msg.get("data") or {}).get("user") or {}).get("username")
            self._set_state("connected", _clip(u))
            self._send_activity()
        elif msg.get("evt") == "ERROR" and (msg.get("data") or {}).get("code") == 4000:
            self._fatal_bad_id(my_gen)

    # ---------- публичное ----------
    def configure(self) -> None:
        """Вызывать после любого изменения настроек."""
        s = self.get_settings()
        cid = str(s.get("discordClientId") or "").strip()
        if not s.get("discordRpc"):
            self._stop()
            self._set_state("off")
            return
        if not ID_RE.match(cid):
            self._stop()
            self._set_state("no-id")
            return
        if cid == self.active_id and self.state in ("connecting", "connected"):
            self._send_activity()  # язык мог измениться
            return
        self._stop()
        self._connect(cid)

    def set_idle(self) -> None:
        self.mode = {"kind": "idle", "profile": None, "since": self.mode["since"]}
        self._send_activity()

    def set_launching(self, profile) -> None:
        self.mode = {"kind": "launching", "profile": profile, "since": int(time.time())}
        self._send_activity()

    def set_playing(self, profile) -> None:
        self.mode = {"kind": "playing", "profile": profile, "since": int(time.time())}
        self._send_activity()

    def stop(self) -> None:
        self._stop()
        self._set_state("off")

    # имена как в JS на случай прямого порта вызовов
    setIdle, setLaunching, setPlaying = set_idle, set_launching, set_playing


def setup(ctx) -> None:
    ctx.presence = Presence(lambda: ctx.settings, lambda s: ctx.send("discord:status", s))
    ctx.presence.configure()


def on_settings_changed(ctx) -> None:
    ctx.presence.configure()


def shutdown(ctx) -> None:
    p = getattr(ctx, "presence", None)
    if p:
        p.stop()


def handlers(ctx):
    return {"discord:status": lambda _=None: ctx.presence.status()}
