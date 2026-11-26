"""Откат, дублирование, код сборки, обновление сборки, проверка перед запуском, брошенные файлы."""
import hashlib
import io
import json
import os
import zipfile

import pytest

from dlauncher.api import Api
from dlauncher.core import modpacks, profileio, rollback, util


def mk(ctx, name="P", **extra):
    p = ctx.create_profile({"name": name, "version": "1.20.1", "versionType": "release", "loader": "fabric", "loaderVersion": "0.15"})
    p.update(extra)
    return p


def put(ctx, p, rel, data=b"PK"):
    f = os.path.join(ctx.instance_dir(p["id"]), rel)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    open(f, "wb").write(data)
    return f


def test_rollback_module(ctx):
    p = mk(ctx)
    a = put(ctx, p, "mods/a-1.jar", b"old")
    rollback.reset(ctx, p["id"])
    rollback.stash(ctx, p["id"], "mods/a-1.jar")
    put(ctx, p, "mods/a-2.jar", b"new")
    rollback.added(ctx, p["id"], "mods/a-2.jar")
    assert not os.path.exists(a) and rollback.count(ctx, p["id"]) == 2 and rollback.names(ctx, p["id"]) == ["a-1.jar"]
    r = rollback.restore(ctx, p["id"])
    assert r["ok"] and r["restored"] == 1 and r["removed"] == 1
    assert open(a, "rb").read() == b"old" and not os.path.exists(os.path.join(os.path.dirname(a), "a-2.jar"))
    assert rollback.restore(ctx, p["id"])["ok"] is False  # второй раз откатывать нечего
    with pytest.raises(ValueError):
        rollback.stash(ctx, p["id"], "../evil.jar")


def test_mod_update_can_be_rolled_back(ctx, monkeypatch):
    api = Api(ctx, modules=["base", "modsmgr"])
    p = mk(ctx)
    put(ctx, p, "mods/a-1.jar", b"old")
    monkeypatch.setattr(util, "download", lambda url, dest, prog=None: open(dest, "wb").write(b"new") and None)
    r = api.call("installed:update", {"profileId": p["id"], "file": "a-1.jar", "url": "https://cdn.modrinth.com/x/a-2.jar", "filename": "a-2.jar", "kind": "mod"})
    assert r["ok"]
    mods = os.path.join(ctx.instance_dir(p["id"]), "mods")
    assert sorted(os.listdir(mods)) == ["a-2.jar"]
    assert api.call("installed:rollback_info", {"profileId": p["id"]})["count"] == 2
    rb = api.call("installed:rollback", {"profileId": p["id"]})
    assert rb["ok"] and sorted(os.listdir(mods)) == ["a-1.jar"] and open(os.path.join(mods, "a-1.jar"), "rb").read() == b"old"
    assert api.call("installed:rollback", {"profileId": p["id"]})["ok"] is False
    assert api.call("installed:rollback", {"profileId": "nope"})["ok"] is False


def test_duplicate_profile(ctx):
    api = Api(ctx, modules=["base"])
    p = mk(ctx, "Мир", color="#5b6ee1", glyph="★", group="Выживание", ram=6, servers=[{"id": "s1", "name": "S", "host": "a.net", "port": 25565, "favorite": True}])
    put(ctx, p, "mods/a.jar")
    put(ctx, p, "saves/W/level.dat")
    put(ctx, p, "logs/latest.log")
    cur = ctx.settings["currentProfile"]
    r = api.call("profiles:duplicate", {"id": p["id"]})
    assert r["ok"]
    n = r["profile"]
    assert n["id"] != p["id"] and n["name"] == "Мир (копия)" and n["color"] == "#5b6ee1" and n["group"] == "Выживание" and n["ram"] == 6
    assert n["servers"][0]["host"] == "a.net" and n["servers"][0]["id"] != "s1"
    d = ctx.instance_dir(n["id"])
    assert os.path.isfile(os.path.join(d, "mods", "a.jar")) and not os.path.exists(os.path.join(d, "saves", "W"))
    assert not os.path.exists(os.path.join(d, "logs"))
    assert ctx.settings["currentProfile"] == cur  # выбранной остаётся прежняя
    r2 = api.call("profiles:duplicate", {"id": p["id"], "withWorlds": True})
    assert os.path.isfile(os.path.join(ctx.instance_dir(r2["profile"]["id"]), "saves", "W", "level.dat"))
    assert api.call("profiles:duplicate", {"id": "nope"})["ok"] is False


def test_build_code_roundtrip():
    h1, h2 = hashlib.sha1(b"a").hexdigest(), hashlib.sha1(b"b").hexdigest()
    code = profileio.make_code({"n": "Моя сборка", "m": "1.20.1", "l": "fabric", "v": "0.15"}, [[h1, h2], [], [h1]])
    assert code.startswith("DLC1-") and len(code) < 300
    head, groups = profileio.read_code("  " + code[:20] + "\n" + code[20:] + " ")  # пробелы и переносы не мешают
    assert head["n"] == "Моя сборка" and groups == [[h1, h2], [], [h1]]
    for bad in ("", "abc", "DLC1-", "DLC1-AAAA", code[:-6], "DLC2-" + code[5:]):
        with pytest.raises(ValueError):
            profileio.read_code(bad)
    known = {h1: {"url": "https://cdn.modrinth.com/data/x/versions/y/a.jar", "size": 1, "filename": "a.jar"}}
    idx, lost = profileio.index_from_code(head, groups, known)
    assert lost == 1 and [f["path"] for f in idx["files"]] == ["mods/a.jar", "shaderpacks/a.jar"]
    assert idx["dependencies"] == {"minecraft": "1.20.1", "fabric-loader": "0.15"}
    assert modpacks.parse_index(json.dumps(idx))[1:] == ("1.20.1", "fabric", "0.15")


def test_code_export_and_import(ctx, monkeypatch):
    api = Api(ctx, modules=["base", "profileio", "modpacks"])
    p = mk(ctx)
    put(ctx, p, "mods/a.jar", b"AAA")
    put(ctx, p, "mods/own.jar", b"OWN")
    ha = hashlib.sha1(b"AAA").hexdigest()
    monkeypatch.setattr(profileio, "lookup", lambda sh: {ha: {"url": "https://cdn.modrinth.com/data/x/a.jar", "size": 3, "filename": "a.jar"}} if ha in sh else {})
    r = api.call("profile:code", {"profileId": p["id"]})
    assert r["ok"] and r["linked"] == 1 and r["skipped"] == 1
    monkeypatch.setattr(util, "download", lambda url, dest, prog=None: (os.makedirs(os.path.dirname(dest), exist_ok=True), open(dest, "wb").write(b"AAA")) and None)
    n = api.call("profile:code_import", {"code": r["code"]})
    assert n["ok"] and n["missing"] == []
    assert os.path.isfile(os.path.join(ctx.instance_dir(n["profile"]["id"]), "mods", "a.jar"))
    assert n["profile"]["loader"] == "fabric" and n["profile"]["name"] == "P"
    assert api.call("profile:code_import", {"code": "мусор"})["ok"] is False
    empty = mk(ctx, "Empty")
    assert api.call("profile:code", {"profileId": empty["id"]})["ok"] is False


def make_mrpack(path, files, name="Pack", extra=None):
    idx = {"formatVersion": 1, "game": "minecraft", "name": name, "dependencies": {"minecraft": "1.20.4", "fabric-loader": "0.16"},
           "files": [{"path": p, "hashes": {"sha1": hashlib.sha1(d).hexdigest()}, "downloads": ["https://cdn.modrinth.com/data/" + p], "env": {"client": "required"}} for p, d in files.items()]}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("modrinth.index.json", json.dumps(idx))
        for k, v in (extra or {}).items():
            z.writestr(k, v)


def test_update_pack_in_place(ctx, monkeypatch, tmp_path):
    p = mk(ctx, "Pack", pack={"source": "modrinth", "id": "abc", "version": "1", "versionId": "v1"}, packFiles=["mods/old.jar", "mods/keep.jar"])
    put(ctx, p, "mods/old.jar", b"old")
    put(ctx, p, "mods/keep.jar", b"keep1")
    put(ctx, p, "mods/mine.jar", b"mine")
    put(ctx, p, "options.txt", b"mine-options")
    put(ctx, p, "saves/W/level.dat", b"world")
    mr = str(tmp_path / "new.mrpack")
    make_mrpack(mr, {"mods/keep.jar": b"keep2", "mods/new.jar": b"new"}, extra={"overrides/options.txt": "pack-options", "overrides/config/x.toml": "x"})
    blobs = {"mods/keep.jar": b"keep2", "mods/new.jar": b"new"}

    def fake_dl(url, dest, prog=None):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        key = url.split("/data/")[-1] if "/data/" in url else None
        open(dest, "wb").write(blobs[key] if key else open(mr, "rb").read())
    monkeypatch.setattr(util, "download", fake_dl)
    ver = {"id": "v2", "version_number": "2", "files": [{"primary": True, "url": "https://cdn.modrinth.com/pack.mrpack"}]}
    r = modpacks.update_pack(ctx, p, ver)
    d = ctx.instance_dir(p["id"])
    assert r["version"] == "2" and r["missing"] == []
    assert sorted(os.listdir(os.path.join(d, "mods"))) == ["keep.jar", "mine.jar", "new.jar"]  # old.jar убран, своё мод-файл цел
    assert open(os.path.join(d, "mods", "keep.jar"), "rb").read() == b"keep2"
    assert open(os.path.join(d, "options.txt"), "rb").read() == b"mine-options"  # свои настройки игрока сохранены
    assert os.path.isfile(os.path.join(d, "config", "x.toml")) and os.path.isfile(os.path.join(d, "saves", "W", "level.dat"))
    assert p["version"] == "1.20.4" and p["pack"]["versionId"] == "v2" and sorted(p["packFiles"]) == ["mods/keep.jar", "mods/new.jar"]
    rb = rollback.restore(ctx, p["id"])
    assert rb["ok"] and sorted(os.listdir(os.path.join(d, "mods"))) == ["keep.jar", "mine.jar", "old.jar"]
    assert open(os.path.join(d, "mods", "keep.jar"), "rb").read() == b"keep1"
    # сборка, поставленная старой версией лаунчера (нет packFiles), на месте не обновляется
    q = mk(ctx, "Old", pack={"source": "modrinth", "id": "abc", "version": "1"})
    with pytest.raises(ValueError):
        modpacks.update_pack(ctx, q, ver)


def test_pack_updates_check(ctx, monkeypatch):
    api = Api(ctx, modules=["base", "modpacks"])
    p = mk(ctx, "Pack", pack={"source": "modrinth", "id": "abcd1234", "version": "1.0", "versionId": "v1"}, packFiles=["mods/a.jar"])
    vs = [{"id": "v3", "version_number": "3.0", "version_type": "beta"}, {"id": "v2", "version_number": "2.0", "version_type": "release", "name": "Two"},
          {"id": "v1", "version_number": "1.0", "version_type": "release"}]
    monkeypatch.setattr(util, "get_json", lambda *a, **k: vs)
    r = api.call("pack:updates", {"profileId": p["id"]})
    assert r["ok"] and r["available"] and r["version"] == "2.0" and r["canUpdate"] is True
    p["pack"]["versionId"] = "v2"
    assert api.call("pack:updates", {"profileId": p["id"]})["available"] is False
    q = mk(ctx, "Own")
    assert api.call("pack:updates", {"profileId": q["id"]})["available"] is False
    assert api.call("pack:updates", {"profileId": "nope"})["ok"] is False


def test_preflight_and_drop(ctx, tmp_path):
    api = Api(ctx, modules=["base"])
    p = mk(ctx, javaPath="/nonexistent/java")
    r = api.call("launch:preflight", {"profileId": p["id"]})
    assert r["ok"] and any(w["key"] == "java" and w["level"] == "err" for w in r["warnings"])
    jar = tmp_path / "cool.jar"
    jar.write_bytes(b"PK")
    d = api.call("files:drop", {"profileId": p["id"], "path": str(jar)})
    assert d["ok"] and d["folder"] == "mods" and os.path.isfile(os.path.join(ctx.instance_dir(p["id"]), "mods", "cool.jar"))
    assert api.call("files:drop", {"profileId": p["id"], "path": str(jar)})["ok"] is False  # уже есть
    z = tmp_path / "pack.zip"
    z.write_bytes(b"PK")
    assert api.call("files:drop", {"profileId": p["id"], "path": str(z), "kind": "shader"})["folder"] == "shaderpacks"
    assert api.call("files:drop", {"profileId": p["id"], "path": str(z)})["folder"] == "resourcepacks"
    t = tmp_path / "a.txt"
    t.write_text("x")
    assert api.call("files:drop", {"profileId": p["id"], "path": str(t)})["ok"] is False
    assert api.call("files:drop", {"profileId": p["id"], "path": str(tmp_path / "none.jar")})["ok"] is False


def test_new_achievements_and_theme_settings(ctx, tmp_path):
    from dlauncher.core import achievements as A
    api = Api(ctx, modules=["base", "achievements"])
    assert {"builds_5", "clone", "undo", "code", "drop", "accent"} <= set(A.ORDER)
    for i in range(5):
        api.call("profiles:create", {"name": f"B{i}", "version": "1.20.1", "versionType": "release"})
    assert ctx.achievements.has("builds_5")
    assert api.call("achievements:grant", {"id": "accent"})["ok"]
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"PK")
    api.call("files:drop", {"path": str(jar)})
    assert ctx.achievements.has("drop")
    s = api.call("settings:set", {"tone": "midnight", "accent": "#5b6ee1"})
    assert s["tone"] == "midnight" and s["accent"] == "#5b6ee1"
    s = api.call("settings:set", {"tone": "pink", "accent": "javascript:1"})
    assert s["tone"] == "dark" and s["accent"] == ""
