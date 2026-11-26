import json
import os
import urllib.parse

import pytest

from contenthelp import add_profile, hdr, mod_hosts, read
from dlauncher.api import Api
from dlauncher.core import mods


def V(id_, **o):
    d = {"id": id_, "project_id": "AAAA1111", "name": "Mod " + id_, "version_number": id_, "game_versions": ["1.21.1"],
         "loaders": ["fabric"], "version_type": "release", "date_published": "2026-01-01T00:00:00Z",
         "files": [{"primary": True, "url": f"https://cdn.modrinth.com/{id_}.jar", "filename": f"mod-{id_}.jar"}],
         "dependencies": []}
    d.update(o)
    return d


@pytest.fixture
def env(ctx, srv):
    mod_hosts(srv)
    api = Api(ctx, modules=["base", "mods"])
    return api, ctx, srv


def mods_dir(ctx, pid="p1", sub="mods"):
    return os.path.join(ctx.instance_dir(pid), sub)


# ---------- search ----------
def test_search_modrinth_mapping_and_paging(env):
    api, ctx, srv = env
    srv.route("GET", "/v2/search", json={"total_hits": 77, "hits": [
        {"project_id": "P1", "title": "Sodium", "description": "d", "icon_url": "https://cdn.modrinth.com/i.png",
         "downloads": 5, "author": "jelly", "extra": 1}]})
    r = api.call("mods:search", {"source": "modrinth", "query": "sod", "mc": "1.21.1", "loader": "fabric", "kind": "mod", "offset": 40})
    assert r == {"ok": True, "total": 77, "items": [{"id": "P1", "title": "Sodium", "description": "d",
                 "icon": "https://cdn.modrinth.com/i.png", "downloads": 5, "author": "jelly"}]}
    q = srv.log[-1]["query"]
    assert q["offset"] == "40" and q["limit"] == "40" and q["index"] == "relevance" and q["query"] == "sod"
    assert json.loads(q["facets"]) == [["project_type:mod"], ["versions:1.21.1"], ["categories:fabric"]]
    # без запроса сортировка по загрузкам; ресурспак — без фильтра по загрузчику; vanilla — тоже
    api.call("mods:search", {"source": "modrinth", "kind": "resourcepack", "mc": "1.21", "loader": "fabric"})
    q = srv.log[-1]["query"]
    assert q["index"] == "downloads" and json.loads(q["facets"]) == [["project_type:resourcepack"], ["versions:1.21"]]
    api.call("mods:search", {"source": "modrinth", "kind": "modpack"})
    assert json.loads(srv.log[-1]["query"]["facets"]) == [["project_type:modpack"]]
    api.call("mods:search", {"source": "modrinth", "loader": "vanilla"})
    assert json.loads(srv.log[-1]["query"]["facets"]) == [["project_type:mod"]]


def test_search_error_is_returned(env):
    api, ctx, srv = env
    srv.route("GET", "/v2/search", status=400, body=b"{}")
    r = api.call("mods:search", {"source": "modrinth"})
    assert r["ok"] is False and "400" in r["error"]


def test_search_curseforge_key_and_mapping(env):
    api, ctx, srv = env
    r = api.call("mods:search", {"source": "curseforge", "query": "x"})
    assert r["ok"] is False and "API-ключ" in r["error"]
    ctx.settings["curseforgeKey"] = "KEY"
    srv.route("GET", "/v1/mods/search", json={"pagination": {"totalCount": 3}, "data": [
        {"id": 5, "name": "CF Mod", "summary": "s", "logo": {"thumbnailUrl": "https://media.forgecdn.net/t.png"},
         "downloadCount": 9, "authors": [{"name": "au"}]},
        {"id": 6, "name": "No logo", "summary": "", "downloadCount": 1, "authors": []}]})
    r = api.call("mods:search", {"source": "curseforge", "query": "cf", "mc": "1.20.1", "loader": "forge", "kind": "mod", "offset": 40})
    assert r["ok"] and r["total"] == 3
    assert r["items"][0] == {"id": 5, "title": "CF Mod", "description": "s", "icon": "https://media.forgecdn.net/t.png",
                             "downloads": 9, "author": "au"}
    assert r["items"][1]["icon"] is None and r["items"][1]["author"] is None
    req = srv.log[-1]
    q = req["query"]
    assert hdr(req, "x-api-key") == "KEY"
    assert (q["classId"], q["index"], q["sortField"], q["gameVersion"], q["modLoaderType"], q["gameId"]) == ("6", "40", "2", "1.20.1", "1", "432")
    api.call("mods:search", {"source": "curseforge", "kind": "shader"})
    q = srv.log[-1]["query"]
    assert q["classId"] == "6552" and q["sortField"] == "6" and "modLoaderType" not in q and "gameVersion" not in q


# ---------- versions + fit ----------
def test_versions_fit(env):
    api, ctx, srv = env
    add_profile(ctx, "p1", loader="fabric")
    add_profile(ctx, "q", name="Q", version="1.20.1", loader="quilt")
    add_profile(ctx, "v", name="V", loader="vanilla")
    lst = [V("vNEW00001", game_versions=["1.21.3", "1.21.4"]), V("vBETA0002", version_type="beta"),
           V("vFORGE003", loaders=["forge"]), V("vREL00004"), V("vOLD00005", game_versions=["1.19.2"])]
    srv.route("GET", "/v2/project/AAAA1111/version", json=lambda r: lst)
    r = api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "kind": "mod", "profileId": "p1"})
    assert r["ok"] and r["profile"] == {"version": "1.21.1", "loader": "fabric"}
    assert [(i["id"], i["fit"]) for i in r["items"]] == [("vNEW00001", False), ("vBETA0002", True), ("vFORGE003", False), ("vREL00004", True), ("vOLD00005", False)]
    assert r["items"][0]["mc"] == "1.21.3, 1.21.4" and r["items"][1]["type"] == "beta"
    assert set(r["items"][0]) == {"id", "name", "number", "mc", "loaders", "type", "date", "fit"}
    # Quilt принимает моды Fabric; профиль 1.20.1: ничего не подходит
    r = api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "kind": "mod", "profileId": "q"})
    assert not any(i["fit"] for i in r["items"])
    lst.append(V("vQ000006", game_versions=["1.20.1"]))
    r = api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "kind": "mod", "profileId": "q"})
    assert [i["id"] for i in r["items"] if i["fit"]] == ["vQ000006"]
    lst.pop()
    # ресурспак: загрузчик не важен
    r = api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "kind": "resourcepack", "profileId": "p1"})
    assert [i["id"] for i in r["items"] if i["fit"]] == ["vBETA0002", "vFORGE003", "vREL00004"]
    assert api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "kind": "mod", "profileId": "v"})["ok"]
    # мусор
    assert not api.call("mods:versions", {"source": "modrinth", "id": "../../x", "profileId": "p1"})["ok"]
    r = api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "profileId": "нет"})
    assert not r["ok"] and "профиль" in r["error"]
    # лимит 150
    lst[:] = [V(f"v{i:05d}") for i in range(200)]
    assert len(api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1"})["items"]) == 150
    # текущий профиль по умолчанию
    assert api.call("mods:versions", {"source": "modrinth", "id": "AAAA1111"})["profile"]["version"] == "1.21.1"


def F(id_, **o):
    d = {"id": id_, "displayName": f"CF {id_}", "fileName": f"cf-{id_}.jar", "releaseType": 1,
         "fileDate": "2026-02-02T00:00:00Z", "gameVersions": ["1.21.1", "Fabric"],
         "downloadUrl": f"https://edge.forgecdn.net/{id_}.jar", "dependencies": []}
    d.update(o)
    return d


def test_curseforge_without_key_clear_error(env):
    api, ctx, srv = env
    add_profile(ctx)
    for call in (lambda: api.call("mods:versions", {"source": "curseforge", "id": 5, "profileId": "p1"}),
                 lambda: api.call("mods:install", {"source": "curseforge", "id": 5, "profileId": "p1"})):
        r = call()
        assert r["ok"] is False and "API-ключ" in r["error"]


def test_curseforge_versions_install_and_deps(env):
    api, ctx, srv = env
    add_profile(ctx)
    ctx.settings["curseforgeKey"] = "K"
    cf = [F(101, gameVersions=["1.20.1", "Forge"]), F(102), F(103, releaseType=2, gameVersions=["1.21.1", "Quilt", "Fabric"]),
          F(104, gameVersions=["1.21.1", "Forge"], releaseType=3), F(105, dependencies=[{"modId": 9, "relationType": 3}, {"modId": 8, "relationType": 2}])]
    srv.route("GET", "/v1/mods/5/files", json=lambda r: {"data": cf})
    for f in cf:
        srv.route("GET", f"/v1/mods/5/files/{f['id']}", json={"data": f})
        srv.route("GET", f"/forge/{f['id']}.jar", body=f"cf:{f['id']}".encode())
    srv.route("GET", "/v1/mods/9/files", json={"data": [F(900, fileName="dep9.jar", downloadUrl="https://edge.forgecdn.net/900.jar")]})
    srv.route("GET", "/forge/900.jar", body=b"dep9")
    r = api.call("mods:versions", {"source": "curseforge", "id": 5, "profileId": "p1"})
    assert r["ok"], r
    assert [(i["id"], i["fit"], i["type"]) for i in r["items"]] == [
        ("101", False, "release"), ("102", True, "release"), ("103", True, "beta"), ("104", False, "alpha"), ("105", True, "release")]
    assert r["items"][2]["loaders"] == ["quilt", "fabric"]
    r = api.call("mods:install", {"source": "curseforge", "id": 5, "profileId": "p1", "versionId": "103"})
    assert r == {"ok": True, "filename": "cf-103.jar", "extra": 0}
    assert read(os.path.join(mods_dir(ctx), "cf-103.jar")) == b"cf:103"
    r = api.call("mods:install", {"source": "curseforge", "id": 5, "profileId": "p1", "versionId": "105"})
    assert r["ok"] and r["extra"] == 1 and read(os.path.join(mods_dir(ctx), "dep9.jar")) == b"dep9"
    assert not api.call("mods:install", {"source": "curseforge", "id": 5, "profileId": "p1", "versionId": "9999"})["ok"]
    r = api.call("mods:install", {"source": "curseforge", "id": 5, "profileId": "p1", "versionId": "abc"})
    assert not r["ok"] and "Неверная версия" in r["error"]
    # без versionId: последний релиз под игру и загрузчик
    srv.route("GET", "/v1/mods/7/files", json={"data": [F(701, releaseType=2, fileName="beta.jar"), F(702, fileName="rel.jar")]})
    srv.route("GET", "/forge/702.jar", body=b"r")
    r = api.call("mods:install", {"source": "curseforge", "id": 7, "profileId": "p1"})
    assert r["ok"] and r["filename"] == "rel.jar"
    q = [x for x in srv.log if x["path"] == "/v1/mods/7/files"][-1]["query"]
    assert q["gameVersion"] == "1.21.1" and q["modLoaderType"] == "4"
    # ресурспак: без загрузчика; нет файла -> ошибка
    srv.route("GET", "/v1/mods/8/files", json={"data": []})
    r = api.call("mods:install", {"source": "curseforge", "id": 8, "profileId": "p1", "kind": "resourcepack"})
    assert not r["ok"] and "Нет файла" in r["error"]
    assert "modLoaderType" not in [x for x in srv.log if x["path"] == "/v1/mods/8/files"][-1]["query"]


# ---------- install ----------
def test_install_pinned_dependencies_and_rejections(env):
    api, ctx, srv = env
    add_profile(ctx)
    add_profile(ctx, "v", name="V", loader="vanilla")
    lst = {v["id"]: v for v in [V("vBETA0002", version_type="beta"),
                                V("vREL00004", dependencies=[{"dependency_type": "required", "project_id": "DEPP2222"},
                                                             {"dependency_type": "optional", "project_id": "OPTT3333"},
                                                             {"dependency_type": "required", "project_id": "GONE4444"}])]}
    for vid, v in lst.items():
        srv.route("GET", f"/v2/version/{vid}", json=v)
        srv.route("GET", f"/cdn/{vid}.jar", body=f"jar:{vid}".encode())
    srv.route("GET", "/v2/project/AAAA1111/version", json=lambda r: [lst["vBETA0002"], lst["vREL00004"]])
    srv.route("GET", "/v2/project/DEPP2222/version", json=[V("depver001", project_id="DEPP2222", files=[
        {"primary": True, "url": "https://cdn.modrinth.com/dep.jar", "filename": "dep-lib.jar"}])])
    srv.route("GET", "/cdn/dep.jar", body=b"dep")
    srv.route("GET", "/v2/project/GONE4444/version", json=[])
    d = mods_dir(ctx)
    r = api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1", "versionId": "vBETA0002"})
    assert r == {"ok": True, "filename": "mod-vBETA0002.jar", "extra": 0}
    assert read(os.path.join(d, "mod-vBETA0002.jar")) == b"jar:vBETA0002"   # выбранная версия, даже бета
    r = api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1", "versionId": "vREL00004"})
    assert r["ok"] and r["filename"] == "mod-vREL00004.jar" and r["extra"] == 1   # опциональная и пропавшая зависимости пропущены
    assert read(os.path.join(d, "dep-lib.jar")) == b"dep"
    assert not os.path.exists(os.path.join(d, "mod-vBETA0002.jar.part"))
    # чужой проект / мусор / несуществующая версия
    r = api.call("mods:install", {"source": "modrinth", "id": "OTHER999", "profileId": "p1", "versionId": "vBETA0002"})
    assert not r["ok"] and "не относится" in r["error"]
    r = api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1", "versionId": "../etc/passwd"})
    assert not r["ok"] and "Неверная версия" in r["error"]
    assert not api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1", "versionId": "nonexist"})["ok"]
    # без versionId — последний релиз среди совместимых
    os.remove(os.path.join(d, "mod-vREL00004.jar"))
    r = api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "p1"})
    assert r["ok"] and r["filename"] == "mod-vREL00004.jar"
    q = [x for x in srv.log if x["path"] == "/v2/project/AAAA1111/version"][-1]["query"]
    assert json.loads(q["game_versions"]) == ["1.21.1"] and json.loads(q["loaders"]) == ["fabric"]
    # vanilla и нет профиля
    r = api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "v"})
    assert not r["ok"] and "Vanilla" in r["error"]
    assert not api.call("mods:install", {"source": "modrinth", "id": "AAAA1111", "profileId": "zzz"})["ok"]


def test_install_kinds_and_quilt_loaders_and_safe_filename(env):
    api, ctx, srv = env
    add_profile(ctx, "q", name="Q", loader="quilt")
    srv.route("GET", "/v2/project/RP000001/version", json=[V("rpv", project_id="RP000001", files=[
        {"primary": True, "url": "https://cdn.modrinth.com/rp.zip", "filename": "pack.zip"}])])
    srv.route("GET", "/cdn/rp.zip", body=b"zip")
    r = api.call("mods:install", {"source": "modrinth", "id": "RP000001", "kind": "resourcepack", "profileId": "q"})
    assert r["ok"] and os.path.isfile(os.path.join(mods_dir(ctx, "q", "resourcepacks"), "pack.zip"))
    assert "loaders" not in [x for x in srv.log if x["path"].endswith("RP000001/version")][-1]["query"]
    r = api.call("mods:install", {"source": "modrinth", "id": "RP000001", "kind": "shader", "profileId": "q"})
    assert r["ok"] and os.path.isfile(os.path.join(mods_dir(ctx, "q", "shaderpacks"), "pack.zip"))
    srv.route("GET", "/v2/project/MODQ0001/version", json=[V("m", project_id="MODQ0001")])
    srv.route("GET", "/cdn/m.jar", body=b"m")
    assert api.call("mods:install", {"source": "modrinth", "id": "MODQ0001", "profileId": "q"})["ok"]
    assert json.loads([x for x in srv.log if x["path"].endswith("MODQ0001/version")][-1]["query"]["loaders"]) == ["quilt", "fabric"]
    # имя файла из ответа сервера не может выйти из папки
    srv.route("GET", "/v2/project/EVIL0001/version", json=[V("e", project_id="EVIL0001", files=[
        {"primary": True, "url": "https://cdn.modrinth.com/m.jar", "filename": "../../../evil.jar"}])])
    r = api.call("mods:install", {"source": "modrinth", "id": "EVIL0001", "profileId": "q"})
    assert r["ok"] and r["filename"] == "evil.jar"
    assert not os.path.exists(os.path.join(ctx.root, "evil.jar")) and os.path.isfile(os.path.join(mods_dir(ctx, "q"), "evil.jar"))


def test_helpers():
    assert mods.ok_project_id("AAAA1111") and mods.ok_project_id("a_b-c") and not mods.ok_project_id("../x") and not mods.ok_project_id(5)
    assert not mods.ok_project_id("") and not mods.ok_project_id("a" * 65)
    assert mods.ok_cf_number(5) and mods.ok_cf_number("12") and not mods.ok_cf_number("abc") and not mods.ok_cf_number(0)
    assert not mods.ok_cf_number(1.5) and not mods.ok_cf_number("-3") and not mods.ok_cf_number(1e10)
    assert mods.mc_summary(["1.21"]) == "1.21" and mods.mc_summary(list("abcd")) == "a … d"


# ---------- icons ----------
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


def test_icon_cache_hosts_and_fallback(env):
    api, ctx, srv = env
    srv.route("GET", "/cdn/i.png", body=PNG, ctype="image/png")
    p = api.call("icon:get", "https://cdn.modrinth.com/i.png")
    assert p and p.startswith(os.path.join(ctx.user_data, "icon-cache")) and p.endswith(".png") and read(p) == PNG
    n = len(srv.log)
    assert api.call("icon:get", "https://cdn.modrinth.com/i.png") == p and len(srv.log) == n   # из кэша
    # чужие хосты, http, мусор
    for bad in ("https://evil.com/i.png", "http://cdn.modrinth.com/i.png", "https://modrinth.com.evil.com/i.png",
                "file:///etc/passwd", "nonsense", None, 5):
        assert api.call("icon:get", bad) is None
    assert len(srv.log) == n
    # прямой путь недоступен -> wsrv.nl
    srv.route("GET", "/cdn/gone.jpg", status=404, body=b"x")
    srv.route("GET", "/wsrv/", body=b"JPEG", ctype="image/jpeg")
    p2 = api.call("icon:get", "https://cdn.modrinth.com/gone.jpg")
    assert p2 and p2.endswith(".jpg") and read(p2) == b"JPEG"
    w = [x for x in srv.log if x["path"] == "/wsrv/"][-1]["query"]
    assert w["url"] == "https://cdn.modrinth.com/gone.jpg" and w["w"] == "128"
    # не картинка / слишком большая -> None и ничего не кэшируется
    srv.route("GET", "/cdn/html.png", body=b"<html>", ctype="text/html")
    srv.route("GET", "/cdn/big.png", body=b"0" * (2 * 1024 * 1024 + 1), ctype="image/png")
    srv.routes.pop(("GET", "/wsrv/"))
    assert api.call("icon:get", "https://cdn.modrinth.com/html.png") is None
    assert api.call("icon:get", "https://cdn.modrinth.com/big.png") is None
    assert not [f for f in os.listdir(os.path.join(ctx.user_data, "icon-cache")) if f.endswith(".part")]
    assert len(os.listdir(os.path.join(ctx.user_data, "icon-cache"))) == 2


# ---------- optimization ----------
def test_opt_list(env):
    api, ctx, srv = env
    fab = api.call("opt:list", "fabric")
    assert fab[0] == {"slug": "sodium", "name": "Sodium", "desc": "Новый движок отрисовки — главный буст FPS"} and len(fab) == 13
    assert api.call("opt:list", "quilt") == fab
    assert any(m["slug"] == "embeddium" for m in api.call("opt:list", "neoforge")) and len(api.call("opt:list", "forge")) == 8
    assert api.call("opt:list", "vanilla") == [] and api.call("opt:list", None) == []


def test_opt_install_vanilla_and_noprofile(env):
    api, ctx, srv = env
    assert not api.call("opt:install", {})["ok"]
    add_profile(ctx, "v", name="V", loader="vanilla")
    r = api.call("opt:install", {"profileId": "v"})
    assert not r["ok"] and "Vanilla" in r["error"]


def test_opt_install_modrinth_skip_fail_and_progress(env):
    api, ctx, srv = env
    add_profile(ctx)
    events = []
    ctx.on("opt:progress", events.append)
    slugs = [m["slug"] for m in api.call("opt:list", "fabric")]
    for s in slugs:
        srv.route("GET", f"/v2/project/{s}/version", json=[])             # нет версии -> skip
    srv.route("GET", "/v2/project/sodium/version", json=[V("s1", project_id="S", dependencies=[
        {"dependency_type": "required", "project_id": "lithium"}], files=[{"primary": True, "url": "https://cdn.modrinth.com/s.jar", "filename": "sodium.jar"}])])
    srv.route("GET", "/cdn/s.jar", body=b"s")
    srv.route("GET", "/v2/project/lithium/version", json=[V("l1", project_id="L", files=[{"primary": True, "url": "https://cdn.modrinth.com/l.jar", "filename": "lithium.jar"}])])
    srv.route("GET", "/cdn/l.jar", body=b"l")
    srv.route("GET", "/v2/project/krypton/version", status=400, body=b"{}")    # настоящая ошибка -> fail
    r = api.call("opt:install", {})
    # lithium поставился как зависимость sodium -> позже «уже есть» (seen), но считается установленным
    assert r["ok"] and r["installed"] == 2 and r["failed"] == 1 and r["skipped"] == 10 and r["needKey"] == 10 + 1
    assert r["bySource"] == {"modrinth": 2, "curseforge": 0}
    d = mods_dir(ctx)
    assert read(os.path.join(d, "sodium.jar")) == b"s" and read(os.path.join(d, "lithium.jar")) == b"l"
    by = {}
    for e in events:
        by.setdefault(e["slug"], []).append(e)
    assert [e["status"] for e in by["sodium"]] == ["loading", "ok"] and by["sodium"][1] == {"slug": "sodium", "status": "ok", "detail": "sodium.jar", "source": "Modrinth"}
    assert by["krypton"][1]["status"] == "fail" and "400" in by["krypton"][1]["detail"]
    assert by["noisium"][1] == {"slug": "noisium", "status": "skip", "detail": "Нет версии для 1.21.1"}
    assert len(events) == 2 * len(slugs)


def test_opt_install_curseforge_fallback(env):
    api, ctx, srv = env
    add_profile(ctx, "f", name="F", version="1.20.1", loader="forge", loader_version="47.2.0")
    ctx.settings["curseforgeKey"] = "KEY"
    for m in api.call("opt:list", "forge"):
        srv.route("GET", f"/v2/project/{m['slug']}/version", json=[])
    srv.route("GET", "/v2/project/ferrite-core/version", json=[V("fc", project_id="FC", game_versions=["1.20.1"], loaders=["forge"], files=[
        {"primary": True, "url": "https://cdn.modrinth.com/fc.jar", "filename": "ferrite.jar"}])])
    srv.route("GET", "/cdn/fc.jar", body=b"fc")
    # CurseForge знает только Embeddium (точное совпадение по названию); «ModernFix» — чужой мод с похожим именем
    def search(req):
        name = req["query"]["searchFilter"]
        if name == "Embeddium":
            return {"data": [{"id": 1, "name": "Embeddium Extra", "slug": "x"}, {"id": 2, "name": "Embeddium", "slug": "embeddium"}]}
        if name == "ModernFix":
            return {"data": [{"id": 3, "name": "ModernFix Tweaks", "slug": "mf2"}]}
        return {"data": []}
    srv.route("GET", "/v1/mods/search", json=search)
    srv.route("GET", "/v1/mods/2/files", json={"data": [F(20, fileName="embeddium-cf.jar", gameVersions=["1.20.1", "Forge"],
                                                     downloadUrl="https://edge.forgecdn.net/20.jar")]})
    srv.route("GET", "/forge/20.jar", body=b"emb")
    r = api.call("opt:install", {"profileId": "f"})
    assert r["ok"] and r["installed"] == 2 and r["bySource"] == {"modrinth": 1, "curseforge": 1} and r["needKey"] == 0
    assert r["failed"] == 0 and r["skipped"] == 6
    assert read(os.path.join(mods_dir(ctx, "f"), "embeddium-cf.jar")) == b"emb"
    s = [x for x in srv.log if x["path"] == "/v1/mods/search"][0]
    assert hdr(s, "x-api-key") == "KEY" and s["query"]["modLoaderType"] == "1" and s["query"]["gameVersion"] == "1.20.1"
