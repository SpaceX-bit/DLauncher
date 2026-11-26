"""Загрузчики модов: список версий (`loaders:list`) и подготовка Fabric / Quilt / Forge / NeoForge к запуску.

Порт loaders:list и ensureNeoForge из main.js; Forge ставится так же установщиком (--installClient).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import util

FABRIC_META = "https://meta.fabricmc.net/v2/versions/loader"
QUILT_META = "https://meta.quiltmc.org/v3/versions/loader"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEO_META = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
NEO_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

_neo_cache: list[str] | None = None
_neo_lock = threading.Lock()


# ---------------------------------------------------------------- список версий

def neoforge_versions(mc: str) -> list[str]:
    global _neo_cache
    m = re.match(r"^1\.(\d+)(?:\.(\d+))?$", mc or "")
    if not m:
        return []
    major, minor = int(m.group(1)), int(m.group(2) or 0)
    if major < 20 or (major == 20 and minor < 2):
        return []  # NeoForge начинается с 1.20.2
    with _neo_lock:
        if _neo_cache is None:
            xml = util.get_text(NEO_META)
            _neo_cache = re.findall(r"<version>([^<]+)</version>", xml)
    prefix = f"{major}.{minor}."

    def nums(v: str) -> list[int]:
        return [int(x) if x.isdigit() else 0 for x in re.sub(r"-.*", "", v).split(".")]

    def key(v: str):
        n = nums(v)
        return [-(x) for x in n] + [0] * (8 - len(n))

    allv = sorted((v for v in _neo_cache if v.startswith(prefix)), key=key)
    return [v for v in allv if "-" not in v] + [v for v in allv if "-" in v]


def list_loaders(mc: str) -> list[dict]:
    result = [{"loader": "vanilla", "versions": ["—"]}]
    q = urllib.parse.quote(str(mc), safe="")

    def safe(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_fabric = ex.submit(safe, lambda: util.get_json(f"{FABRIC_META}/{q}"))
        f_quilt = ex.submit(safe, lambda: util.get_json(f"{QUILT_META}/{q}"))
        f_forge = ex.submit(safe, lambda: util.get_json(FORGE_PROMOS))
        f_neo = ex.submit(safe, lambda: neoforge_versions(mc))
        fabric, quilt, forge, neo = f_fabric.result(), f_quilt.result(), f_forge.result(), f_neo.result()

    def metas(v):
        return [x["loader"]["version"] for x in v if isinstance(x, dict) and x.get("loader")]

    if isinstance(fabric, list) and fabric:
        result.append({"loader": "fabric", "versions": metas(fabric)})
    if isinstance(quilt, list) and quilt:
        result.append({"loader": "quilt", "versions": metas(quilt)})
    if isinstance(forge, dict):
        promos = forge.get("promos") or {}
        lst = []
        if promos.get(f"{mc}-recommended"):
            lst.append(promos[f"{mc}-recommended"])
        if promos.get(f"{mc}-latest") and promos[f"{mc}-latest"] not in lst:
            lst.append(promos[f"{mc}-latest"])
        if lst:
            result.append({"loader": "forge", "versions": lst})
    if neo:
        result.append({"loader": "neoforge", "versions": neo})
    return result


# ---------------------------------------------------------------- подготовка

Status = Callable[[str], None]


def _status(ctx, text: str) -> None:
    ctx.send("game:status", text)


def _has_version(root: str, vid: str) -> bool:
    return os.path.isfile(os.path.join(root, "versions", vid, vid + ".json"))


def prepare_fabric(ctx, loader: str, mc: str, loader_version: str) -> str:
    """Fabric/Quilt: профиль с мета-сервера -> versions/<id>/<id>.json. Установленный профиль переиспользуется."""
    if not loader_version:
        raise ValueError("Не выбрана версия загрузчика")
    root = ctx.root
    expected = f"{loader}-loader-{loader_version}-{mc}"
    if _has_version(root, expected):
        return expected
    _status(ctx, f"Подготовка {loader}...")
    base = FABRIC_META if loader == "fabric" else QUILT_META
    prof = util.get_json("/".join([base, urllib.parse.quote(mc, safe=""), urllib.parse.quote(loader_version, safe=""),
                                   "profile", "json"]))
    vid = prof.get("id")
    if not vid:
        raise RuntimeError(f"Мета-сервер {loader} вернул профиль без id")
    util.write_json(os.path.join(root, "versions", vid, vid + ".json"), prof, indent=None)
    return vid


def _ensure_launcher_profiles(root: str) -> None:
    lp = os.path.join(root, "launcher_profiles.json")  # установщик требует этот файл
    if not os.path.exists(lp):
        os.makedirs(root, exist_ok=True)
        with open(lp, "w", encoding="utf-8") as f:
            json.dump({"profiles": {}, "version": 3}, f)


def run_installer(ctx, java: str, jar: str, root: str, label: str) -> None:
    p = subprocess.Popen([java, "-jar", jar, "--installClient", root], cwd=root, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, creationflags=util.NO_WINDOW)
    tail = ""
    assert p.stdout is not None
    for raw in iter(p.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if line:
            tail = (tail + "\n" + line)[-2000:]
            _status(ctx, f"{label}: {line[:80]}")
    code = p.wait()
    if code != 0:
        last = " ".join(tail.strip().splitlines()[-3:])
        raise RuntimeError(f"Установщик {label} завершился с ошибкой ({code}). {last}")


def _find_installed(root: str, prefix: str, loader_version: str) -> str | None:
    vdir = os.path.join(root, "versions")
    try:
        names = sorted(os.listdir(vdir))
    except OSError:
        return None
    for d in names:
        low = d.lower()
        if low.startswith(prefix) and loader_version in d and _has_version(root, d):
            return d
    return None


def ensure_neoforge(ctx, loader_version: str, java: str) -> str:
    if not loader_version:
        raise ValueError("Не выбрана версия загрузчика")
    root = ctx.root
    exact = f"neoforge-{loader_version}"
    if _has_version(root, exact):
        return exact
    ready = _find_installed(root, "neoforge-", loader_version)
    if ready:
        return ready
    jar = os.path.join(root, "neoforge", f"neoforge-{loader_version}-installer.jar")
    if not os.path.exists(jar):
        _status(ctx, "Скачивание NeoForge...")
        util.download(f"{NEO_MAVEN}/{loader_version}/neoforge-{loader_version}-installer.jar", jar)
    _ensure_launcher_profiles(root)
    _status(ctx, "Установка NeoForge (это займёт несколько минут)...")
    run_installer(ctx, java, jar, root, "NeoForge")
    vid = _find_installed(root, "neoforge-", loader_version)
    if not vid:
        raise RuntimeError("NeoForge установлен, но версия не найдена в папке versions.")
    return vid


def forge_supported(mc: str) -> bool:
    m = re.match(r"^1\.(\d+)(?:\.(\d+))?", mc or "")
    if not m:
        return True
    minor, patch = int(m.group(1)), int(m.group(2) or 0)
    return minor > 12 or (minor == 12 and patch >= 2)


def _find_forge(root: str, mc: str, loader_version: str) -> str | None:
    try:
        for d in sorted(os.listdir(os.path.join(root, "versions"))):
            if d.startswith(mc) and "forge" in d.lower() and loader_version in d and _has_version(root, d):
                return d
    except OSError:
        pass
    return None


def ensure_forge(ctx, mc: str, loader_version: str, java: str) -> str:
    """Forge 1.12.2+ через официальный установщик (--installClient). Установленная версия переиспользуется."""
    if not loader_version:
        raise ValueError("Не выбрана версия загрузчика")
    if not forge_supported(mc):
        raise RuntimeError(f"Forge для Minecraft {mc} не поддерживается лаунчером: нужна версия 1.12.2 или новее. "
                           "Выбери Fabric или более новую версию игры.")
    root = ctx.root
    ready = _find_forge(root, mc, loader_version)
    if ready:
        return ready
    full = f"{mc}-{loader_version}"
    jar = os.path.join(root, "forge", f"forge-{full}-installer.jar")
    if not os.path.exists(jar):
        _status(ctx, "Скачивание Forge...")
        util.download(f"{FORGE_MAVEN}/{full}/forge-{full}-installer.jar", jar)
    _ensure_launcher_profiles(root)
    _status(ctx, "Установка Forge (это займёт несколько минут)...")
    run_installer(ctx, java, jar, root, "Forge")
    vid = _find_forge(root, mc, loader_version)
    if not vid:
        raise RuntimeError("Forge установлен, но версия не найдена в папке versions.")
    return vid


def prepare_loader(ctx, loader: str, mc: str, loader_version: str, java: str) -> str | None:
    """-> id версии для запуска (None для vanilla)."""
    if loader in ("fabric", "quilt"):
        return prepare_fabric(ctx, loader, mc, loader_version)
    if loader == "forge":
        return ensure_forge(ctx, mc, loader_version, java)
    if loader == "neoforge":
        return ensure_neoforge(ctx, loader_version, java)
    return None


def handlers(ctx):
    def loaders_list(mc=None):
        return list_loaders(mc)

    return {"loaders:list": loaders_list}
