import hashlib, io, json, os, stat, time, zipfile
from dlauncher.api import Api
from dlauncher.core import minecraft


def sha1(b): return hashlib.sha1(b).hexdigest()


def native_zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("lwjgl.dll", b"dll"); z.writestr("META-INF/x.sf", b"no")
    return b.getvalue()


def build_world(srv, version="1.20.4"):
    jar, lib, nat, asset = b"CLIENTJAR", b"LIBJAR", native_zip(), b"hello-asset"
    ah = sha1(asset)
    idx = json.dumps({"objects": {"minecraft/lang/en.json": {"hash": ah, "size": len(asset)}}}).encode()
    vj = {
        "id": version, "type": "release", "mainClass": "net.minecraft.client.main.Main",
        "assetIndex": {"id": "12", "url": srv.base + "/idx.json", "sha1": sha1(idx), "size": len(idx)},
        "downloads": {"client": {"url": srv.base + "/client.jar", "sha1": sha1(jar), "size": len(jar)}},
        "libraries": [
            {"name": "com.x:lib:1.0", "downloads": {"artifact": {"path": "com/x/lib/1.0/lib-1.0.jar", "url": srv.base + "/lib.jar", "sha1": sha1(lib), "size": len(lib)}}},
            {"name": "org.lwjgl:lwjgl:3.3:natives-windows", "rules": [{"action": "allow", "os": {"name": "windows"}}],
             "downloads": {"artifact": {"path": "org/lwjgl/lwjgl/3.3/lwjgl-3.3-natives-windows.jar", "url": srv.base + "/nat.jar", "sha1": sha1(nat), "size": len(nat)}}},
            {"name": "org.skip:me:1", "rules": [{"action": "allow", "os": {"name": "osx"}}],
             "downloads": {"artifact": {"path": "org/skip/me/1/me-1.jar", "url": srv.base + "/skip.jar", "sha1": "0" * 40, "size": 1}}},
        ],
        "arguments": {
            "jvm": ["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"],
            "game": ["--username", "${auth_player_name}", "--version", "${version_name}", "--gameDir", "${game_directory}",
                     "--assetsDir", "${assets_root}", "--assetIndex", "${assets_index_name}", "--uuid", "${auth_uuid}",
                     "--accessToken", "${auth_access_token}", "--userType", "${user_type}", "--versionType", "${version_type}"],
        },
    }
    vjb = json.dumps(vj).encode()
    srv.route("GET", "/client.jar", body=jar); srv.route("GET", "/lib.jar", body=lib)
    srv.route("GET", "/nat.jar", body=nat); srv.route("GET", "/idx.json", body=idx)
    srv.route("GET", "/skip.jar", body=b"x"); srv.route("GET", "/v.json", body=vjb)
    srv.route("GET", f"/objects/{ah[:2]}/{ah}", body=asset)
    srv.map_host("https://resources.download.minecraft.net", "/objects")
    srv.map_host("https://launchermeta.mojang.com", "")
    srv.route("GET", "/mc/game/version_manifest_v2.json", json={"latest": {"release": version}, "versions": [
        {"id": version, "type": "release", "url": srv.base + "/v.json", "sha1": sha1(vjb), "releaseTime": "x"}]})


def fake_java(tmp, windows_style=False):
    p = tmp / "java.sh"
    p.write_text('#!/bin/sh\nfor a in "$@"; do echo "ARG:$a"; done\necho "Connecting to play.test.net, 25565"\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_full_launch(ctx, srv, tmp_path, monkeypatch):
    build_world(srv)
    monkeypatch.setattr(minecraft, "current_os", lambda: {"name": "windows", "arch": "x64", "version": "10"})
    api = Api(ctx)
    ctx.settings.update(nickname="Steve", ram=2, autoBackup=False)
    r = api.call("profiles:create", {"version": "1.20.4", "name": "T"})
    pid = r["profile"]["id"]
    api.call("profiles:update", {"id": pid, "patch": {"javaPath": fake_java(tmp_path), "width": 800, "height": 600, "jvmArgs": "-Dfoo=bar"}})
    events = []
    ctx.on("*", lambda ch, p: events.append((ch, p)))
    res = api.call("game:launch", {"profileId": pid, "quickJoin": True, "server": {"host": "play.test.net", "port": 25565}})
    assert res == {"ok": True}, res
    for _ in range(100):
        if any(c == "game:closed" for c, _ in events): break
        time.sleep(0.1)
    logs = [p for c, p in events if c == "game:log"]
    args = [l.strip()[4:] for l in logs if l.startswith("ARG:")]
    assert args[0] == "-Xmx2048M" and args[1] == "-Xms1024M" and "-Dfoo=bar" in args
    i = args.index("--username"); assert args[i + 1] == "Steve"
    assert args[args.index("--uuid") + 1] == minecraft.offline_uuid("Steve")
    assert "--quickPlayMultiplayer" in args and args[args.index("--quickPlayMultiplayer") + 1] == "play.test.net:25565"
    assert args[args.index("--width") + 1] == "800"
    cp = args[args.index("-cp") + 1].split(";")
    assert any(c.endswith("lib-1.0.jar") for c in cp) and any("natives-windows" in c for c in cp)
    assert not any("skip" in c for c in cp) and cp[-1].endswith("1.20.4.jar")
    nd = args[[a for a in args].index(next(a for a in args if a.startswith("-Djava.library.path=")))].split("=", 1)[1]
    assert os.path.exists(os.path.join(nd, "lwjgl.dll")) and not os.path.exists(os.path.join(nd, "META-INF"))
    assert os.path.exists(os.path.join(ctx.root, "assets", "objects"))
    closed = next(p for c, p in events if c == "game:closed")
    assert closed == {"code": 0, "profileId": pid} and ctx.launching is False
    assert ctx.find_profile(pid)["lastServer"]["host"] == "play.test.net"
    assert ctx.find_profile(pid)["lastPlayed"]
    assert any(c == "game:progress" for c, _ in events)


def test_launch_errors(ctx, srv, tmp_path):
    api = Api(ctx)
    assert api.call("game:launch", {})["ok"] is False
    r = api.call("profiles:create", {"version": "1.20.4"})
    api.call("profiles:update", {"id": r["profile"]["id"], "patch": {"javaPath": str(tmp_path / "nojava")}})
    srv.map_host("https://launchermeta.mojang.com", "")
    srv.route("GET", "/mc/game/version_manifest_v2.json", json={"latest": {}, "versions": []})
    out = api.call("game:launch", {})
    assert out["ok"] is False and ctx.launching is False


def test_rules_and_merge():
    win = {"name": "windows", "arch": "x64", "version": "10"}
    assert minecraft.rules_allow([{"action": "allow", "os": {"name": "windows"}}], win, {})
    assert not minecraft.rules_allow([{"action": "allow", "os": {"name": "osx"}}], win, {})
    assert not minecraft.rules_allow([{"action": "allow"}, {"action": "disallow", "os": {"name": "windows"}}], win, {})
    assert minecraft.rules_allow([{"action": "allow", "features": {"has_custom_resolution": True}}], win, {"has_custom_resolution": True})
    assert minecraft.offline_uuid("Steve") == minecraft.offline_uuid("Steve")
    assert minecraft.substitute("a ${x} b ${y}", {"x": "1"}) .startswith("a 1 b")
    assert minecraft.supports_quick_play("1.20.4") and not minecraft.supports_quick_play("1.19.2")
