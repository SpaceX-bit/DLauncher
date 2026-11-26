"""Дымовые тесты страниц: Qt подменён (fakeqt), ядро — настоящее. Ловит опечатки, NameError, неверные формы данных."""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import fakeqt  # noqa: E402

fakeqt.install()
from fakeapp import FakeApp  # noqa: E402

PAGES = [("play", "PlayPage"), ("profiles", "ProfilesPage"), ("mods", "ModsPage"), ("installed", "InstalledPage"),
         ("worlds", "WorldsPage"), ("skins", "SkinsPage"), ("achievements", "AchievementsPage"), ("settings", "SettingsPage")]


class RealApp(FakeApp):
    """FakeApp, у которого call() идёт в настоящее ядро (Api)."""

    def __init__(self, api, **kw):
        super().__init__(**kw)
        self.api = api
        self.ctx = api.ctx
        self.settings.update(api.ctx.public_settings())

    def call(self, channel, payload=None, on_ok=None, on_err=None):
        self.calls.append((channel, payload))
        try:
            res = self.api.call(channel, payload)
        except Exception as e:  # noqa: BLE001
            self.errors = getattr(self, "errors", []) + [(channel, repr(e))]
            if on_err:
                on_err(str(e))
            return
        if on_ok:
            on_ok(res)


@pytest.fixture
def app(ctx, monkeypatch):
    from dlauncher.api import Api
    from dlauncher.core import util

    def offline(url, *a, **k):
        raise util.HttpError(0, url, reason="offline in tests")
    monkeypatch.setattr(util, "request", offline)
    api = Api(ctx)
    ctx.create_profile({"name": "Test", "version": "1.20.1", "loader": "vanilla"})
    a = RealApp(api)
    a.profiles = [dict(p, modsCount=0) for p in ctx.settings["profiles"]]
    a.current_id = ctx.settings["currentProfile"]
    ctx.on_settings_changed = None
    return a


@pytest.mark.parametrize("mod,cls", PAGES)
def test_page_builds_and_cycles(app, mod, cls):
    m = importlib.import_module(f"dlauncher.ui.pages.{mod}")
    page = getattr(m, cls)(app)
    for fn in ("on_show", "retranslate", "selftest"):
        f = getattr(page, fn, None)
        if callable(f):
            f()
    real = [e for e in getattr(app, "errors", []) if "offline in tests" not in e[1]]
    assert not real, real


def test_settings_save_roundtrip(app):
    from dlauncher.ui.pages import settings as st
    f = {"accountMode": "microsoft", "nickname": "  Abcdefghijklmnopqrstu ", "msClientId": " id ", "ram": 5.3,
         "javaPath": "", "lang": "en", "glass": False, "glassStrength": 30, "bgDim": 20, "closeToTray": True,
         "autoStart": False, "compatCheck": True, "autoUpdateMods": True, "achSound": False, "autoBackup": True, "backupKeep": 3, "discordRpc": True,
         "discordClientId": "12ab34", "autoUpdate": True, "updateUrl": "", "curseforgeKey": "k", "rootDir": "/x"}
    p = st.build_patch(f, 16)
    assert p["nickname"] == "Abcdefghijklmnop" and p["ram"] == 5.5 and p["discordClientId"] == "1234"
    s = app.api.call("settings:set", p)
    assert s["accountMode"] == "microsoft" and s["lang"] == "en" and s["glass"] is False and s["closeToTray"] is True
    assert s["autoUpdateMods"] is True and s["achSound"] is False
    assert app.api.call("settings:set", st.build_patch({**f, "autoUpdateMods": False}, 16))["autoUpdateMods"] is False
    assert st.clamp_ram(99, 8) == 8 and st.clamp_ram(0, 8) == 1
    assert st.fmt_gb(4.0) == "4" and st.fmt_gb(4.5) == "4.5"


def test_update_and_discord_text(app):
    from dlauncher.ui.pages import settings as st
    assert "1.8" in st.update_text(app, {"state": "ready", "version": "1.8"})
    assert st.update_text(app, {"state": "downloading", "percent": 40}).endswith("40%")
    assert st.update_text(app, {}) == ""
    assert "user1" in st.discord_text(app, {"state": "ready", "user": "user1"})
    assert st.discord_text(app, None) == ""


def test_importer_dialog(app):
    from dlauncher.ui.dialogs import importer
    d = importer.ImportDialog(app)
    d._scanned({"ok": True, "candidates": [
        {"id": "a", "name": "A", "launcher": "TLauncher", "version": "1.16.5", "loader": "forge", "modsCount": 2,
         "worldsCount": 1, "imported": False, "options": [{"id": "o1", "version": "1.16.5", "loader": "forge",
                                                         "loaderVersion": "36"}, {"id": "o2", "version": "1.16.5"}],
         "defaultOption": "o1"}]})
    assert len(d.rows) == 1
    assert importer.option_label({"version": "1.20", "loader": "fabric", "loaderVersion": "0.15"}) == "1.20 · fabric 0.15"


def test_skin_geometry():
    from dlauncher.ui.pages.skins import skin_parts
    for legacy in (False, True):
        for slim in (False, True):
            for back in (False, True):
                for p in skin_parts(legacy, slim, back):
                    x, y, w, h = p["src"]
                    assert x + w <= 64 and y + h <= (32 if legacy else 64)
                    dx, dy, dw, dh = p["dst"]
                    assert 0 <= dx and dx + dw <= 16 and dy + dh <= 32


def test_buildcard_helpers(app):
    from dlauncher.ui import buildcard as bc
    assert bc.initials("Pixel mon") == "PM" and bc.initials("ATM10") == "AT" and bc.initials("") == "?"
    assert bc.tile_color("x") == bc.tile_color("x") and bc.tile_color("x").startswith("#")
    ps = [{"id": "a"}, {"id": "b", "lastPlayed": 5}, {"id": "c", "lastPlayed": 9}]
    assert [p["id"] for p in bc.recent_first(ps)] == ["c", "b", "a"]
    c = bc.BuildCard(app, {"id": "a", "name": "A", "version": "1.20.1", "loader": "forge", "modsCount": 3}, selected=True)
    assert c.pid == "a"


def test_guides_content():
    from dlauncher.ui import guides, i18n
    from dlauncher.ui.mainwindow import PAGE_SPECS
    pages = {k for k, *_ in PAGE_SPECS}
    for gid in guides.GUIDES:
        cells = guides.portrait_cells(gid)
        if guides.GUIDES[gid].get("asset"):  # герой-картинка: файл должен лежать в assets/guides
            assert os.path.isfile(__import__("dlauncher.resources", fromlist=["asset"]).asset("guides/" + guides.GUIDES[gid]["asset"]))
            continue
        assert 100 < len(cells) <= 256
        assert all(0 <= x < guides.SIZE and 0 <= y < guides.SIZE for x, y in cells)
    assert len(set(guides.TOPIC_ORDER)) == len(guides.TOPICS) >= 10
    for key, title, gid, steps in guides.TOPICS:
        assert steps and gid in guides.GUIDES
        assert i18n.translate(title, "en") != title, title
        used = {st[0] for st in steps}
        assert used - {"steve"}  # в теме рассказывает не Стив, а другой герой
        for g, page, head, text in steps:
            assert g in guides.GUIDES and page in pages
            for ru in (head, text):
                assert i18n.translate(ru, "en") != ru, ru
    for ru in ("Не хотите пройти обучение?", "Не надо", "Да", "Привет! Я Стив", "Хватит", "К темам"):
        assert i18n.translate(ru, "en") != ru, ru
    for g in guides.GUIDES.values():
        assert i18n.translate(g["name"], "en") != g["name"]


def test_tour_done_setting(app):
    app.api.call("settings:set", {"tourDone": True})
    assert app.api.ctx.public_settings()["tourDone"] is True
    app.api.call("settings:set", {"tourDone": "yes"})
    assert app.api.ctx.public_settings()["tourDone"] is False


def test_filter_profiles():
    from dlauncher.ui.buildcard import filter_profiles
    ps = [{"name": "Выживание", "version": "1.20.1", "loader": "fabric"}, {"name": "Тест", "version": "1.16.5", "loader": "forge"}]
    assert filter_profiles(ps, "") == ps and filter_profiles(ps, None) == ps
    assert [p["name"] for p in filter_profiles(ps, "выж")] == ["Выживание"]
    assert [p["name"] for p in filter_profiles(ps, "1.16")] == ["Тест"]
    assert [p["name"] for p in filter_profiles(ps, "FABRIC")] == ["Выживание"]
    assert filter_profiles(ps, "zzz") == []


def test_switch_assets_and_qss():
    from dlauncher.ui import theme
    for f in (theme.SW_OFF, theme.SW_ON):
        assert os.path.isfile(f), f
    assert "switch_on.png" in theme.qss()


def test_other_launchers():
    from dlauncher.ui import i18n
    from dlauncher.ui.dialogs import launchers as L
    assert len(L.LAUNCHERS) >= 5
    for name, site, desc in L.LAUNCHERS:
        assert site.startswith("https://")
        assert i18n.translate(desc, "en") != desc, desc
    u = L.video_url("Prism Launcher", "ru")
    assert u.startswith("https://www.youtube.com/results?search_query=") and "Prism%20Launcher" in u
    assert "review" in L.video_url("Modrinth App", "en")


# ---------------- достижения и автообновление модов ----------------
def test_achievements_core(app):
    from dlauncher.core import achievements as A
    ach = app.ctx.achievements
    sent = []
    app.ctx.send = lambda ch, payload=None: sent.append((ch, payload))
    assert not ach.has("first_profile")
    app.api.call("profiles:create", {"name": "Second", "version": "1.20.1", "loader": "vanilla"})
    assert ach.has("first_profile")
    assert [c for c, _ in sent] == ["achievement:unlocked"] and sent[0][1]["id"] == "first_profile"
    app.api.call("profiles:create", {"name": "Third", "version": "1.20.1", "loader": "vanilla"})
    assert len(sent) == 1  # второй раз не поздравляем
    r = app.api.call("achievements:list")
    assert r["ok"] and r["total"] == len(A.DEFS) and r["done"] == 1
    assert {i["id"] for i in r["items"] if i["unlocked"]} == {"first_profile"}
    assert any(i["hidden"] for i in r["items"])
    # состояние сохраняется на диск
    from dlauncher.core.achievements import Achievements
    assert Achievements(app.ctx).has("first_profile")


def test_achievements_observe_and_limits(app):
    from dlauncher.core import achievements as A
    ach = app.ctx.achievements
    A.observe(app.ctx, "mods:install", {"kind": "shader"}, {"ok": True})
    A.observe(app.ctx, "mods:install", {"kind": "resourcepack"}, {"ok": True})
    A.observe(app.ctx, "mods:install", {"kind": "mod"}, {"ok": True, "extra": 3})
    assert ach.has("shader") and ach.has("resourcepack") and ach.has("first_mod") and not ach.has("modder")
    A.observe(app.ctx, "mods:install", {"kind": "mod"}, {"ok": True, "extra": 5})  # 4 + 6 = 10 модов
    assert ach.has("modder")
    A.observe(app.ctx, "profile:export", None, {"ok": False})  # неудача — не считается
    assert not ach.has("export")
    A.observe(app.ctx, "profile:export", None, {"ok": True})
    assert ach.has("export")
    A.observe(app.ctx, "installed:autoupdate", {}, {"ok": True, "updated": 0})
    assert not ach.has("fresh")
    A.observe(app.ctx, "installed:autoupdate", {}, {"ok": True, "updated": 2})
    assert ach.has("fresh")
    # интерфейс может выдать только «свои» достижения
    assert app.api.call("achievements:grant", {"id": "export2"})["ok"] is False
    assert app.api.call("achievements:grant", {"id": "first_launch"})["ok"] is False
    assert app.api.call("achievements:grant", {"id": "secret"})["new"] is True
    assert app.api.call("achievements:grant", {"id": "secret"})["new"] is False


def test_achievements_stats(app):
    ach = app.ctx.achievements
    app.ctx.stats.load()["profiles"]["p"] = {"ms": 3_700_000, "launches": 12, "last": 0}
    ach.check_stats()
    assert ach.has("first_launch") and ach.has("launches_10") and ach.has("hour") and not ach.has("ten_hours")
    items = {i["id"]: i for i in ach.listing()["items"]}
    assert items["ten_hours"]["progress"][:2] == [1.0, 10.0] or items["ten_hours"]["progress"][0] > 0


def test_achievements_texts_and_ui_helpers():
    from dlauncher.core import achievements as A
    from dlauncher.ui import achievements_ui as U, i18n
    from dlauncher.ui.pages.achievements import progress_text, sort_items
    for aid, glyph, color, title, desc, hidden in A.DEFS:
        assert i18n.translate(title, "en") != title, title
        assert i18n.translate(desc, "en") != desc, desc
        assert color.startswith("#") and len(color) == 7
    assert len(set(A.ORDER)) == len(A.DEFS)
    items = [{"id": "s", "hidden": True, "unlocked": None}, {"id": "b", "unlocked": None},
             {"id": "a", "unlocked": 5}, {"id": "c", "unlocked": 9}]
    assert [i["id"] for i in sort_items(items)] == ["c", "a", "b", "s"]
    assert progress_text({"progress": [3, 10, ""]}) == "3 / 10"
    assert progress_text({"progress": [0.5, 1.0, "ч"]}) == "0.5 / 1 ч"
    assert progress_text({"progress": [3, 10, ""], "unlocked": 1}) == ""


def test_autoupdate_mods_offline(app):
    r = app.api.call("installed:autoupdate", {"profileId": "nope"})
    assert r["ok"] is False
    pid = app.current_id
    inst = app.ctx.instance_dir(pid)
    import os
    os.makedirs(os.path.join(inst, "mods"), exist_ok=True)
    open(os.path.join(inst, "mods", "x.jar"), "wb").write(b"PK")
    r = app.api.call("installed:autoupdate", {"profileId": pid})
    assert r["ok"] is True and r["updated"] == 0 and r.get("offline") is True


def test_mc_icons():
    from dlauncher.core import achievements as A
    from dlauncher.ui import mcicons as M
    assert set(M.ICONS) == set(A.ORDER)  # у каждого достижения свой значок
    for aid in A.ORDER:
        cells = M.icon_cells(aid)
        assert 30 < len(cells) <= 256, aid
        assert all(0 <= x < M.SIZE and 0 <= y < M.SIZE for x, y in cells), aid
        for unlocked in (True, False):
            t = M.tile_cells(aid, unlocked)
            assert all(0 <= x < M.TILE and 0 <= y < M.TILE for x, y in t)
            assert (11, 11) in t
        locked = M.tile_cells(aid, False)
        icon_px = [locked[(x + 3, y + 3)] for (x, y) in M.icon_cells(aid)]
        assert all(c[1:3] == c[3:5] == c[5:7] for c in icon_px), aid  # неполученный — серый силуэт
    assert M.tile_cells("secret", False, known=False)  # знак вопроса
    assert M.tile_cells("export", True)[(11, 1)] != M.tile_cells("modder", True)[(11, 1)]  # золотая и каменная рамки
    assert M.gray("#ff0000").startswith("#") and len(M.gray("#ffffff")) == 7


def test_buildcard_look_groups_status(app):
    from dlauncher.core.base import PROFILE_COLORS, PROFILE_GLYPHS
    from dlauncher.ui import buildcard as bc
    assert bc.tile_look({"name": "Pixel mon"})[1] == "PM"
    assert bc.tile_look({"name": "X", "color": PROFILE_COLORS[1], "glyph": PROFILE_GLYPHS[3]}) == (PROFILE_COLORS[1], PROFILE_GLYPHS[3])
    assert bc.tile_look({"name": "X", "color": "zzz"})[0] == bc.tile_color("X")  # кривой цвет игнорируется
    ps = [{"id": "1", "name": "a", "group": "Выживание"}, {"id": "2", "name": "b"}, {"id": "3", "name": "c", "group": "Выживание"},
          {"id": "4", "name": "d", "group": "Аркада"}]
    g = bc.group_profiles(ps)
    assert [x[0] for x in g] == ["", "Аркада", "Выживание"] and [p["id"] for p in g[2][1]] == ["1", "3"]
    assert [p["id"] for p in bc.filter_profiles(ps, "аркад")] == ["4"]
    online = {"server": {"name": "Hyp", "host": "h"}, "online": True, "latency": 42, "players": {"online": 5, "max": 100}}
    text, up = bc.status_text(app, online)
    assert up and "Hyp" in text and "42 ms" in text and "5/100" in text
    text, up = bc.status_text(app, {"server": {"name": "Hyp", "host": "h"}, "online": False})
    assert not up and "Hyp" in text
    c = bc.BuildCard(app, {"id": "a", "name": "A", "version": "1.20.1", "loader": "forge", "color": PROFILE_COLORS[0], "glyph": "★"})
    c.set_status(online)
    c.set_status({"ok": True, "server": None})
    c.load_status()  # без серверов — ничего не делает


def test_edit_dialog_look_and_ram(app):
    from dlauncher.ui.pages.profiles import EditDialog
    d = EditDialog(app, dict(app.profiles[0]))
    d._set_color("#5b6ee1")
    d._set_glyph("★")
    d._suggest_ram()
    d._srv_favorite()  # сервер не выбран — не падает


def test_changelog_logic(app):
    from dlauncher.ui.dialogs import changelog as ch
    assert ch.should_show({"lastSeenVersion": "2.0.24"}, "2.0.24") == ""
    assert ch.should_show({"lastSeenVersion": "", "tourDone": False}, "2.0.24") == "mark"  # новая установка
    assert ch.should_show({"lastSeenVersion": "", "tourDone": True}, "2.0.24") == "show"  # обновление
    assert ch.should_show({"lastSeenVersion": "2.0.21", "tourDone": False}, "2.0.24") == "show"
    from dlauncher import __version__
    assert ch.CHANGES[0][0] == __version__ and ch.CHANGES[0][1]
    ch.ChangelogDialog(app)


def test_chime_and_sound_setting():
    import os
    from dlauncher.resources import asset
    from dlauncher.ui.achievements_ui import play_chime
    assert play_chime(False) is False
    assert play_chime(True) in (True, False)  # не Windows — тишина без ошибок
    import wave
    with wave.open(asset("achievement.wav")) as w:
        assert w.getframerate() == 44100 and 0.5 < w.getnframes() / w.getframerate() < 3
    assert os.path.getsize(asset("achievement.wav")) < 400_000


def test_update_dialog(app):
    from dlauncher.ui.dialogs.update import UpdateDialog
    d = UpdateDialog(app, "9.9.9", "- что-то новое")
    d._on_event("update:status", {"state": "ready"})  # без нажатия «Скачать» ничего не запускается


def test_theme_tones_and_accent():
    from dlauncher.ui import theme
    base = theme.qss(True, 60)
    assert theme.qss(True, 60, "dark", "") == base
    mid = theme.qss(True, 60, "midnight", "#5b6ee1")
    assert mid != base and "#5b6ee1" in mid and "kind=\"primary\"" in mid
    assert theme.tint("#121213", "midnight") != "#121213" and theme.tint("#ececf0", "midnight") == "#ececf0"  # светлые цвета не трогаем
    assert theme.tint("#121213", "dark") == "#121213" and theme.tint("zzz", "forest") == "zzz"
    assert theme.qss(True, 60, "forest", "not-a-color") == theme.qss(True, 60, "forest", "")  # кривой цвет игнорируется
    light = theme.qss(True, 60, "dark", "#ffe066")  # светлый акцент -> тёмный текст на кнопках
    assert "color: #111114" in light.split('kind="primary"] {')[1].split("}")[0]
    theme.look("midnight")
    assert theme.GRAD_A != "#0a0a0b"
    theme.look("dark")
    assert theme.GRAD_A == "#0a0a0b"


def test_extras_dialogs_and_texts(app):
    from dlauncher.ui.dialogs import extras
    extras.CodeDialog(app, "DLC1-abc", 2)
    extras.EnterCodeDialog(app)
    for w in ({"level": "err", "key": "disk", "n": 0.4}, {"level": "warn", "key": "disk", "n": 2.1},
              {"level": "err", "key": "java", "path": "C:/j"}, {"level": "warn", "key": "ram", "n": 14, "total": 16}):
        t = extras.warning_text(app, w)
        assert t and "{" not in t
    extras.handle_drop(app, ["/definitely/not/here.xyz"])  # несуществующий файл — молча пропускается
    extras.update_pack(app, {"id": "x", "name": "X", "pack": None})  # не Modrinth — только сообщение


def test_buildcard_menu_has_new_actions(app):
    from dlauncher.ui.pages.profiles import ProfilesPage
    page = ProfilesPage(app)
    card = page._card(dict(app.profiles[0]))
    labels = [ru for ru, _fn in card.actions if ru]
    assert {"Дублировать", "Код сборки", "Обновить сборку", "Экспорт .mrpack"} <= set(labels)
