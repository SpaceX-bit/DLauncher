import os

import pytest

from contenthelp import add_profile, mod_hosts, read, sha1
from dlauncher.api import Api

JAR_A, JAR_B = b"aaa", b"bbb"


@pytest.fixture
def env(ctx, srv):
    mod_hosts(srv)
    api = Api(ctx, modules=["base", "modsmgr"])
    add_profile(ctx)
    d = os.path.join(ctx.instance_dir("p1"), "mods")
    with open(os.path.join(d, "sodium.jar"), "wb") as f:
        f.write(JAR_A)
    with open(os.path.join(d, "other.jar.disabled"), "wb") as f:
        f.write(JAR_B)
    with open(os.path.join(d, "notes.txt"), "w") as f:
        f.write("x")
    os.makedirs(os.path.join(d, "dir.jar"))
    return api, ctx, srv, d


def mock_modrinth(srv, calls=None):
    def upd(req):
        import json
        b = json.loads(req["body"])
        if calls is not None:
            calls.append(b)
        return {sha1(JAR_A): {"id": "v2", "version_number": "0.6", "files": [
            {"primary": True, "url": "https://cdn.modrinth.com/s2.jar", "filename": "sodium-0.6.jar"}]}}
    srv.route("POST", "/v2/version_files", json={sha1(JAR_A): {"id": "v1", "project_id": "P1", "version_number": "0.5"}})
    srv.route("POST", "/v2/version_files/update", json=upd)
    srv.route("GET", "/v2/projects", json=[{"id": "P1", "title": "Sodium", "icon_url": "https://cdn.modrinth.com/i.png"}])
    srv.route("GET", "/cdn/s2.jar", body=b"new-sodium")


def test_list_enrich_and_update_flag(env):
    api, ctx, srv, d = env
    calls = []
    mock_modrinth(srv, calls)
    r = api.call("installed:list", {"profileId": "p1"})
    assert r["ok"] and r["checked"] and r["kind"] == "mod" and r["dir"] == d
    assert r["profile"] == {"id": "p1", "name": "Fab", "version": "1.21.1", "loader": "fabric"}
    assert [i["file"] for i in r["items"]] == ["other.jar.disabled", "sodium.jar"]   # txt и папка не в списке
    sod = r["items"][1]
    assert sod["title"] == "Sodium" and sod["icon"] == "https://cdn.modrinth.com/i.png" and sod["version"] == "0.5"
    assert sod["projectId"] == "P1" and sod["enabled"] is True and sod["size"] == 3
    assert sod["update"] == {"version": "0.6", "url": "https://cdn.modrinth.com/s2.jar", "filename": "sodium-0.6.jar"}
    off = r["items"][0]
    assert off["enabled"] is False and off["title"] is None and off["update"] is None and "hash" not in off
    assert calls[0]["loaders"] == ["fabric"] and calls[0]["game_versions"] == ["1.21.1"] and calls[0]["hashes"] == [sha1(JAR_A)]


def test_list_offline_and_check_false(env):
    api, ctx, srv, d = env
    srv.route("POST", "/v2/version_files", status=500, body=b"{}")  # сеть «отвалилась»
    srv.log.clear()
    r = api.call("installed:list", {"profileId": "p1", "check": False})
    assert r["ok"] and r["checked"] is False and len(r["items"]) == 2 and not srv.log
    r = api.call("installed:list", {"profileId": "p1"})
    assert r["ok"] and r["checked"] is False and r["items"][1]["title"] is None
    assert api.call("installed:list", {"profileId": "nope"}) == {"ok": False, "error": "Профиль не найден"}
    assert api.call("installed:list", {})["ok"] is False
    # папки ещё нет
    import shutil
    shutil.rmtree(d)
    r = api.call("installed:list", {"profileId": "p1"})
    assert r["ok"] and r["items"] == []


def test_list_quilt_loaders_and_kinds(env):
    api, ctx, srv, d = env
    add_profile(ctx, "q", name="Q", loader="quilt")
    rp = os.path.join(ctx.instance_dir("q"), "resourcepacks")
    with open(os.path.join(rp, "a.zip"), "wb") as f:
        f.write(JAR_A)
    with open(os.path.join(rp, "b.zip.disabled"), "wb") as f:
        f.write(JAR_B)
    with open(os.path.join(rp, "c.jar"), "wb") as f:
        f.write(JAR_B)
    calls = []
    mock_modrinth(srv, calls)
    r = api.call("installed:list", {"profileId": "q", "kind": "resourcepack"})
    assert r["kind"] == "resourcepack" and [i["file"] for i in r["items"]] == ["a.zip", "b.zip.disabled"]
    assert "loaders" not in calls[0] and calls[0]["game_versions"] == ["1.21.1"]   # у паков — только версия игры
    r = api.call("installed:list", {"profileId": "q", "kind": "bogus"})
    assert r["kind"] == "mod" and r["items"] == []
    with open(os.path.join(ctx.instance_dir("q"), "mods", "m.jar"), "wb") as f:
        f.write(JAR_A)
    calls.clear()
    api.call("installed:list", {"profileId": "q"})
    assert calls[0]["loaders"] == ["quilt", "fabric"]


def test_toggle_delete(env):
    api, ctx, srv, d = env
    r = api.call("installed:toggle", {"profileId": "p1", "file": "other.jar.disabled"})
    assert r == {"ok": True, "file": "other.jar", "enabled": True} and os.path.exists(os.path.join(d, "other.jar"))
    r = api.call("installed:toggle", {"profileId": "p1", "file": "other.jar"})
    assert r == {"ok": True, "file": "other.jar.disabled", "enabled": False} and not os.path.exists(os.path.join(d, "other.jar"))
    for bad in ("../evil.jar", "a/b.jar", "..\\x.jar", "notes.txt", "", None, 5, "sub/../x.jar", "x.JAR.DISABLEDX"):
        assert api.call("installed:toggle", {"profileId": "p1", "file": bad}) == {"ok": False, "error": "Неверный файл"}
        assert api.call("installed:delete", {"profileId": "p1", "file": bad}) == {"ok": False, "error": "Неверный файл"}
    assert api.call("installed:toggle", {"profileId": "p1", "file": "ghost.jar"}) == {"ok": False, "error": "Файл не найден"}
    assert api.call("installed:toggle", {"profileId": "zzz", "file": "sodium.jar"})["ok"] is False
    # ресурспак: расширение .zip, для мода .zip недопустим
    assert api.call("installed:toggle", {"profileId": "p1", "file": "x.zip", "kind": "mod"})["ok"] is False
    rp = os.path.join(ctx.instance_dir("p1"), "resourcepacks", "x.zip")
    with open(rp, "wb") as f:
        f.write(b"z")
    assert api.call("installed:toggle", {"profileId": "p1", "file": "x.zip", "kind": "resourcepack"})["file"] == "x.zip.disabled"
    assert api.call("installed:delete", {"profileId": "p1", "file": "x.zip.disabled", "kind": "resourcepack"})["ok"]
    assert not os.path.exists(rp + ".disabled")
    # удаление
    assert api.call("installed:delete", {"profileId": "p1", "file": "sodium.jar"}) == {"ok": True}
    assert not os.path.exists(os.path.join(d, "sodium.jar"))
    assert api.call("installed:delete", {"profileId": "p1", "file": "sodium.jar"}) == {"ok": True}   # force: нет файла — не ошибка


def test_update(env):
    api, ctx, srv, d = env
    mock_modrinth(srv)
    base = {"profileId": "p1", "file": "sodium.jar", "filename": "sodium-0.6.jar"}
    for bad_url in ("https://evil.com/a.jar", "http://cdn.modrinth.com/s2.jar", "https://modrinth.com.evil.com/a.jar", "nonsense", None):
        r = api.call("installed:update", {**base, "url": bad_url})
        assert r == {"ok": False, "error": "Недопустимый адрес загрузки"}
    assert api.call("installed:update", {**base, "url": "https://cdn.modrinth.com/s2.jar", "filename": "../x.jar"})["ok"] is False
    assert api.call("installed:update", {**base, "url": "https://cdn.modrinth.com/s2.jar", "file": "../sodium.jar"})["ok"] is False
    r = api.call("installed:update", {**base, "url": "https://cdn.modrinth.com/s2.jar"})
    assert r == {"ok": True, "file": "sodium-0.6.jar"}
    assert read(os.path.join(d, "sodium-0.6.jar")) == b"new-sodium" and not os.path.exists(os.path.join(d, "sodium.jar"))
    # отключённый мод остаётся отключённым
    with open(os.path.join(d, "old.jar.disabled"), "wb") as f:
        f.write(b"o")
    r = api.call("installed:update", {"profileId": "p1", "file": "old.jar.disabled", "filename": "new.jar", "url": "https://cdn.modrinth.com/s2.jar"})
    assert r == {"ok": True, "file": "new.jar.disabled"}
    assert os.path.exists(os.path.join(d, "new.jar.disabled")) and not os.path.exists(os.path.join(d, "old.jar.disabled"))
    # тот же файл: просто перезаписывается, не удаляется
    r = api.call("installed:update", {"profileId": "p1", "file": "new.jar.disabled", "filename": "new.jar", "url": "https://cdn.modrinth.com/s2.jar"})
    assert r["ok"] and os.path.exists(os.path.join(d, "new.jar.disabled"))
    # ошибка скачивания: старый файл остаётся
    srv.route("GET", "/cdn/missing.jar", status=404, body=b"")
    r = api.call("installed:update", {"profileId": "p1", "file": "new.jar.disabled", "filename": "z.jar", "url": "https://cdn.modrinth.com/missing.jar"})
    assert r["ok"] is False and "404" in r["error"] and os.path.exists(os.path.join(d, "new.jar.disabled"))
