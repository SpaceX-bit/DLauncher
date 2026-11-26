"""Пиксельные значки достижений в стиле Minecraft: свои рисунки 16×16 в квадратной рамке-слоте.

Всё рисуется кодом (никаких чужих текстур). tile_cells() — чистая функция без Qt: {(x, y): '#rrggbb'}.
У сложных достижений золотая рамка (как «испытания» в игре), у остальных каменная.
"""
from __future__ import annotations

SIZE = 16
TILE = 22  # рамка 22×22: значок 16×16 лежит внутри с отступом 3
OUTLINE = "#17171c"
CHALLENGE = {"modder", "ten_hours", "night", "secret"}


class Canvas:
    def __init__(self):
        self.c: dict[tuple[int, int], str] = {}

    def px(self, x, y, col):
        if 0 <= x < SIZE and 0 <= y < SIZE:
            self.c[(x, y)] = col

    def rect(self, x0, y0, x1, y1, col):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.px(x, y, col)

    def disc(self, cx, cy, r, col):
        for y in range(SIZE):
            for x in range(SIZE):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + r * 0.6:
                    self.px(x, y, col)

    def erase_disc(self, cx, cy, r):
        for y in range(SIZE):
            for x in range(SIZE):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + r * 0.6:
                    self.c.pop((x, y), None)

    def line(self, x0, y0, x1, y1, col):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.px(x0, y0, col)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def art(self, rows, palette, ox=0, oy=0):
        """Рисунок из строк: символ → цвет из palette, '.' — пусто."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch in palette:
                    self.px(ox + i, oy + j, palette[ch])

    def outlined(self) -> dict[tuple[int, int], str]:
        out = dict(self.c)
        for (x, y) in self.c:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = (x + dx, y + dy)
                if p not in self.c and 0 <= p[0] < SIZE and 0 <= p[1] < SIZE:
                    out[p] = OUTLINE
        return out


def _cube(c):
    c.rect(3, 3, 12, 12, "#8a5a2b")
    c.rect(3, 3, 12, 5, "#5fb04a")
    for x in (4, 7, 10):
        c.px(x, 6, "#5fb04a")
    for xy in ((5, 8), (9, 9), (6, 11), (11, 7), (8, 12)):
        c.px(*xy, "#6b4420")
    c.rect(12, 6, 12, 12, "#6b4420")


def _play(c):
    for x in range(4, 13):
        half = round((12 - x) * 5 / 8)
        c.rect(x, 8 - half, x, 8 + half, "#3ddc97")
    c.line(4, 3, 12, 8, "#9af0c8")


def _puzzle(c):
    c.rect(3, 6, 11, 13, "#e0a030")
    c.rect(5, 3, 8, 6, "#e0a030")
    c.rect(11, 8, 13, 11, "#e0a030")
    c.rect(3, 8, 4, 11, "#e0a030")
    c.erase_disc(3, 9, 1)
    c.rect(3, 6, 11, 6, "#f2c260")
    c.rect(3, 13, 11, 13, "#b07a1a")
    c.px(6, 4, "#f2c260")


def _chest(c):
    c.rect(2, 6, 13, 13, "#9c6a2f")
    c.rect(2, 3, 13, 6, "#b57f3a")
    c.rect(2, 6, 13, 6, "#5b3b17")
    c.rect(7, 6, 8, 9, "#e8c84a")
    c.px(7, 8, "#a88a1a")
    c.rect(2, 13, 13, 13, "#6b4420")


def _package(c):
    c.rect(3, 4, 12, 13, "#c99a5b")
    c.rect(3, 4, 12, 5, "#a97b3f")
    c.rect(7, 4, 8, 13, "#efe0b0")
    c.rect(4, 9, 6, 11, "#e8d9a8")
    c.rect(9, 9, 11, 11, "#e8d9a8")


def _palette(c):
    c.disc(8, 8, 6, "#c9a06a")
    c.rect(5, 5, 6, 6, "#e04a4a")
    c.rect(9, 4, 10, 5, "#4a7de0")
    c.rect(11, 8, 12, 9, "#4ac06a")
    c.rect(4, 9, 5, 10, "#e8d04a")
    c.erase_disc(10, 11, 1)


def _sun(c):
    c.disc(8, 8, 3, "#ffd34a")
    for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        for k in (5, 6):
            c.px(8 + dx * k, 8 + dy * k, "#ffb02e")
    c.px(7, 7, "#fff3b0")


def _bolt(c):
    c.art(["......XXXX..", ".....XXXX...", "....XXXX....", "...XXXXXXX..", "....XXXXXX..",
           ".......XXX..", "......XXX...", ".....XX.....", "....XX......", "...X........"], {"X": "#f4d03f"}, 2, 3)
    c.px(7, 4, "#fff6b0")
    c.px(6, 5, "#fff6b0")


def _tray(c):
    c.rect(3, 11, 12, 13, "#9aa5b1")
    c.rect(3, 9, 3, 13, "#9aa5b1")
    c.rect(12, 9, 12, 13, "#9aa5b1")
    c.rect(4, 11, 11, 11, "#6b7682")


def _arrow(c, up: bool):
    _tray(c)
    ys = range(2, 11)
    head = [(0, 7, 8), (1, 6, 9), (2, 5, 10), (3, 4, 11)]
    for i, x0, x1 in head:
        y = 2 + i if up else 10 - i
        c.rect(x0, y, x1, y, "#f2f2f6")
    for y in (range(6, 11) if up else range(2, 7)):
        c.rect(7, y, 8, y, "#f2f2f6")
    del ys


def _export(c):
    _arrow(c, True)


def _import(c):
    _arrow(c, False)


def _shield(c):
    rows = ["XXXXXXXXXX", "XXXXXXXXXX", "XXXXXXXXXX", "XXXXXXXXXX", "XXXXXXXXXX", "XXXXXXXXXX",
            ".XXXXXXXX.", ".XXXXXXXX.", "..XXXXXX..", "...XXXX...", "....XX...."]
    c.art(rows, {"X": "#4a7de0"}, 3, 2)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "X" and i >= 5:
                c.px(3 + i, 2 + j, "#3a63c0")
    c.rect(7, 5, 8, 10, "#f2f2f6")
    c.rect(5, 7, 10, 8, "#f2f2f6")


def _server(c):
    for y0 in (3, 9):
        c.rect(3, y0, 12, y0 + 4, "#7b8794")
        c.rect(3, y0, 12, y0, "#a2adb9")
        c.rect(6, y0 + 2, 11, y0 + 2, "#3b434c")
        c.px(4, y0 + 2, "#3ddc97")


def _head(c):
    c.rect(4, 3, 11, 12, "#e0b48a")
    c.rect(4, 3, 11, 5, "#6b3fa0")
    c.rect(4, 6, 4, 7, "#6b3fa0")
    c.rect(11, 6, 11, 7, "#6b3fa0")
    c.px(6, 8, "#ffffff")
    c.px(9, 8, "#ffffff")
    c.px(7, 8, "#2a4aa0")
    c.px(10, 8, "#2a4aa0")
    c.rect(7, 11, 8, 11, "#a0623a")


def _check(c):
    c.disc(8, 8, 6, "#2fae6d")
    for x, y in ((5, 8), (6, 9), (7, 10), (8, 9), (9, 8), (10, 7), (11, 6)):
        c.px(x, y, "#ffffff")
        c.px(x, y - 1, "#ffffff")


def _magnifier(c):
    c.disc(6, 6, 4, "#cfd6e0")
    c.disc(6, 6, 3, "#6fb8e8")
    c.erase_disc(6, 6, 0)
    c.disc(6, 6, 2, "#6fb8e8")
    c.line(9, 9, 13, 13, "#8a5a2b")
    c.line(10, 9, 13, 12, "#8a5a2b")
    c.px(5, 5, "#e8f6ff")


def _refresh(c):
    c.disc(8, 8, 6, "#2f8fd8")
    c.art(["...XX...", "..XXXX..", ".XXXXXX.", "XXXXXXXX"], {"X": "#ffffff"}, 4, 3)
    c.rect(6, 7, 9, 12, "#ffffff")


def _picture(c):
    c.rect(2, 3, 13, 12, "#c99a5b")
    c.rect(3, 4, 12, 11, "#6fb8e8")
    c.px(10, 5, "#ffe066")
    for j, (x0, x1) in enumerate(((8, 8), (7, 9), (6, 10), (5, 11), (4, 12))):
        c.rect(x0, 7 + j, x1, 7 + j, "#4a8f3a")


def _book(c):
    c.rect(2, 4, 13, 12, "#3f6fd0")
    c.rect(3, 5, 7, 11, "#f4efe0")
    c.rect(8, 5, 12, 11, "#f4efe0")
    c.rect(7, 4, 8, 12, "#2a4fa0")
    for y in (6, 8, 10):
        c.rect(4, y, 6, y, "#b8b0a0")
        c.rect(9, y, 11, y, "#b8b0a0")


def _heart(c):
    c.art(["..XX..XX..", ".XXXXXXXX.", "XXXXXXXXXX", "XXXXXXXXXX", ".XXXXXXXX.", "..XXXXXX..", "...XXXX...", "....XX...."],
          {"X": "#e0405a"}, 3, 4)
    c.px(4, 6, "#ff9aa8")
    c.px(5, 5, "#ff9aa8")


def _hourglass(c):
    c.rect(4, 2, 11, 3, "#8a5a2b")
    c.rect(4, 12, 11, 13, "#8a5a2b")
    for j, (x0, x1) in enumerate(((5, 10), (5, 10), (6, 9), (7, 8), (7, 8), (6, 9), (5, 10), (5, 10))):
        c.rect(x0, 4 + j, x1, 4 + j, "#cfe8f4")
    c.rect(6, 9, 9, 9, "#e8c060")
    c.rect(5, 10, 10, 11, "#e8c060")
    c.px(8, 6, "#e8c060")


def _crown(c):
    c.rect(3, 9, 12, 12, "#e0b84a")
    for x in (3, 7, 8, 12):
        c.rect(x, 5 if x in (3, 12) else 4, x, 8, "#e0b84a")
    c.rect(4, 7, 6, 8, "#e0b84a")
    c.rect(9, 7, 11, 8, "#e0b84a")
    c.px(5, 10, "#e04a4a")
    c.px(8, 10, "#4a7de0")
    c.px(10, 10, "#4ac06a")
    c.rect(3, 12, 12, 12, "#b8902a")


def _moon(c):
    c.disc(8, 8, 6, "#e8e2a0")
    c.erase_disc(11, 6, 5)


def _star(c):
    c.art(["......XX......", "......XX......", ".....XXXX.....", "XXXXXXXXXXXXXX", ".XXXXXXXXXXXX.", "..XXXXXXXXXX..",
           "...XXXXXXXX...", "...XXXXXXXX...", "..XXXX..XXXX..", ".XXX......XXX."], {"X": "#f4d03f"}, 1, 3)
    c.px(6, 6, "#fff6b0")


def _stack(c):
    for y, col in ((10, "#6d4fa8"), (6, "#8b5cc2"), (2, "#b08ae0")):
        c.rect(3, y, 12, y + 3, col)
        c.rect(3, y, 12, y, "#d4b8f4")
        c.rect(3, y + 3, 12, y + 3, "#563d86")


def _clone(c):
    c.rect(2, 2, 9, 9, "#2f8fb5")
    c.rect(3, 3, 8, 8, "#5cc0e6")
    c.rect(6, 6, 13, 13, "#e8f4fa")
    c.rect(7, 7, 12, 12, "#a8dcf0")


def _undo(c):
    c.art(["..XXXXXX..", ".XX....XX.", "XX......XX", "XX......XX", "XX......XX", ".XX....XX.", "..XX..XX.."],
          {"X": "#e0b84a"}, 3, 5)
    c.art(["XXXXX", ".XXX.", "..X.."], {"X": "#e0b84a"}, 0, 4)
    c.rect(2, 6, 4, 6, "#e0b84a")


def _code(c):
    c.line(5, 4, 2, 8, "#3ddc97")
    c.line(2, 8, 5, 12, "#3ddc97")
    c.line(10, 4, 13, 8, "#3ddc97")
    c.line(13, 8, 10, 12, "#3ddc97")
    c.line(9, 3, 6, 13, "#f2f2f6")


def _drop(c):
    c.rect(4, 2, 11, 13, "#f4efe0")
    c.rect(4, 2, 11, 2, "#c8c0b0")
    c.rect(7, 5, 8, 8, "#c2557a")
    c.art(["XXXXXX", ".XXXX.", "..XX.."], {"X": "#c2557a"}, 5, 9)


def _swatch(c):
    c.disc(8, 8, 6, "#5b6ee1")
    for y in range(SIZE):
        for x in range(SIZE):
            if (x - 8) ** 2 + (y - 8) ** 2 <= 6 * 6 + 3.6:
                if x >= 8 and y < 8:
                    c.px(x, y, "#e04a4a")
                elif x >= 8 and y >= 8:
                    c.px(x, y, "#e8d04a")
                elif x < 8 and y >= 8:
                    c.px(x, y, "#4ac06a")


def _unknown(c):
    c.art(["..XXXX..", ".XX..XX.", ".XX..XX.", "....XX..", "...XX...", "...XX...", "........", "...XX...", "...XX..."],
          {"X": "#8a8a96"}, 4, 3)


ICONS = {
    "first_profile": _cube, "first_launch": _play, "first_mod": _puzzle, "modder": _chest, "pack": _package,
    "resourcepack": _palette, "shader": _sun, "optimize": _bolt, "export": _export, "import": _import,
    "backup": _shield, "server": _server, "skin": _head, "microsoft": _check, "compat": _magnifier,
    "fresh": _refresh, "background": _picture, "tour": _book, "launches_10": _heart, "hour": _hourglass,
    "ten_hours": _crown, "night": _moon, "secret": _star,
    "builds_5": _stack, "clone": _clone, "undo": _undo, "code": _code, "drop": _drop, "accent": _swatch,
}


def icon_cells(aid: str, known: bool = True) -> dict[tuple[int, int], str]:
    """Значок 16×16 с тёмной обводкой. known=False — знак вопроса (секретное, пока не получено)."""
    cv = Canvas()
    (ICONS.get(aid, _unknown) if known else _unknown)(cv)
    return cv.outlined()


def gray(col: str) -> str:
    r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
    v = int((0.3 * r + 0.59 * g + 0.11 * b) * 0.38)
    return f"#{v:02x}{v:02x}{v:02x}"


def tile_cells(aid: str, unlocked: bool, known: bool = True) -> dict[tuple[int, int], str]:
    """Значок в квадратной рамке-слоте 22×22. Получено — цветной, нет — тёмно-серый силуэт."""
    gold = aid in CHALLENGE
    if gold:
        edge, hi, lo, fill = "#8a6a14", "#f6dc7a", "#b8902a", "#5a4a22"
    else:
        edge, hi, lo, fill = "#17171c", "#c6c6c6", "#555555", "#6e6e6e"
    if not unlocked:
        edge, hi, lo, fill = "#17171c", "#555555", "#2a2a2a", "#303030"
    cells: dict[tuple[int, int], str] = {}
    for y in range(TILE):
        for x in range(TILE):
            if (x in (0, TILE - 1)) and (y in (0, TILE - 1)):
                continue  # срезанные углы
            if x in (0, TILE - 1) or y in (0, TILE - 1):
                col = edge
            elif x == 1 or y == 1:
                col = hi
            elif x == TILE - 2 or y == TILE - 2:
                col = lo
            else:
                col = fill
            cells[(x, y)] = col
    for (x, y), col in icon_cells(aid, known or unlocked).items():
        cells[(x + 3, y + 3)] = col if unlocked else gray(col)
    return cells
