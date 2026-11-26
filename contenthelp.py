"""Общие помощники для тестов контента (моды, сборки, профили)."""
import hashlib
import io
import json
import os
import zipfile


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def add_profile(ctx, pid="p1", name="Fab", version="1.21.1", loader="fabric", loader_version="0.16.5", **extra):
    p = {"id": pid, "name": name, "version": version, "versionType": "release", "loader": loader,
         "loaderVersion": loader_version if loader != "vanilla" else "", "pack": None}
    p.update(extra)
    ctx.settings["profiles"].append(p)
    if not ctx.settings.get("currentProfile"):
        ctx.settings["currentProfile"] = pid
    ctx.ensure_instance(pid)
    return p


def make_zip(files: dict, path: str | None = None) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data if isinstance(data, (bytes, bytearray)) else str(data))
    raw = bio.getvalue()
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(raw)
    return raw


def mock_manifest(srv):
    srv.map_host("https://launchermeta.mojang.com", "")
    srv.route("GET", "/mc/game/version_manifest_v2.json", json={
        "latest": {"release": "1.21.1"},
        "versions": [{"id": v, "type": "release", "releaseTime": "x"} for v in ("1.21.1", "1.20.1", "1.21")]})


def mod_hosts(srv):
    srv.map_host("https://api.modrinth.com", "")
    srv.map_host("https://cdn.modrinth.com", "/cdn")
    srv.map_host("https://api.curseforge.com", "")
    srv.map_host("https://edge.forgecdn.net", "/forge")
    srv.map_host("https://wsrv.nl", "/wsrv")


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def hdr(req, name):
    low = name.lower()
    return next((v for k, v in req["headers"].items() if k.lower() == low), None)
