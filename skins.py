"""Вкладка «Скины»: скин и плащи аккаунта Microsoft, предпросмотр спереди/сзади (рисуем из текстуры скина)."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import i18n, theme
from ..dialogs.shared import Segment
from ..widgets import Card, VScroll, button, label

i18n.register({
    "Скины": "Skins",
    "Скин аккаунта": "Account skin",
    "Выбрать файл скина": "Choose a skin file",
    "Применить": "Apply",
    "Отмена": "Cancel",
    "Повернуть": "Turn around",
    "Вернуть стандартный": "Reset to default",
    "Классический": "Classic",
    "Тонкие руки": "Slim arms",
    "Плащи": "Capes",
    "Надеть": "Wear",
    "Снять плащ": "Take off the cape",
    "Надет": "Worn",
    "Аккаунт: {n}": "Account: {n}",
    "Скин выбран: {n}. Нажми «Применить».": "Skin chosen: {n}. Press “Apply”.",
    "Старый формат скина (64×32) — он отобразится в игре без второго слоя.": "Old skin format (64×32) — it will show without the second layer.",
    "Скин применён": "Skin applied",
    "Загрузка...": "Loading...",
    "Нет плащей": "No capes",
    "Вернуть стандартный скин?": "Reset to the default skin?",
})


def skin_parts(legacy: bool, slim: bool, back: bool) -> list[dict]:
    """Какие куски текстуры куда рисовать (в «пикселях персонажа»: 16×32).
    Возвращает [{'src': (x,y,w,h), 'dst': (x,y,w,h), 'flip': bool, 'over': bool}] в порядке рисования."""
    aw = 3 if slim else 4
    parts: list[dict] = []

    def add(src, dst, flip=False, over=False):
        parts.append({"src": src, "dst": dst, "flip": flip, "over": over})

    # голова и тело (одинаково у старого и нового формата)
    add((24, 8, 8, 8) if back else (8, 8, 8, 8), (4, 0, 8, 8))
    add((32, 20, 8, 12) if back else (20, 20, 8, 12), (4, 8, 8, 12))
    # правая рука (персонажа): спереди слева, сзади справа
    r_front = (44, 20, aw, 12)
    r_back = ((51 if slim else 52), 20, aw, 12)
    r_src = r_back if back else r_front
    r_dst = (12, 8, aw, 12) if back else (4 - aw, 8, aw, 12)
    # левая рука: у нового формата своя текстура, у старого — отражённая правая
    if legacy:
        l_src, l_flip = r_src, True
    else:
        l_src = ((43 if slim else 44), 52, aw, 12) if back else (36, 52, aw, 12)
        l_flip = False
    l_dst = (4 - aw, 8, aw, 12) if back else (12, 8, aw, 12)
    add(r_src, r_dst)
    add(l_src, l_dst, l_flip)
    # ноги
    rl_src = (12, 20, 4, 12) if back else (4, 20, 4, 12)
    ll_src, ll_flip = ((rl_src, True) if legacy else (((28, 52, 4, 12) if back else (20, 52, 4, 12)), False))
    add(rl_src, (8, 20, 4, 12) if back else (4, 20, 4, 12))
    add(ll_src, (4, 20, 4, 12) if back else (8, 20, 4, 12), ll_flip)
    if not legacy:  # второй слой
        add((56, 8, 8, 8) if back else (40, 8, 8, 8), (4, 0, 8, 8), over=True)
        add((32, 36, 8, 12) if back else (20, 36, 8, 12), (4, 8, 8, 12), over=True)
        add(((51 if slim else 52), 36, aw, 12) if back else (44, 36, aw, 12), r_dst, over=True)
        add(((59 if slim else 60), 52, aw, 12) if back else (52, 52, aw, 12), l_dst, over=True)
        add((12, 36, 4, 12) if back else (4, 36, 4, 12), (8, 20, 4, 12) if back else (4, 20, 4, 12), over=True)
        add((12, 52, 4, 12) if back else (4, 52, 4, 12), (4, 20, 4, 12) if back else (8, 20, 4, 12), over=True)
    return parts


def cape_front_rect() -> tuple[int, int, int, int]:
    return (1, 1, 10, 16)


class SkinPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(200, 340)
        self.image: QImage | None = None
        self.slim = False
        self.back = False

    def set_skin(self, path: str | None, slim: bool) -> None:
        self.image = QImage(path) if path else None
        if self.image is not None and self.image.isNull():
            self.image = None
        self.slim = slim
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        if self.image is None:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "?")
            p.end()
            return
        legacy = self.image.height() < 64
        scale = max(1, min(self.width() // 16, self.height() // 32))
        ox = (self.width() - 16 * scale) // 2
        oy = (self.height() - 32 * scale) // 2
        for part in skin_parts(legacy, self.slim, self.back):
            sx, sy, sw, sh = part["src"]
            dx, dy, dw, dh = part["dst"]
            piece = self.image.copy(QRect(sx, sy, sw, sh))
            if part["flip"]:
                piece = piece.mirrored(True, False)
            p.drawImage(QRect(ox + dx * scale, oy + dy * scale, dw * scale, dh * scale), piece)
        p.end()


class SkinsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.state: dict | None = None
        self.pending = False
        self.variant = "classic"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(label(app, "Скины", "h2"))
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        outer.addLayout(root, 1)

        left = Card()
        left.setMinimumWidth(300)
        left.lay.addWidget(label(app, "Скин аккаунта", "h3"))
        self.acc = label(app, None, "muted", wrap=True)
        left.lay.addWidget(self.acc)
        self.preview = SkinPreview()
        left.lay.addWidget(self.preview, 1)
        left.lay.addWidget(button(app, "Повернуть", "small", self._turn))
        self.seg = Segment(app, [("classic", "Классический"), ("slim", "Тонкие руки")], "classic", self._variant)
        left.lay.addWidget(self.seg)
        self.msg = label(app, None, "muted", wrap=True)
        left.lay.addWidget(self.msg)
        row = QHBoxLayout()
        self.btn_choose = button(app, "Выбрать файл скина", "ghost", self._choose)
        self.btn_apply = button(app, "Применить", "primary", self._apply)
        self.btn_cancel = button(app, "Отмена", "ghost", self._discard)
        row.addWidget(self.btn_choose)
        row.addWidget(self.btn_apply)
        row.addWidget(self.btn_cancel)
        left.lay.addLayout(row)
        self.btn_reset = button(app, "Вернуть стандартный", "danger", self._reset)
        left.lay.addWidget(self.btn_reset)
        root.addWidget(left, 2)

        right = VScroll()
        root.addWidget(right, 3)
        self.capes_card = Card()
        self.capes_card.lay.addWidget(label(app, "Плащи", "h3"))
        self.capes_box = QVBoxLayout()
        self.capes_card.lay.addLayout(self.capes_box)
        right.lay.addWidget(self.capes_card)
        right.lay.addStretch(1)
        self._sync_buttons()

    def on_show(self) -> None:
        self.load()

    def load(self) -> None:
        self.msg.setText(self.app.t("Загрузка..."))
        self.app.call("skins:get", None, self._got, lambda m: self.msg.setText(m))

    def _got(self, r) -> None:
        if not isinstance(r, dict):
            return
        if not r.get("ok"):
            self.state = None
            self.msg.setText(self.app.t(r.get("error") or "?"))
            self.acc.setText("")
            self.preview.set_skin(None, False)
            self._fill_capes([])
            self._sync_buttons()
            return
        self.state = r
        self.pending = False
        self.variant = r.get("variant") or "classic"
        self.seg.select(self.variant, notify=False)
        self.acc.setText(self.app.t("Аккаунт: {n}", n=r.get("name")))
        self.preview.set_skin(r.get("skin"), self.variant == "slim")
        self.msg.setText("")
        self._fill_capes(r.get("capes") or [])
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        ok = self.state is not None
        self.btn_choose.setEnabled(ok)
        self.btn_reset.setEnabled(ok and not self.pending)
        self.btn_apply.setVisible(self.pending)
        self.btn_cancel.setVisible(self.pending)

    def _fill_capes(self, capes: list) -> None:
        from ..widgets import clear_layout
        clear_layout(self.capes_box)
        if not capes:
            self.capes_box.addWidget(label(self.app, "Нет плащей", "muted"))
            return
        for c in capes:
            row = QHBoxLayout()
            thumb = QLabel()
            thumb.setFixedSize(40, 64)
            if c.get("image"):
                img = QImage(c["image"])
                if not img.isNull():
                    x, y, w, h = cape_front_rect()
                    thumb.setPixmap(QPixmap.fromImage(img.copy(QRect(x, y, w, h))).scaled(40, 64, Qt.KeepAspectRatio, Qt.FastTransformation))
            row.addWidget(thumb)
            nm = QLabel(str(c.get("name") or "Cape"))
            nm.setProperty("kind", "accent" if c.get("active") else "")
            row.addWidget(nm, 1)
            if c.get("active"):
                row.addWidget(label(self.app, "Надет", "ok"))
            else:
                row.addWidget(button(self.app, "Надеть", "small", lambda cid=c["id"]: self._cape(cid)))
            w = QWidget()
            w.setLayout(row)
            self.capes_box.addWidget(w)
        if any(c.get("active") for c in capes):
            self.capes_box.addWidget(button(self.app, "Снять плащ", "ghost", lambda: self._cape("")))

    # ----- действия
    def _turn(self) -> None:
        self.preview.back = not self.preview.back
        self.preview.update()

    def _variant(self, v: str) -> None:
        self.variant = v
        self.preview.slim = v == "slim"
        self.preview.update()

    def _choose(self) -> None:
        def ok(r):
            if (r or {}).get("canceled"):
                return
            if not (r or {}).get("ok"):
                return self.app.toast((r or {}).get("error") or "?", "err")
            self.pending = True
            self.preview.set_skin(r.get("image"), self.variant == "slim")
            self.msg.setText(self.app.t("Скин выбран: {n}. Нажми «Применить».", n=r.get("name")) +
                             ("\n" + self.app.t("Старый формат скина (64×32) — он отобразится в игре без второго слоя.") if r.get("legacy") else ""))
            self._sync_buttons()
        self.app.call("skins:choose", None, ok, lambda m: self.app.toast(m, "err"))

    def _apply(self) -> None:
        def ok(r):
            if (r or {}).get("ok"):
                self._got(r)
                self.app.toast("Скин применён", "ok")
            else:
                self.app.toast((r or {}).get("error") or "?", "err")
        self.app.call("skins:apply", {"variant": self.variant}, ok, lambda m: self.app.toast(m, "err"))

    def _discard(self) -> None:
        self.app.call("skins:discard", None, lambda r: self.load(), lambda m: None)

    def _reset(self) -> None:
        if self.app.confirm("Вернуть стандартный скин?", "Вернуть стандартный", danger=True):
            self.app.call("skins:reset", None, self._after, lambda m: self.app.toast(m, "err"))

    def _cape(self, cid: str) -> None:
        self.app.call("skins:cape", {"id": cid}, self._after, lambda m: self.app.toast(m, "err"))

    def _after(self, r) -> None:
        if (r or {}).get("ok"):
            self._got(r)
        else:
            self.app.toast((r or {}).get("error") or "?", "err")

    def retranslate(self) -> None:
        if self.state:
            self._got(self.state)

    def selftest(self) -> None:
        for legacy in (False, True):
            for slim in (False, True):
                for back in (False, True):
                    assert skin_parts(legacy, slim, back)
