import os, pytest
from dlauncher.api import Api
from dlauncher.core import util
from dlauncher.core.base import parse_jvm_args


def test_settings_roundtrip_and_clamp(ctx):
    api = Api(ctx, modules=["base"])
    s = api.call("settings:set", {"ram": 9999, "lang": "xx", "bgDim": 500, "glassStrength": -4, "backupKeep": 0, "nickname": "Steve", "hack": 1})
    assert s["ram"] == s["systemRamGb"] and s["lang"] == "ru" and s["bgDim"] == 80 and s["glassStrength"] == 0
    assert s["backupKeep"] == 5 and s["nickname"] == "Steve" and "hack" not in s and "profiles" not in s
    from dlauncher.core.ctx import Ctx
    c2 = Ctx(user_data=ctx.user_data)
    assert c2.settings["nickname"] == "Steve"


def test_profiles_crud(ctx, srv):
    srv.map_host("https://launchermeta.mojang.com", "")
    srv.route("GET", "/mc/game/version_manifest_v2.json", json={"latest": {"release": "1.21"}, "versions": [{"id": "1.21", "type": "release", "releaseTime": "x"}]})
    api = Api(ctx, modules=["base"])
    r = api.call("profiles:create", {"version": "1.21", "name": "Мой / профиль", "loader": "fabric", "loaderVersion": "0.15"})
    assert r["ok"] and r["profile"]["loader"] == "fabric" and r["profile"]["versionType"] == "release"
    pid = r["profile"]["id"]
    assert os.path.isdir(os.path.join(ctx.root, "instances", pid, "mods"))
    assert api.call("profiles:create", {})["ok"] is False
    assert api.call("profiles:update", {"id": pid, "patch": {"width": 800}})["ok"] is False
    assert api.call("profiles:update", {"id": pid, "patch": {"width": 800, "height": 600, "jvmArgs": "-XX:+UseG1GC"}})["ok"]
    assert api.call("profiles:update", {"id": pid, "patch": {"jvmArgs": "-Xmx2G"}})["ok"] is False
    assert api.call("profiles:update", {"id": pid, "patch": {"name": " "}})["ok"] is False
    lst = api.call("profiles:list")
    assert lst["current"] == pid and lst["profiles"][0]["modsCount"] == 0
    d = api.call("profiles:delete", {"id": pid})
    assert d["ok"] and d["current"] is None and not os.path.exists(os.path.join(ctx.root, "instances", pid))
    assert api.call("versions:list")["latest"]["release"] == "1.21"


def test_jvm_args():
    assert parse_jvm_args('"-Dfoo=a b" -XX:+X') == ["-Dfoo=a b", "-XX:+X"]
    with pytest.raises(ValueError):
        parse_jvm_args("foo")


def test_http_download(srv, tmp_path):
    srv.route("GET", "/f", body=b"x" * 500000)
    seen = []
    util.download(srv.base + "/f", str(tmp_path / "a" / "f.bin"), seen.append)
    assert os.path.getsize(tmp_path / "a" / "f.bin") == 500000 and seen[-1] == 100
    srv.route("GET", "/e", status=404, body=b"{}")
    with pytest.raises(util.HttpError):
        util.get_json(srv.base + "/e")
    assert util.safe_join(str(tmp_path), "a/b").startswith(str(tmp_path))
    with pytest.raises(ValueError):
        util.safe_join(str(tmp_path), "../x")


def test_suggest_ram_and_profile_look(ctx, srv):
    from dlauncher.core.base import PROFILE_COLORS, PROFILE_GLYPHS, suggest_ram
    assert suggest_ram(16, 0, "vanilla", "1.21")[0] == 3
    assert suggest_ram(16, 20, "fabric", "1.20.1")[0] == 4
    assert suggest_ram(16, 60, "forge", "1.20.1")[0] == 6
    assert suggest_ram(32, 200, "forge", "1.20.1")[0] == 10
    assert suggest_ram(32, 20, "forge", "1.12.2")[0] == 3  # старая версия с модами — на 1 ГБ меньше
    gb, why = suggest_ram(8, 200, "forge", "1.20.1")  # не больше половины оперативки
    assert gb == 4 and "половин" in why
    assert suggest_ram(2, 0)[0] == 2

    srv.map_host("https://launchermeta.mojang.com", "")
    srv.route("GET", "/mc/game/version_manifest_v2.json", json={"latest": {"release": "1.21"}, "versions": [{"id": "1.21", "type": "release", "releaseTime": "x"}]})
    api = Api(ctx, modules=["base"])
    pid = api.call("profiles:create", {"version": "1.21", "name": "Look", "loader": "vanilla"})["profile"]["id"]
    r = api.call("ram:suggest", {"profileId": pid})
    assert r["ok"] and 2 <= r["ram"] <= 10 and r["reason"]
    assert api.call("ram:suggest", {"profileId": "nope"})["ok"] is False
    ok = api.call("profiles:update", {"id": pid, "patch": {"color": PROFILE_COLORS[2], "glyph": PROFILE_GLYPHS[0], "group": "  Выживание   сервер "}})
    assert ok["ok"]
    p = api.call("profiles:list")["profiles"][0]
    assert p["color"] == PROFILE_COLORS[2] and p["glyph"] == PROFILE_GLYPHS[0] and p["group"] == "Выживание сервер"
    api.call("profiles:update", {"id": pid, "patch": {"color": "red", "glyph": "ZZZ", "group": "x" * 80}})
    p = api.call("profiles:list")["profiles"][0]
    assert p.get("color") in (None, "") and p.get("glyph") in (None, "") and len(p["group"]) <= 24


def test_pick_server():
    from dlauncher.core.servers import pick_server
    a = {"id": "1", "host": "a.net", "port": 25565}
    b = {"id": "2", "host": "b.net", "port": 25565, "favorite": True}
    assert pick_server({"servers": [a, b]}) is b
    assert pick_server({"servers": [a], "lastServer": "1"}) is a
    assert pick_server({"servers": [a]}) is None and pick_server({}) is None


def test_new_settings_keys(ctx):
    api = Api(ctx, modules=["base"])
    s = api.call("settings:get")
    assert s["achSound"] is True and s["lastSeenVersion"] == ""
    s = api.call("settings:set", {"achSound": False, "lastSeenVersion": "2.0.22"})
    assert s["achSound"] is False and s["lastSeenVersion"] == "2.0.22"


def test_updater_ask_then_download(ctx, monkeypatch, tmp_path):
    from dlauncher.core import updater, util
    ctx.is_packaged = True
    ctx.app_version = "2.0.1"
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater, "bundled_url", lambda f=None: "https://github.com/a/b")
    rel = {"tag_name": "v2.0.9", "body": "- новое", "assets": [{"name": "DLauncher-Setup-2.0.9.exe", "browser_download_url": "http://x/y.exe"}]}
    monkeypatch.setattr(util, "get_json", lambda *a, **k: rel)
    got = []
    monkeypatch.setattr(util, "download", lambda url, dest, prog=None: open(dest, "wb").write(b"MZ") and None)
    ctx.user_data = str(tmp_path)
    h, _check = updater.handlers_and_service(ctx)
    ctx.send = lambda ch, p=None: got.append((ch, p))
    assert h["update:download"]()["ok"] is False  # сначала нужна проверка
    assert h["update:check"]()["ok"]
    av = [p for ch, p in got if p and p.get("state") == "available"][0]
    assert av["version"] == "2.0.9" and av["ask"] is True and "новое" in av["notes"]
    assert not any(p.get("state") in ("downloading", "ready") for ch, p in got if p)  # без «Скачать» ничего не качается
    assert h["update:download"]()["ok"]
    assert [p for ch, p in got if p and p.get("state") == "ready"]
