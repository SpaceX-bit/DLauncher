"""Минимальный читатель NBT (servers.dat, level.dat). Байт-в-байт порт readNbt из lib/servers.js."""
from __future__ import annotations

import gzip
import struct


def read_nbt(buf: bytes):
    pos = 0

    def need(n):
        if pos + n > len(buf):
            raise ValueError("обрыв файла")

    def rstr():
        nonlocal pos
        need(2)
        (ln,) = struct.unpack_from(">H", buf, pos)
        pos += 2
        need(ln)
        s = buf[pos:pos + ln].decode("utf-8", "replace")
        pos += ln
        return s

    def payload(t, depth):
        nonlocal pos
        if depth > 32:
            raise ValueError("слишком глубокая вложенность")
        if t == 1:
            need(1); v = struct.unpack_from(">b", buf, pos)[0]; pos += 1; return v
        if t == 2:
            need(2); v = struct.unpack_from(">h", buf, pos)[0]; pos += 2; return v
        if t == 3:
            need(4); v = struct.unpack_from(">i", buf, pos)[0]; pos += 4; return v
        if t == 4:
            need(8); v = struct.unpack_from(">q", buf, pos)[0]; pos += 8; return v
        if t == 5:
            need(4); v = struct.unpack_from(">f", buf, pos)[0]; pos += 4; return v
        if t == 6:
            need(8); v = struct.unpack_from(">d", buf, pos)[0]; pos += 8; return v
        if t == 7:
            need(4); n = struct.unpack_from(">i", buf, pos)[0]; pos += 4; need(n); pos += n; return None
        if t == 8:
            return rstr()
        if t == 9:
            need(5)
            et = struct.unpack_from(">b", buf, pos)[0]
            n = struct.unpack_from(">i", buf, pos + 1)[0]
            pos += 5
            if n < 0 or n > 100000:
                raise ValueError("плохой список")
            return [payload(et, depth + 1) for _ in range(n)]
        if t == 10:
            o = {}
            while True:
                need(1)
                tt = struct.unpack_from(">b", buf, pos)[0]
                pos += 1
                if tt == 0:
                    break
                k = rstr()
                o[k] = payload(tt, depth + 1)
            return o
        if t == 11:
            need(4); n = struct.unpack_from(">i", buf, pos)[0]; pos += 4; need(n * 4); pos += n * 4; return None
        if t == 12:
            need(4); n = struct.unpack_from(">i", buf, pos)[0]; pos += 4; need(n * 8); pos += n * 8; return None
        raise ValueError("неизвестный тип NBT")

    need(1)
    if struct.unpack_from(">b", buf, pos)[0] != 10:
        raise ValueError("не NBT-файл")
    pos += 1
    rstr()
    return payload(10, 0)


def read_nbt_file(path: str):
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return read_nbt(data)
