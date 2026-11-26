"""Окно «Импорт из других лаунчеров»: показывает найденные сборки и копирует выбранные."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QProgressBar, QWidget, QVBoxLayout

from .. import i18n
from ..widgets import Modal, VScroll, label

i18n.register({
    "Импорт из других лаунчеров": "Import from other launchers",
    "Ищу сборки...": "Looking for instances...",
    "Ничего не найдено. Поддерживаются: официальный лаунчер, TLauncher, Prism/MultiMC, CurseForge, Modrinth App.":
        "Nothing found. Supported: the official launcher, TLauncher, Prism/MultiMC, CurseForge, Modrinth App.",
    "Копировать и миры": "Copy worlds too",
    "Импортировать": "Import",
    "Не сейчас": "Not now",
    "Больше не спрашивать": "Don't ask again",
    "уже импортировано": "already imported",
    "модов: {m}, миров: {w}": "mods: {m}, worlds: {w}",
    "Импорт завершён: {n}": "Import finished: {n}",
    "Версия:": "Version:",
    "Ничего не выбрано": "Nothing selected",
    "Найдены сборки из других лаунчеров. Твои файлы не изменяются — всё копируется в папку DLauncher.":
        "Found instances from other launchers. Your files are not changed — everything is copied into DLauncher's folder.",
})


def option_label(o: dict) -> str:
    s = str(o.get("version") or "")
    if o.get("loader") and o["loader"] != "vanilla":
        s += f" · {o['loader']}"
        if o.get("loaderVersion"):
            s += f" {o['loaderVersion']}"
    return s


class ImportDialog(Modal):
    def __init__(self, app, auto: bool = False, parent=None):
        super().__init__(app, "Импорт из других лаунчеров", width=560, parent=parent)
        self.auto = auto
        self.rows: list[dict] = []
        self.busy = False
        self.note = label(app, "Найдены сборки из других лаунчеров. Твои файлы не изменяются — всё копируется в папку DLauncher.",
                          "muted", wrap=True)
        self.body.addWidget(self.note)
        self.status = label(app, "Ищу сборки...", "muted", wrap=True)
        self.body.addWidget(self.status)
        self.scroll = VScroll()
        self.scroll.setMinimumHeight(220)
        self.body.addWidget(self.scroll, 1)
        self.worlds = QCheckBox()
        app.bind(self.worlds, "Копировать и миры")
        self.worlds.setChecked(True)
        self.body.addWidget(self.worlds)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()
        self.body.addWidget(self.bar)
        self.btn_no = self.add_button("Больше не спрашивать" if auto else "Закрыть", "ghost", self._never if auto else self.reject)
        if auto:
            self.add_button("Не сейчас", "ghost", self.reject)
        self.btn_go = self.add_button("Импортировать", "primary", self.run)
        self.btn_go.setEnabled(False)
        app.event.connect(self._on_event)
        self.finished.connect(lambda *_: self._disconnect())
        self.scan()

    def _disconnect(self) -> None:
        try:
            self.app.event.disconnect(self._on_event)
        except (RuntimeError, TypeError):
            pass

    def _on_event(self, channel: str, payload) -> None:
        if channel == "import:progress" and isinstance(payload, dict):
            total = int(payload.get("total") or 0)
            self.bar.show()
            self.bar.setValue(int(100 * int(payload.get("done") or 0) / total) if total else 0)
            self.status.setText(str(payload.get("text") or ""))

    def scan(self) -> None:
        self.app.call("import:scan", {"auto": self.auto}, self._scanned, lambda m: self.status.setText(m))

    def _scanned(self, r) -> None:
        r = r or {}
        cands = r.get("candidates") or []
        if not r.get("ok"):
            self.status.setText(self.app.t(r.get("error") or "?"))
        elif not cands:
            self.status.setText(self.app.t("Ничего не найдено. Поддерживаются: официальный лаунчер, TLauncher, Prism/MultiMC, CurseForge, Modrinth App."))
        else:
            self.status.setText("")
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        for c in cands:
            cb = QCheckBox(f"{c.get('name')}  ·  {c.get('launcher')}")
            cb.setChecked(not c.get("imported"))
            lay.addWidget(cb)
            sub = f"{c.get('version')}" + (f" · {c['loader']}" if c.get("loader") and c["loader"] != "vanilla" else "")
            info = label(self.app, None, "muted")
            info.setText(sub + "  ·  " + self.app.t("модов: {m}, миров: {w}", m=c.get("modsCount", 0), w=c.get("worldsCount", 0))
                         + ("  ·  " + self.app.t("уже импортировано") if c.get("imported") else ""))
            lay.addWidget(info)
            combo = None
            opts = c.get("options") or []
            if len(opts) > 1:
                combo = QComboBox()
                for o in opts:
                    combo.addItem(option_label(o), o["id"])
                idx = combo.findData(c.get("defaultOption"))
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                lay.addWidget(combo)
            self.rows.append({"id": c["id"], "cb": cb, "combo": combo, "name": c.get("name")})
        lay.addStretch(1)
        self.scroll.lay.addWidget(host)
        self.btn_go.setEnabled(bool(cands))

    def run(self) -> None:
        if self.busy:
            return
        ids = [r["id"] for r in self.rows if r["cb"].isChecked()]
        if not ids:
            return self.app.toast("Ничего не выбрано", "warn")
        choices = {r["id"]: r["combo"].currentData() for r in self.rows if r["combo"] is not None and r["id"] in ids}
        self.busy = True
        self.btn_go.setEnabled(False)

        def ok(r):
            self.busy = False
            r = r or {}
            good = [x for x in (r.get("results") or []) if x.get("ok")]
            bad = [x for x in (r.get("results") or []) if not x.get("ok")]
            self.bar.hide()
            self.app.refresh_profiles()
            if r.get("ok") and not bad:
                self.app.toast(self.app.t("Импорт завершён: {n}", n=len(good)), "ok")
                self.accept()
            else:
                msg = r.get("error") or "; ".join(f"{x.get('id')}: {x.get('error')}" for x in bad)
                self.status.setText(self.app.t(msg))
                self.btn_go.setEnabled(True)

        def err(m):
            self.busy = False
            self.btn_go.setEnabled(True)
            self.status.setText(m)
        self.app.call("import:run", {"ids": ids, "withWorlds": self.worlds.isChecked(), "choices": choices}, ok, err)

    def _never(self) -> None:
        self.app.call("import:dismiss", None, lambda r: None)
        self.reject()


def maybe_show_on_start(app) -> None:
    """При первом запуске: если нашлись чужие сборки и мы ещё не спрашивали — предлагаем импорт."""
    def got(r):
        r = r or {}
        if r.get("ok") and not r.get("asked") and r.get("candidates"):
            dlg = ImportDialog(app, auto=True)
            app.call("import:dismiss", None, lambda _r: None)  # спросили один раз
            dlg.exec()
    app.call("import:scan", {"auto": True}, got)
