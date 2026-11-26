"""Вкладка «Миры»: миры профиля, резервные копии и галерея скриншотов.

Порт features.js (МИРЫ / КОПИИ / СКРИНШОТЫ). Каналы ядра: worlds:list / backup / restore / remove-backup,
shots:list / open / copy / delete, folder:open; событие worlds:progress.
"""
from __future__ import annotations

import datetime
import urllib.parse
import urllib.request

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import i18n
from ..widgets import Card, FlowLayout, Modal, VScroll, button, clear_layout, label

NAMES = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge", "neoforge": "NeoForge", "quilt": "Quilt"}
THUMB_W, THUMB_H = 220, 124
PREVIEW_W, PREVIEW_H = 860, 480

i18n.register({
    "Миры": "Worlds",
    "Резервные копии": "Backups",
    "Скриншоты": "Screenshots",
    "Открыть папку": "Open folder",
    "Обновить": "Refresh",
    "Сначала создай профиль во вкладке «Профили».": "Create a profile on the Profiles tab first.",
    "В этом профиле пока нет миров. Они появятся после первой игры.": "This profile has no worlds yet. They appear after you play.",
    "Резервных копий пока нет. Их можно сделать вручную на вкладке «Миры» или включить автоматические копии в настройках.":
        "No backups yet. Make one by hand on the Worlds tab or enable automatic backups in settings.",
    "Скриншотов пока нет. В игре они делаются клавишей F2.": "No screenshots yet. In the game press F2 to take one.",
    "Сделать копию": "Make backup",
    "Восстановить": "Restore",
    "Удалить": "Delete",
    "Мир распакуется как новый — существующие миры не затрагиваются":
        "The world is unpacked as a new one — existing worlds are not touched",
    "Игра запущена: восстановление копий недоступно": "The game is running: restoring backups is unavailable",
    "Копия создана: {file}": "Backup created: {file}",
    "Мир восстановлен как «{folder}»": "World restored as “{folder}”",
    "Скриншотов: {n}": "Screenshots: {n}",
    "Игра: {d}": "Played: {d}",
    "Копий: {n}": "Backups: {n}",
    "Копий нет": "No backups",
    "Удалить копию мира «{name}»?": "Delete the backup of “{name}”?",
    "Удалить скриншот?": "Delete this screenshot?",
    "Скопировано ✓": "Copied ✓",
    "Ошибка": "Error",
    "Копировать": "Copy",
    "Открыть": "Open",
    "Закрыть": "Close",
    "Скриншот": "Screenshot",
})


# ---------- чистые функции (тестируются без Qt) ----------
def fmt_size(b, en: bool = False) -> str:
    b = float(b or 0)
    gb, mb, kb = ("GB", "MB", "KB") if en else ("ГБ", "МБ", "КБ")
    if b > 1073741824:
        return f"{b / 1073741824:.1f} {gb}"
    if b > 1048576:
        return f"{b / 1048576:.1f} {mb}"
    return f"{max(1, round(b / 1024))} {kb}"


def date_time(ms, en: bool = False) -> str:
    if not ms:
        return "—"
    try:
        d = datetime.datetime.fromtimestamp(float(ms) / 1000.0)
    except (OverflowError, OSError, ValueError):
        return "—"
    return d.strftime("%m/%d/%Y, %I:%M %p") if en else d.strftime("%d.%m.%Y, %H:%M")


def meta_line(parts) -> str:
    return " · ".join(str(p) for p in parts if p)


def profile_label(p: dict) -> str:
    return f"{p.get('name', '')} · {p.get('version', '')} · {NAMES.get(p.get('loader'), p.get('loader'))}"


def first_letter(name) -> str:
    s = str(name or "?").strip()
    return (s[:1] or "?").upper()


def shot_path(item: dict) -> str:
    """Путь к картинке: ядро отдаёт локальный путь (path/url); file:// тоже понимаем."""
    p = str(item.get("path") or item.get("url") or "")
    if p.startswith("file:"):
        p = urllib.request.url2pathname(urllib.parse.urlparse(p).path)
    return p


def fit_size(w: int, h: int, max_w: int, max_h: int) -> tuple[int, int]:
    """Вписать w×h в max_w×max_h с сохранением пропорций (без увеличения не нужно: миниатюры тоже растягиваем)."""
    if w <= 0 or h <= 0:
        return max_w, max_h
    k = min(max_w / w, max_h / h)
    return max(1, int(w * k)), max(1, int(h * k))


def wrap_index(i: int, n: int) -> int:
    return (i + n) % n if n else -1


class _ThumbLoader:
    """Подгружает миниатюры порциями, чтобы окно не зависало на сотнях скриншотов."""

    def __init__(self):
        self.queue: list[tuple[QPushButton, str]] = []
        self.timer = QTimer()
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._tick)

    def clear(self):
        self.queue.clear()
        self.timer.stop()

    def add(self, btn, path):
        self.queue.append((btn, path))
        if not self.timer.isActive():
            self.timer.start()

    def _tick(self):
        for _ in range(4):
            if not self.queue:
                self.timer.stop()
                return
            btn, path = self.queue.pop(0)
            try:
                r = QImageReader(path)
                r.setAutoTransform(True)
                sz = r.size()
                if sz.isValid():
                    w, h = fit_size(sz.width(), sz.height(), THUMB_W * 2, THUMB_H * 2)
                    r.setScaledSize(QSize(w, h))
                img = r.read()
                if not img.isNull():
                    pm = QPixmap.fromImage(img).scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatioByExpanding,
                                                       Qt.SmoothTransformation)
                    btn.setIcon(QIcon(pm))
                    btn.setIconSize(QSize(THUMB_W, THUMB_H))
            except RuntimeError:
                pass  # кнопка уже удалена


class ShotDialog(Modal):
    """Просмотр скриншота: ◀ ▶, открыть, копировать, удалить."""

    def __init__(self, app, items: list, index: int, profile_id, on_changed=None):
        super().__init__(app, "Скриншот", width=PREVIEW_W + 40)
        self.items = items
        self.idx = -1
        self.profile_id = profile_id
        self.on_changed = on_changed
        self.img = QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setMinimumSize(PREVIEW_W, PREVIEW_H)
        self.body.addWidget(self.img, 1)
        self.name = label(app, None, "muted", wrap=True)
        self.name.setAlignment(Qt.AlignCenter)
        self.body.addWidget(self.name)
        self.btn_prev = self.add_button("◀", "ghost", lambda: self.show_index(self.idx - 1))
        self.btn_next = self.add_button("▶", "ghost", lambda: self.show_index(self.idx + 1))
        self.btn_open = self.add_button("Открыть", "ghost", self._open)
        self.btn_copy = self.add_button("Копировать", "ghost", self._copy)
        self.btn_del = self.add_button("Удалить", "danger", self._delete)
        self.add_button("Закрыть", "primary", close=True)
        self.show_index(index)

    def _args(self) -> dict:
        it = self.items[self.idx] if 0 <= self.idx < len(self.items) else {}
        return {"profileId": self.profile_id, "file": it.get("file")}

    def show_index(self, i: int) -> None:
        if not self.items:
            self.accept()
            return
        self.idx = wrap_index(i, len(self.items))
        it = self.items[self.idx]
        en = self.app.lang == "en"
        pm = QPixmap(shot_path(it))
        if not pm.isNull():
            pm = pm.scaled(PREVIEW_W, PREVIEW_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img.setPixmap(pm)
        else:
            self.img.setText(it.get("file", ""))
        self.name.setText(f"{it.get('file', '')} · {fmt_size(it.get('size'), en)} · {date_time(it.get('time'), en)}")

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key_Left:
            self.show_index(self.idx - 1)
        elif e.key() == Qt.Key_Right:
            self.show_index(self.idx + 1)
        else:
            super().keyPressEvent(e)

    def _open(self):
        self.app.call("shots:open", self._args(), None, lambda m: self.app.toast(m, "err"))

    def _copy(self):
        def done(r):
            ok = bool(r and r.get("ok"))
            self.btn_copy.setText(self.app.t("Скопировано ✓" if ok else "Ошибка"))
            QTimer.singleShot(1500, lambda: self._reset_copy())

        self.app.call("shots:copy", self._args(), done, lambda m: self.app.toast(m, "err"))

    def _reset_copy(self):
        try:
            self.btn_copy.setText(self.app.t("Копировать"))
        except RuntimeError:
            pass

    def _delete(self):
        if not self.app.confirm("Удалить скриншот?", ok_ru="Удалить", danger=True):
            return
        at = self.idx

        def done(r):
            if not (r or {}).get("ok"):
                self.app.toast((r or {}).get("error") or "Ошибка", "err")
                return
            self.items.pop(at)
            if self.on_changed:
                self.on_changed()
            if self.items:
                self.show_index(min(at, len(self.items) - 1))
            else:
                self.accept()

        self.app.call("shots:delete", self._args(), done, lambda m: self.app.toast(m, "err"))


class WorldsPage(QWidget):
    TABS = ("worlds", "backups", "shots")

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.tab = "worlds"
        self.data: dict | None = None
        self.shot_items: list = []
        self._gen = 0
        self._thumbs = _ThumbLoader()
        self._seg: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(label(app, "Миры", "h2"))
        card = Card()
        root.addWidget(card, 1)

        top = QHBoxLayout()
        top.setSpacing(6)
        for key, ru in (("worlds", "Миры"), ("backups", "Резервные копии"), ("shots", "Скриншоты")):
            b = button(app, ru, "chip", lambda k=key: self.set_tab(k), checkable=True)
            self._seg[key] = b
            top.addWidget(b)
        top.addStretch(1)
        self.btn_folder = button(app, "Открыть папку", "ghost", self._open_folder)
        self.btn_refresh = button(app, "Обновить", "ghost", self.reload)
        top.addWidget(self.btn_folder)
        top.addWidget(self.btn_refresh)
        card.lay.addLayout(top)

        self.info = label(app, None, "muted", wrap=True)
        card.lay.addWidget(self.info)

        self.stack = QStackedWidget()
        card.lay.addWidget(self.stack, 1)
        self.list_scroll = VScroll(spacing=8)
        self.stack.addWidget(self.list_scroll)
        self.shots_scroll = VScroll()
        self.shots_host = QWidget()
        self.shots_flow = FlowLayout(self.shots_host, 10, 10)
        self.shots_scroll.lay.addWidget(self.shots_host)
        self.shots_msg = label(app, None, "muted", wrap=True)
        self.shots_scroll.lay.addWidget(self.shots_msg)
        self.shots_scroll.lay.addStretch(1)
        self.stack.addWidget(self.shots_scroll)

        self._sync_tabs()
        app.profiles_changed.connect(self._on_profiles)
        app.event.connect(self._on_event)

    # ---------- жизненный цикл ----------
    def on_show(self):
        self.reload()

    def retranslate(self):
        if self.isVisible() or self.data is not None:
            self.reload()

    def selftest(self):
        self.reload()
        ShotDialog(self.app, [], 0, None)  # без exec()

    def _on_profiles(self):
        if self.isVisible():
            self.reload()

    def _on_event(self, channel, payload):
        if channel == "worlds:progress" and self.isVisible():
            self.info.setText((payload or {}).get("text", ""))

    # ---------- вкладки ----------
    def _sync_tabs(self):
        for k, b in self._seg.items():
            b.setChecked(k == self.tab)

    def set_tab(self, tab: str):
        if tab not in self.TABS:
            return
        self.tab = tab
        self._sync_tabs()
        self.reload()

    def _open_folder(self):
        which = {"worlds": "saves", "backups": "backups", "shots": "screenshots"}[self.tab]
        p = self.app.current_profile()
        self.app.call("folder:open", {"which": which, "profileId": p and p["id"]}, None,
                      lambda m: self.app.toast(m, "err"))

    def _wr_info(self, text: str):
        self.info.setText(text or "")

    # ---------- загрузка ----------
    def reload(self):
        self._gen += 1
        gen = self._gen
        p = self.app.current_profile()
        if not p:
            self._wr_info("")
            self.stack.setCurrentIndex(0)
            self._message(self.app.t("Сначала создай профиль во вкладке «Профили»."))
            return
        self._wr_info(profile_label(p))
        if self.tab == "shots":
            self.stack.setCurrentIndex(1)
            self.app.call("shots:list", {"profileId": p["id"]},
                          lambda r: self._shots_loaded(gen, p, r), lambda m: self._shots_error(gen, m))
            return
        self.stack.setCurrentIndex(0)
        self.app.call("worlds:list", {"profileId": p["id"]},
                      lambda r: self._worlds_loaded(gen, p, r), lambda m: self._message(m, gen))

    def _message(self, text: str, gen: int | None = None):
        if gen is not None and gen != self._gen:
            return
        self.list_scroll.clear()
        self.list_scroll.lay.addWidget(label(self.app, None, "muted", wrap=True))
        lb = self.list_scroll.lay.itemAt(0).widget()
        lb.setText(text)
        self.list_scroll.lay.addStretch(1)

    def _worlds_loaded(self, gen, p, r):
        if gen != self._gen:
            return
        if not r or not r.get("ok"):
            self._message((r or {}).get("error") or "Ошибка", gen)
            return
        self.data = r
        if r.get("running"):
            self._wr_info(f"{profile_label(p)} · {self.app.t('Игра запущена: восстановление копий недоступно')}")
        if self.tab == "backups":
            self._render_backups(r)
        else:
            self._render_worlds(r)

    # ---------- строки ----------
    def _row(self, letter: str, title: str, meta: str, buttons: list) -> Card:
        row = Card("build", "h", margins=(12, 10, 12, 10), spacing=12)
        ph = QLabel(letter)
        ph.setProperty("kind", "ph")
        ph.setFixedSize(44, 44)
        ph.setAlignment(Qt.AlignCenter)
        row.lay.addWidget(ph)
        info = QVBoxLayout()
        info.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; font-size: 14px;")
        m = label(self.app, None, "muted", wrap=True)
        m.setText(meta)
        info.addWidget(t)
        info.addWidget(m)
        row.lay.addLayout(info, 1)
        for b in buttons:
            row.lay.addWidget(b)
        return row

    def _render_worlds(self, r):
        box = self.list_scroll
        box.clear()
        en = self.app.lang == "en"
        if not r.get("worlds"):
            box.lay.addWidget(label(self.app, "В этом профиле пока нет миров. Они появятся после первой игры.", "muted", wrap=True))
            box.lay.addStretch(1)
            return
        for w in r["worlds"]:
            b = button(self.app, "Сделать копию", "ghost")
            b.clicked.connect(lambda _=False, w=w, b=b: self._backup(w, b))
            meta = meta_line([
                f"Minecraft {w['version']}" if w.get("version") else "",
                fmt_size(w.get("size"), en),
                self.app.t("Игра: {d}", d=date_time(w.get("lastPlayed"), en)),
                self.app.t("Копий: {n}", n=w["backups"]) if w.get("backups") else self.app.t("Копий нет"),
            ])
            box.lay.addWidget(self._row(first_letter(w.get("name")), str(w.get("name") or w.get("folder")), meta, [b]))
        box.lay.addStretch(1)

    def _render_backups(self, r):
        box = self.list_scroll
        box.clear()
        en = self.app.lang == "en"
        if not r.get("backups"):
            box.lay.addWidget(label(self.app, "Резервных копий пока нет. Их можно сделать вручную на вкладке «Миры» или включить автоматические копии в настройках.", "muted", wrap=True))
            box.lay.addStretch(1)
            return
        running = bool(r.get("running"))
        for bk in r["backups"]:
            restore = button(self.app, "Восстановить", "ghost")
            restore.setEnabled(not running)
            self.app.bind(restore, "Мир распакуется как новый — существующие миры не затрагиваются", "tooltip")
            restore.clicked.connect(lambda _=False, bk=bk, b=restore: self._restore(bk, b))
            delete = button(self.app, "Удалить", "danger")
            delete.clicked.connect(lambda _=False, bk=bk: self._remove(bk))
            meta = meta_line([date_time(bk.get("time"), en), fmt_size(bk.get("size"), en)])
            box.lay.addWidget(self._row(first_letter(bk.get("world")), str(bk.get("world")), meta, [restore, delete]))
        box.lay.addStretch(1)

    # ---------- действия над мирами ----------
    def _pid(self):
        p = self.app.current_profile()
        return (self.data or {}).get("profile", {}).get("id") or (p and p["id"])

    def _backup(self, w, btn):
        btn.setEnabled(False)

        def done(res):
            self.reload()
            res = res or {}
            if res.get("ok"):
                self._wr_info(res.get("warning") or self.app.t("Копия создана: {file}", file=res.get("file", "")))
            else:
                self._wr_info(res.get("error") or "")

        def fail(m):
            btn.setEnabled(True)
            self.app.toast(m, "err")

        self.app.call("worlds:backup", {"profileId": self._pid(), "folder": w.get("folder")}, done, fail)

    def _restore(self, bk, btn):
        btn.setEnabled(False)

        def done(res):
            self.reload()
            res = res or {}
            self._wr_info(self.app.t("Мир восстановлен как «{folder}»", folder=res.get("folder", ""))
                          if res.get("ok") else (res.get("error") or ""))

        def fail(m):
            btn.setEnabled(True)
            self.app.toast(m, "err")

        self.app.call("worlds:restore", {"profileId": self._pid(), "file": bk.get("file")}, done, fail)

    def _remove(self, bk):
        if not self.app.confirm("Удалить копию мира «{name}»?", ok_ru="Удалить", danger=True, name=bk.get("world", "")):
            return

        def done(res):
            self.reload()
            if not (res or {}).get("ok"):
                self._wr_info((res or {}).get("error") or "")

        self.app.call("worlds:remove-backup", {"profileId": self._pid(), "file": bk.get("file")}, done,
                      lambda m: self.app.toast(m, "err"))

    # ---------- скриншоты ----------
    def _shots_error(self, gen, msg):
        if gen != self._gen:
            return
        self._clear_shots()
        self.shots_msg.setText(msg)

    def _clear_shots(self):
        self._thumbs.clear()
        self.shots_flow.clear()
        self.shots_msg.setText("")

    def _shots_loaded(self, gen, p, r):
        if gen != self._gen:
            return
        self._clear_shots()
        if not r or not r.get("ok"):
            self.shots_msg.setText((r or {}).get("error") or "Ошибка")
            return
        self.shot_items = list(r.get("items") or [])
        total = r.get("total") or len(self.shot_items)
        self._wr_info(f"{profile_label(p)} · {self.app.t('Скриншотов: {n}', n=total)}" if total else profile_label(p))
        if not self.shot_items:
            self.shots_msg.setText(self.app.t("Скриншотов пока нет. В игре они делаются клавишей F2."))
            return
        for i, it in enumerate(self.shot_items):
            b = QPushButton()
            b.setFixedSize(THUMB_W, THUMB_H)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(str(it.get("file", "")))
            b.setStyleSheet("QPushButton{padding:0;border-radius:10px;background:rgba(0,0,0,90);border:1px solid rgba(255,255,255,30);}"
                            "QPushButton:hover{border:1px solid #ffffff;}")
            b.clicked.connect(lambda _=False, i=i: self.open_shot(i))
            self.shots_flow.addWidget(b)
            self._thumbs.add(b, shot_path(it))

    def open_shot(self, i: int):
        if not self.shot_items:
            return
        p = self.app.current_profile()
        dlg = ShotDialog(self.app, self.shot_items, i, p and p["id"], on_changed=self._shots_changed)
        dlg.exec()
        self.reload()

    def _shots_changed(self):
        # список в диалоге уже обновлён; подпись «Скриншотов: N» обновим после закрытия
        pass
