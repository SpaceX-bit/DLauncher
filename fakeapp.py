"""Поддельный AppContext для тестов логики страниц (работает вместе с fakeqt).

    app = FakeApp(responses={"mods:search": {...} или функция(payload)}, settings={...}, profiles=[...])
    page = ModsPage(app); app.calls -> список (канал, payload); app.toasts -> [(текст, вид)]
call() синхронный: колбэк вызывается сразу. Нет ответа в responses -> on_err("нет ответа для канала").
"""
class Sig:
    def __init__(self):
        self.slots = []

    def connect(self, fn, *a, **k):
        self.slots.append(fn)

    def disconnect(self, *a):
        self.slots.clear()

    def emit(self, *args):
        for s in list(self.slots):
            s(*args)


class FakeCtx:
    def __init__(self):
        self.app_version = "2.0.0"
        self.diags = []

    def diag(self, t):
        self.diags.append(t)


class FakeApp:
    def __init__(self, responses=None, settings=None, profiles=None, current=None, lang="ru"):
        self.responses = responses or {}
        self.settings = {"lang": lang, "nickname": "Player", "ram": 4, "systemRamGb": 16, "compatCheck": True,
                         "accountMode": "offline", "glass": True, "glassStrength": 60, "bgDim": 0,
                         "appVersion": "2.0.0", "autoBackup": True, "backupKeep": 5, "autoUpdate": True,
                         "closeToTray": False, "autoStart": False, "discordRpc": False, "discordClientId": "",
                         "curseforgeKey": "", "javaPath": "", "msClientId": "", "updateUrl": "", "rootDir": "/tmp/dl",
                         "bgUrl": "", "bgType": "", "bgName": ""}
        if settings:
            self.settings.update(settings)
        self.profiles = profiles or []
        self.current_id = current or (self.profiles[0]["id"] if self.profiles else None)
        self.calls, self.toasts, self.pages_shown = [], [], []
        self.confirm_result = True
        self.ctx = FakeCtx()
        self.window = None
        self.settings_changed, self.profiles_changed, self.lang_changed, self.event = Sig(), Sig(), Sig(), Sig()
        self.texts = []

    @property
    def lang(self):
        return "en" if self.settings.get("lang") == "en" else "ru"

    def call(self, channel, payload=None, on_ok=None, on_err=None):
        self.calls.append((channel, payload))
        if channel not in self.responses:
            if on_err:
                on_err(f"нет ответа для канала {channel}")
            return
        r = self.responses[channel]
        try:
            res = r(payload) if callable(r) else r
        except Exception as e:  # noqa: BLE001
            if on_err:
                on_err(str(e))
            return
        if on_ok:
            on_ok(res)

    call_sync = lambda self, channel, payload=None: (self.responses[channel](payload) if callable(self.responses[channel]) else self.responses[channel])  # noqa: E731

    def post(self, fn):
        fn()

    def run_gui(self, fn):
        return fn()

    def t(self, text, **kw):
        from dlauncher.ui import i18n
        out = i18n.translate(text, self.lang)
        return out.format(**kw) if kw else out

    def L(self, ru, en):
        return en if self.lang == "en" else ru

    def locale(self):
        return "en-US" if self.lang == "en" else "ru-RU"

    def bind(self, widget, ru, prop="text"):
        self.texts.append((widget, ru, prop))
        try:
            setattr(widget, "_bound_" + prop, ru)
        except Exception:
            pass

    def toast(self, text, kind="info"):
        self.toasts.append((text, kind))

    def confirm(self, text_ru, *a, **k):
        return self.confirm_result

    def info(self, *a, **k):
        pass

    def ask_text(self, *a, **k):
        return getattr(self, "ask_result", None)

    def show_page(self, key):
        self.pages_shown.append(key)

    def refresh_profiles(self, cb=None):
        self.call("profiles:list", None, lambda r: (setattr(self, "profiles", r["profiles"]), setattr(self, "current_id", r["current"]), self.profiles_changed.emit(), cb and cb()))

    def refresh_settings(self, cb=None):
        pass

    def save_settings(self, patch, on_ok=None, on_err=None):
        self.settings.update(patch)
        self.calls.append(("settings:set", patch))
        if on_ok:
            on_ok(self.settings)

    def current_profile(self):
        return self.find_profile(self.current_id)

    def find_profile(self, pid):
        for p in self.profiles:
            if p.get("id") == pid:
                return p
        return None
