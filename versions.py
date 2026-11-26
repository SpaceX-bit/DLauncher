"""Окно выбора версии (мод, ресурспак, шейдер, сборка). Порт pickPackVersion из features.js.

    pick_version(app, item, source, kind, on_pick, on_cancel=None)
      item   — карточка из mods:search ({id, title, ...})
      kind   — 'mod' | 'resourcepack' | 'shader' | 'modpack'
      on_pick(version_id) — id выбранной версии или '' (поставить последнюю подходящую/стабильную)
      on_cancel()         — окно закрыто без выбора (Отмена / Esc)

Для модов, ресурспаков и шейдеров версии, подходящие профилю (fit), подсвечены зелёным и список
плавно прокручивается к нужной строке.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout, QWidget

from .. import i18n
from ..widgets import Card, Modal, VScroll, button, label
from .shared import NAMES, fmt_date, meta

i18n.register({
    "Версии: {title}": "Versions: {title}",
    "Версии сборки: {title}": "Modpack versions: {title}",
    "Загрузка...": "Loading...",
    "Выбери версию сборки. Первая в списке — самая новая.": "Choose a modpack version. The first one is the newest.",
    "Выбери версию.": "Choose a version.",
    "Зелёным отмечены версии для твоего профиля: {prof}": "Versions for your profile are marked green: {prof}",
    "Только стабильные версии": "Stable versions only",
    "Установить": "Install",
    "Отмена": "Cancel",
    "Подходит": "Fits",
    "Minecraft {mc}": "Minecraft {mc}",
    "У этого проекта нет версий": "This project has no versions",
    "У сборки нет доступных версий": "The modpack has no available versions",
    "Не удалось получить список версий": "Could not load the version list",
    "Можно установить последнюю подходящую версию.": "You can install the latest matching version.",
    "Можно установить последнюю стабильную версию.": "You can install the latest stable version.",
    "Для твоего профиля ({prof}) подходящих версий нет. Можно выбрать любую, но она может не работать.":
        "No versions fit your profile ({prof}). You can pick any, but it may not work.",
    "Эта версия не для твоего профиля ({prof}) — она может не работать.":
        "This version is not for your profile ({prof}) — it may not work.",
    "Версии": "Versions",
})

_SKIP = re.compile(r"^(minecraft|datapack|mrpack)$", re.I)


# ---------- чистая логика (без Qt, проверяется тестами) ----------
def is_mod_kind(kind) -> bool:
    return bool(kind) and kind != "modpack"


def profile_text(info: dict | None, kind: str | None) -> str:
    if not info:
        return ""
    parts = [info.get("version")]
    if kind == "mod" and info.get("loader") and info["loader"] != "vanilla":
        parts.append(NAMES.get(info["loader"], info["loader"]))
    return " · ".join(p for p in parts if p)


def loader_badges(it: dict, info: dict | None, kind: str | None) -> list[tuple[str, bool]]:
    """[(подпись, mine)] — mine только у подходящей версии и подходящего загрузчика."""
    mine: list[str] = []
    if info and info.get("loader"):
        mine = ["quilt", "fabric"] if info["loader"] == "quilt" else [info["loader"]]
    out = []
    for l in it.get("loaders") or []:
        if _SKIP.match(str(l)):
            continue
        low = str(l).lower()
        out.append((NAMES.get(low, str(l)), bool(it.get("fit") and low in mine and kind == "mod")))
    return out


def shown_items(items: list[dict], stable_only: bool) -> list[dict]:
    stable = [i for i in items if i.get("type") == "release"]
    return stable if (stable_only and stable) else items


def default_choice(shown: list[dict], chosen, is_mod: bool):
    keep = next((i for i in shown if i.get("id") == chosen), None)
    if keep:
        return keep
    if is_mod:
        return (next((i for i in shown if i.get("fit") and i.get("type") == "release"), None)
                or next((i for i in shown if i.get("fit")), None))
    return shown[0] if shown else None


def warn_key(items: list[dict], chosen, info, is_mod: bool):
    """None | 'none' (нет подходящих версий) | 'sel' (выбранная версия не подходит)."""
    if not (is_mod and info):
        return None
    if not any(i.get("fit") for i in items):
        return "none"
    sel = next((i for i in items if i.get("id") == chosen), None)
    if sel and not sel.get("fit"):
        return "sel"
    return None


def _badge(text: str, mine: bool) -> QLabel:
    lb = QLabel(text)
    color = "#6ee7a0" if mine else "#b9b2d6"
    lb.setStyleSheet(f"color: {color}; border: 1px solid {color}; border-radius: 7px; padding: 0 6px; font-size: 11px;")
    return lb


class _Row(Card):
    def __init__(self, kind, on_click):
        super().__init__(kind, "h", (10, 8, 12, 8), 10)
        self._on_click = on_click

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._on_click()
        super().mouseReleaseEvent(e)


class VersionPicker(Modal):
    def __init__(self, app, item: dict, source: str, kind: str, on_pick, on_cancel=None):
        self.is_mod = is_mod_kind(kind)
        title = ("Версии: {title}" if self.is_mod else "Версии сборки: {title}")
        super().__init__(app, "Версии", width=680, height=520)
        self.title.setText(app.t(title, title=item.get("title", "")))
        self.item, self.source, self.kind = item, source, kind
        self.on_pick, self.on_cancel = on_pick, on_cancel
        self.items: list[dict] = []
        self.info: dict | None = None
        self.chosen = None if self.is_mod else ""
        self.rows: list[dict] = []
        self.go_enabled = False
        self.warn = ""
        self.scroll_to: str | None = None
        self.stable_only = True
        self._done = False
        self._anim = None

        self.sub = label(app, None, "muted", wrap=True)
        self.sub.setText(app.t("Загрузка...") if self.is_mod else app.t("Выбери версию сборки. Первая в списке — самая новая."))
        self.body.addWidget(self.sub)
        self.rel = QCheckBox()
        app.bind(self.rel, "Только стабильные версии")
        self.rel.setChecked(True)
        self.rel.toggled.connect(self._on_rel)
        self.body.addWidget(self.rel)
        self.scroll = VScroll(spacing=6)
        self.scroll.setMinimumHeight(260)
        self.body.addWidget(self.scroll, 1)
        self.scroll.lay.addWidget(label(app, "Загрузка..."))
        self.warn_label = label(app, None, "warn", wrap=True)
        self.warn_label.hide()
        self.body.addWidget(self.warn_label)
        self.btn_cancel = self.add_button("Отмена", "ghost", on_click=self.reject)
        self.btn_go = self.add_button("Установить", "primary", on_click=self.accept)
        self.btn_go.setEnabled(False)

    # ---------- загрузка ----------
    def load(self) -> None:
        if self.is_mod:
            self.app.call("mods:versions", {"source": self.source, "id": self.item.get("id"),
                                            "kind": self.kind, "profileId": self.app.current_id},
                          self._loaded, lambda m: self._fail(m))
        else:
            self.app.call("pack:versions", {"source": self.source, "id": self.item.get("id")},
                          self._loaded, lambda m: self._fail(m))

    def _loaded(self, r) -> None:
        if self._done:
            return  # пока грузилось, окно закрыли
        if not r or not r.get("ok"):
            return self._fail((r or {}).get("error") or self.app.t("Не удалось получить список версий"))
        self.items = r.get("items") if isinstance(r.get("items"), list) else []
        self.info = r.get("profile") or None
        if self.is_mod:
            if self.info:
                self.sub.setText(self.app.t("Зелёным отмечены версии для твоего профиля: {prof}",
                                            prof=profile_text(self.info, self.kind)))
            else:
                self.sub.setText(self.app.t("Выбери версию."))
            # нет стабильной подходящей версии -> показываем всё, чтобы подсвеченная не пряталась
            self.stable_only = any(i.get("fit") and i.get("type") == "release" for i in self.items)
            self.rel.setChecked(self.stable_only)
        if not self.items:
            self._message(self.app.t("У этого проекта нет версий" if self.is_mod else "У сборки нет доступных версий"))
            self.go_enabled = False
            return
        self.draw()

    def _fail(self, text: str) -> None:
        if self._done:
            return
        tail = "Можно установить последнюю подходящую версию." if self.is_mod else "Можно установить последнюю стабильную версию."
        self.scroll.clear()
        self.scroll.lay.addWidget(label(self.app, None, "muted", wrap=True)).__class__  # noqa: B018
        lb = self.scroll.lay.itemAt(0).widget() if self.scroll.lay.count() else None
        if lb is not None:
            lb.setText(text)
        self.scroll.lay.addWidget(label(self.app, tail, "muted", wrap=True))
        self.fail_text = text
        self.chosen = ""
        self.go_enabled = True
        self.btn_go.setEnabled(True)

    def _message(self, text: str) -> None:
        self.scroll.clear()
        lb = label(self.app, None, "muted", wrap=True)
        lb.setText(text)
        self.scroll.lay.addWidget(lb)

    # ---------- список ----------
    def _on_rel(self, checked=None) -> None:
        self.stable_only = bool(self.rel.isChecked()) if checked is None else bool(checked)
        if self.items:
            self.draw()

    def draw(self) -> None:
        shown = shown_items(self.items, self.stable_only)
        d = default_choice(shown, self.chosen, self.is_mod)
        self.chosen = d["id"] if d else (None if self.is_mod else "")
        self.scroll.clear()
        self.rows = []
        group = QButtonGroup(self)
        self._group = group
        def_widget = first_fit_widget = None
        for it in shown:
            fit = bool(self.is_mod and it.get("fit"))
            row = _Row("fit" if fit else "soft", lambda it=it: self._choose(it, from_row=True))
            radio = QRadioButton()
            radio.setChecked(bool(d and it["id"] == d["id"]))
            radio.toggled.connect(lambda on, it=it: on and self._choose(it))
            group.addButton(radio)
            row.lay.addWidget(radio)
            col = QVBoxLayout()
            col.setSpacing(2)
            name = QLabel(str(it.get("name") or ""))
            name.setStyleSheet("font-weight: 700;")
            col.addWidget(name)
            sub = QHBoxLayout()
            sub.setSpacing(6)
            mc = self.app.t("Minecraft {mc}", mc=it["mc"]) if it.get("mc") else ""
            text = QLabel(meta([mc, fmt_date(self.app, it.get("date"))]))
            text.setProperty("kind", "muted")
            sub.addWidget(text)
            badges = loader_badges(it, self.info, self.kind)
            for t, mine in badges:
                sub.addWidget(_badge(t, mine))
            sub.addStretch(1)
            col.addLayout(sub)
            row.lay.addLayout(col, 1)
            if fit:
                mark = QLabel(self.app.t("Подходит"))
                mark.setStyleSheet("color: #6ee7a0; font-weight: 700;")
                row.lay.addWidget(mark)
            if it.get("type") and it["type"] != "release":
                tb = QLabel(str(it["type"]))
                tb.setProperty("kind", "muted")
                row.lay.addWidget(tb)
            self.scroll.lay.addWidget(row)
            self.rows.append({"item": it, "id": it["id"], "fit": fit, "checked": bool(d and it["id"] == d["id"]),
                              "badges": badges, "widget": row, "radio": radio, "kind": "fit" if fit else "soft",
                              "mark": fit})
            if d and it["id"] == d["id"]:
                def_widget = row
            if it.get("fit") and first_fit_widget is None:
                first_fit_widget = row
        self.scroll.lay.addStretch(1)
        self.go_enabled = (self.chosen is not None) if self.is_mod else bool(shown)
        self.btn_go.setEnabled(self.go_enabled)
        self._sync_warn()
        if self.is_mod:
            target = def_widget or first_fit_widget
            self.scroll_to = next((r["id"] for r in self.rows if r["widget"] is target), None)
            QTimer.singleShot(60, lambda: self._scroll_to(target))  # даём окну дорисоваться

    def _choose(self, it: dict, from_row: bool = False) -> None:
        self.chosen = it["id"]
        if from_row:
            for r in self.rows:
                r["checked"] = r["id"] == it["id"]
                r["radio"].setChecked(r["checked"])
        self.go_enabled = True  # выбор вручную включает кнопку, даже если подходящих версий не было
        self.btn_go.setEnabled(True)
        self._sync_warn()

    def _sync_warn(self) -> None:
        key = warn_key(self.items, self.chosen, self.info, self.is_mod)
        prof = profile_text(self.info, self.kind)
        if key == "none":
            self.warn = self.app.t("Для твоего профиля ({prof}) подходящих версий нет. Можно выбрать любую, но она может не работать.", prof=prof)
        elif key == "sel":
            self.warn = self.app.t("Эта версия не для твоего профиля ({prof}) — она может не работать.", prof=prof)
        else:
            self.warn = ""
        self.warn_label.setText(self.warn)
        self.warn_label.setVisible(bool(self.warn))

    def _scroll_to(self, w: QWidget | None) -> None:
        """Плавно прокручивает список так, чтобы строка оказалась по центру."""
        if w is None or self._done:
            return
        try:
            sb = self.scroll.verticalScrollBar()
            target = w.y() - (self.scroll.viewport().height() - w.height()) // 2
            target = int(max(0, min(int(sb.maximum()), int(target))))
            anim = QPropertyAnimation(sb, b"value", self)
            anim.setDuration(450)
            anim.setEasingCurve(QEasingCurve.InOutCubic)
            anim.setStartValue(sb.value())
            anim.setEndValue(target)
            anim.start()
            self._anim = anim
        except (RuntimeError, TypeError, ValueError):
            pass

    # ---------- закрытие ----------
    def _finish(self, value) -> None:
        if self._done:
            return
        self._done = True
        if value is None:
            if self.on_cancel:
                self.on_cancel()
        else:
            self.on_pick(value)

    def accept(self) -> None:
        v = self.chosen
        super().accept()
        self._finish("" if v is None and not self.is_mod else v)

    def reject(self) -> None:
        super().reject()
        self._finish(None)


def pick_version(app, item: dict, source: str, kind: str, on_pick, on_cancel=None) -> VersionPicker:
    dlg = VersionPicker(app, item, source, kind, on_pick, on_cancel)
    dlg.show()
    dlg.load()
    return dlg
