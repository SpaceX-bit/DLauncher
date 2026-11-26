"""Список серверов профиля: хранение, пинг (Server List Ping), импорт из servers.dat. Порт lib/servers.js."""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import struct
import time

from .nbt import read_nbt_file

MAX_SERVERS = 30
HOST_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$", re.I)


def check_server(host, port):
    """{'host','port'} или ValueError."""
    host = str(host or "").strip().lower()
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    if not HOST_RE.match(host) or not 1 <= port <= 65535:
        raise ValueError("Неверный адрес сервера")
    return {"host": host, "port": port}


def parse_address(text):
    """«host» или «host:port» -> {'host','port'} либо None."""
    m = re.match(r"^([^:\s]+)(?::(\d{1,5}))?$", str(text or "").strip())
    if not m:
        return None
    try:
        return check_server(m.group(1), int(m.group(2)) if m.group(2) else 25565)
    except ValueError:
        return None


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(sock) -> int:
    v = 0
    for i in range(5):
        b = sock.recv(1)
        if not b:
            raise ConnectionError("closed")
        v |= (b[0] & 0x7F) << (7 * i)
        if not b[0] & 0x80:
            return v
    raise ValueError("bad varint")


def _packet(pid: int, data: bytes) -> bytes:
    body = _varint(pid) + data
    return _varint(len(body)) + body


def _mcstr(s: str) -> bytes:
    b = s.encode("utf-8")
    return _varint(len(b)) + b


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def _flatten(c) -> str:
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(_flatten(x) for x in c)
    return str(c.get("text", "")) + (_flatten(c["extra"]) if c.get("extra") else "")


def _resolve_target(host: str, port: int):
    return host, port  # SRV-записи без внешних библиотек не получить; используем адрес как есть


def ping_server(host: str, port: int, timeout: float = 4.0) -> dict:
    host, port = _resolve_target(host, port)
    try:
        t0 = time.time()
        sock = socket.create_connection((host, port), timeout=timeout)
    except socket.gaierror:
        return {"online": False, "error": "адрес не найден"}
    except OSError:
        return {"online": False, "error": "не отвечает"}
    try:
        sock.settimeout(timeout)
        hs = _varint(767) + _mcstr(host) + struct.pack(">H", port) + _varint(1)
        sent = time.time()
        sock.sendall(_packet(0, hs) + _packet(0, b""))
        ln = _read_varint(sock)
        if ln > 1024 * 1024:
            raise ValueError("слишком большой ответ")
        body = _recv_exact(sock, ln)
        # id (varint) + строка (varint длина + json)
        i = 0
        pid, k = 0, 0
        while True:
            b = body[i]; i += 1
            pid |= (b & 0x7F) << (7 * k); k += 1
            if not b & 0x80:
                break
        if pid != 0:
            raise ValueError("странный ответ")
        sl, k = 0, 0
        while True:
            b = body[i]; i += 1
            sl |= (b & 0x7F) << (7 * k); k += 1
            if not b & 0x80:
                break
        status = json.loads(body[i:i + sl].decode("utf-8"))
        latency = max(1, int((time.time() - sent) * 1000))
        try:
            sock.sendall(_packet(1, struct.pack(">q", int(time.time() * 1000))))
            t1 = time.time()
            l2 = _read_varint(sock)
            _recv_exact(sock, l2)
            latency = max(1, int((time.time() - t1) * 1000))
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        return {"online": False, "error": "странный ответ сервера"}
    finally:
        try:
            sock.close()
        except OSError:
            pass
    players = status.get("players") or {}
    fav = status.get("favicon")
    return {
        "online": True,
        "latency": latency,
        "players": {"online": int(players.get("online") or 0), "max": int(players.get("max") or 0)},
        "version": str((status.get("version") or {}).get("name") or "")[:40],
        "motd": re.sub(r"\s+", " ", re.sub(r"§.", "", _flatten(status.get("description")))).strip()[:120],
        "icon": fav if isinstance(fav, str) and fav.startswith("data:image/png;base64,") and len(fav) < 40000 else None,
    }


def pick_server(profile: dict) -> dict | None:
    """Какой сервер показывать на карточке: избранный, иначе последний, к которому заходили."""
    servers = [x for x in (profile.get("servers") or []) if isinstance(x, dict) and x.get("host")]
    for x in servers:
        if x.get("favorite"):
            return x
    last = profile.get("lastServer")
    if last:
        for x in servers:
            if x.get("id") == last or x.get("host") == last:
                return x
    return None


def read_servers_dat(path: str) -> list[dict]:
    root = read_nbt_file(path)
    out = []
    for s in root.get("servers") or []:
        a = parse_address(s.get("ip")) if isinstance(s, dict) and isinstance(s.get("ip"), str) else None
        if a:
            out.append({"name": str(s.get("name") or a["host"])[:40], **a})
    return out


def handlers(ctx):
    def lst(p):
        if not isinstance(p.get("servers"), list):
            p["servers"] = []
        return p["servers"]

    def same(s, a):
        return s.get("host") == a["host"] and s.get("port") == a["port"]

    def s_list(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        return {"ok": True, "servers": lst(p), "last": p.get("lastServer") or None}

    def s_add(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        a = parse_address(arg.get("address"))
        if not a:
            return {"ok": False, "error": "Неверный адрес. Пример: play.example.net или play.example.net:25566"}
        servers = lst(p)
        if len(servers) >= MAX_SERVERS:
            return {"ok": False, "error": f"Не больше {MAX_SERVERS} серверов в профиле"}
        if any(same(s, a) for s in servers):
            return {"ok": False, "error": "Такой сервер уже есть в списке"}
        server = {"id": secrets.token_hex(4), "name": str(arg.get("name") or "").strip()[:40] or a["host"], **a, "favorite": False}
        servers.append(server)
        ctx.save_settings()
        return {"ok": True, "server": server}

    def s_edit(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        s = next((x for x in lst(p) if x.get("id") == arg.get("id")), None) if p else None
        if not s:
            return {"ok": False, "error": "Сервер не найден"}
        if "address" in arg:
            a = parse_address(arg["address"])
            if not a:
                return {"ok": False, "error": "Неверный адрес"}
            if any(x is not s and same(x, a) for x in lst(p)):
                return {"ok": False, "error": "Такой сервер уже есть в списке"}
            s.update(a)
        if "name" in arg:
            s["name"] = str(arg["name"]).strip()[:40] or s["host"]
        if "favorite" in arg:
            s["favorite"] = bool(arg["favorite"])
        ctx.save_settings()
        return {"ok": True, "server": s}

    def s_remove(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        p["servers"] = [x for x in lst(p) if x.get("id") != arg.get("id")]
        ctx.save_settings()
        return {"ok": True}

    def s_import(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        f = os.path.join(ctx.instance_dir(p["id"]), "servers.dat")
        if not os.path.exists(f):
            return {"ok": False, "error": "Файл servers.dat не найден: сначала добавь сервер в самой игре и выйди из неё."}
        try:
            found = read_servers_dat(f)
            servers = lst(p)
            added = 0
            for x in found:
                if len(servers) >= MAX_SERVERS:
                    break
                if any(same(s, x) for s in servers):
                    continue
                servers.append({"id": secrets.token_hex(4), "name": x["name"], "host": x["host"], "port": x["port"], "favorite": False})
                added += 1
            ctx.save_settings()
            return {"ok": True, "found": len(found), "added": added}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "Не удалось прочитать servers.dat: " + str(e)}

    def s_ping(arg=None):
        arg = arg or {}
        try:
            a = check_server(arg.get("host"), arg.get("port"))
        except ValueError:
            return {"online": False, "error": "неверный адрес"}
        return ping_server(a["host"], a["port"])

    def s_status(arg=None):
        """Онлайн и пинг сервера для карточки сборки (избранный или последний)."""
        p = ctx.find_profile((arg or {}).get("profileId"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        srv = pick_server(p)
        if not srv:
            return {"ok": True, "server": None}
        r = ping_server(srv["host"], int(srv.get("port") or 25565), timeout=3.0)
        return {"ok": True, "server": {"name": srv.get("name") or srv["host"], "host": srv["host"]},
                "online": bool(r.get("online")), "latency": r.get("latency"), "players": r.get("players")}

    return {"servers:status": s_status, "servers:list": s_list, "servers:add": s_add, "servers:edit": s_edit, "servers:remove": s_remove,
            "servers:import": s_import, "servers:ping": s_ping}
