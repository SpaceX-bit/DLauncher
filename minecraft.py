"""Собственный движок запуска Minecraft (замена minecraft-launcher-core).

Только стандартная библиотека. Игру не меняем: скачиваем официальные файлы, собираем командную строку
по version.json так же, как это делает официальный лаунчер.

Основное:
  rules_allow(rules, os_info, features)   — вычисление `rules` (os name/arch/version, features)
  maven_path(name)                        — путь библиотеки по maven-координатам
  merge_versions(child, parent)           — слияние inheritsFrom (Fabric/Quilt/Forge/NeoForge)
  substitute(text, vars)                  — подстановка ${var}
  offline_uuid(name)                      — UUID как у офлайн-режима Mojang (md5 "OfflinePlayer:<name>")
  Engine                                  — resolve / prepare (скачивание) / command (сборка аргументов)
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import threading
import uuid
import zipfile
from typing import Any, Callable

from . import util

LIB_BASE = "https://libraries.minecraft.net/"
ASSET_BASE = "https://resources.download.minecraft.net/"
LAUNCHER_NAME = "DLauncher"
CP_SEP_WIN = ";"


# ---------------------------------------------------------------- система и правила

def current_os() -> dict:
    """{name: windows|linux|osx, arch: x86|x86_64|arm64, version}."""
    if sys.platform == "win32":
        name = "windows"
    elif sys.platform == "darwin":
        name = "osx"
    else:
        name = "linux"
    m = (platform.machine() or "").lower()
    if m in ("arm64", "aarch64"):
        arch = "arm64"
    elif m in ("x86", "i386", "i686") or (m == "" and sys.maxsize <= 2 ** 32):
        arch = "x86"
    else:
        arch = "x86_64"
    return {"name": name, "arch": arch, "version": platform.version() if name != "windows" else (platform.version() or "10.0")}


def _rule_applies(rule: dict, os_info: dict, features: dict) -> bool:
    o = rule.get("os")
    if o:
        if o.get("name") and o["name"] != os_info["name"]:
            return False
        if o.get("arch") and o["arch"] != os_info["arch"]:
            return False
        if o.get("version"):
            try:
                if not re.search(o["version"], str(os_info.get("version") or "")):
                    return False
            except re.error:
                return False
    f = rule.get("features")
    if f:
        for k, v in f.items():
            if bool(features.get(k, False)) != bool(v):
                return False
    return True


def rules_allow(rules: list | None, os_info: dict | None = None, features: dict | None = None) -> bool:
    """Нет правил — разрешено. Иначе по умолчанию запрещено; последнее подошедшее правило решает."""
    if not rules:
        return True
    os_info = os_info or current_os()
    features = features or {}
    allowed = False
    for r in rules:
        if _rule_applies(r, os_info, features):
            allowed = r.get("action", "allow") == "allow"
    return allowed


# ---------------------------------------------------------------- координаты, слияние

def maven_path(name: str) -> str:
    """group:artifact:version[:classifier][@ext] -> group/path/artifact/version/artifact-version[-classifier].ext"""
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    if len(parts) < 3:
        raise ValueError(f"Неверное имя библиотеки: {name}")
    group, art, ver = parts[0], parts[1], parts[2]
    cls = parts[3] if len(parts) > 3 else ""
    fn = f"{art}-{ver}" + (f"-{cls}" if cls else "") + f".{ext}"
    return f"{group.replace('.', '/')}/{art}/{ver}/{fn}"


def lib_key(name: str) -> str:
    """Ключ без версии: group:artifact[:classifier] — для замены библиотек при слиянии."""
    base = name.split("@", 1)[0].split(":")
    key = ":".join(base[:2])
    if len(base) > 3:
        key += ":" + base[3]
    return key


def _split_args(s: str) -> list[str]:
    return str(s or "").split()


def _norm_args(v: dict):
    """-> (jvm|None, game, legacy)"""
    if isinstance(v.get("arguments"), dict):
        a = v["arguments"]
        return list(a.get("jvm") or []), list(a.get("game") or []), False
    if v.get("minecraftArguments"):
        return None, _split_args(v["minecraftArguments"]), True
    return None, [], False


LEGACY_JVM = ["-Djava.library.path=${natives_directory}", "-Dminecraft.launcher.brand=${launcher_name}",
              "-Dminecraft.launcher.version=${launcher_version}", "-cp", "${classpath}"]


def merge_versions(child: dict, parent: dict) -> dict:
    """Слияние профиля загрузчика (child, inheritsFrom) с родительской версией."""
    out = dict(parent)
    for k, v in child.items():
        if k in ("libraries", "arguments", "minecraftArguments", "inheritsFrom"):
            continue
        out[k] = v
    seen, libs = set(), []
    for lib in list(child.get("libraries") or []) + list(parent.get("libraries") or []):
        if not isinstance(lib, dict) or not lib.get("name"):
            continue
        key = lib_key(lib["name"])
        # у разных ОС одна и та же библиотека бывает несколько раз (с правилами) — различаем по правилам
        k2 = (key, json.dumps(lib.get("rules"), sort_keys=True) if lib.get("rules") else "")
        if k2 in seen:
            continue
        seen.add(k2)
        libs.append(lib)
    out["libraries"] = libs
    pj, pg, _ = _norm_args(parent)
    cj, cg, clegacy = _norm_args(child)
    jvm = (pj or []) + (cj or [])
    game = cg if clegacy else pg + cg
    out["arguments"] = {"jvm": jvm, "game": game}
    out.pop("minecraftArguments", None)
    if child.get("jar"):
        out["jar"] = child["jar"]
    return out


def substitute(text: str, variables: dict) -> str:
    return re.sub(r"\$\{([^}]+)\}", lambda m: str(variables[m.group(1)]) if m.group(1) in variables else m.group(0), str(text))


def offline_uuid(name: str) -> str:
    """Как у Mojang: UUID.nameUUIDFromBytes("OfflinePlayer:<name>") (md5, версия 3)."""
    b = bytearray(hashlib.md5(("OfflinePlayer:" + str(name)).encode("utf-8")).digest())
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def offline_auth(name: str) -> dict:
    name = (name or "Player").strip() or "Player"
    return {"name": name, "uuid": offline_uuid(name), "access_token": "0", "user_type": "legacy",
            "client_token": None, "user_properties": "{}"}


def supports_quick_play(v: str) -> bool:
    m = re.match(r"^1\.(\d+)", v)
    if m:
        return int(m.group(1)) >= 20
    m = re.match(r"^(\d\d)w(\d\d)", v)
    if m:
        return int(m.group(1)) > 23 or (int(m.group(1)) == 23 and int(m.group(2)) >= 14)
    # новая схема версий (26.1 и т.п.): год.номер — после 1.21
    m = re.match(r"^(\d{2})\.\d+", v)
    return bool(m and int(m.group(1)) >= 25)


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- движок

class Engine:
    def __init__(self, root: str, manifest: Callable[[], dict] | None = None,
                 progress: Callable[[dict], None] | None = None,
                 status: Callable[[str], None] | None = None,
                 debug: Callable[[str], None] | None = None,
                 os_info: dict | None = None, launcher_version: str = "1.0", threads: int = 8):
        self.root = os.path.abspath(root)
        self.manifest = manifest
        self.progress = progress or (lambda p: None)
        self.status = status or (lambda s: None)
        self.debug = debug or (lambda s: None)
        self.os = os_info or current_os()
        self.launcher_version = launcher_version
        self.threads = threads
        self._lock = threading.Lock()

    # ----- пути
    def vdir(self, vid: str) -> str:
        return os.path.join(self.root, "versions", vid)

    def vfile(self, vid: str) -> str:
        return os.path.join(self.vdir(vid), vid + ".json")

    @property
    def libs_dir(self) -> str:
        return os.path.join(self.root, "libraries")

    @property
    def assets_dir(self) -> str:
        return os.path.join(self.root, "assets")

    @property
    def sep(self) -> str:
        return CP_SEP_WIN if self.os["name"] == "windows" else ":"

    # ----- version.json
    def _fetch_vanilla_json(self, vid: str) -> dict:
        m = self.manifest() if self.manifest else None
        entry = next((v for v in (m or {}).get("versions", []) if v.get("id") == vid), None)
        if not entry:
            raise RuntimeError(f"Версия {vid} не найдена в списке Mojang")
        self.debug(f"Downloading version json {vid}")
        self._download(entry["url"], self.vfile(vid), entry.get("sha1"))
        return util.read_json(self.vfile(vid))

    def resolve(self, vid: str, _depth: int = 0) -> dict:
        """Полный version.json (с inheritsFrom). Недостающий ванильный json скачивается."""
        if _depth > 5:
            raise RuntimeError(f"Слишком глубокая цепочка inheritsFrom: {vid}")
        data = util.read_json(self.vfile(vid), None) if os.path.isfile(self.vfile(vid)) else None
        if not isinstance(data, dict):
            data = self._fetch_vanilla_json(vid)
        parent_id = data.get("inheritsFrom")
        if parent_id:
            merged = merge_versions(data, self.resolve(parent_id, _depth + 1))
            merged["_jar_id"] = data.get("jar") or merged.get("_jar_id") or parent_id
        else:
            merged = dict(data)
            merged["libraries"] = list(data.get("libraries") or [])
            j, g, _ = _norm_args(data)
            merged["arguments"] = {"jvm": j or [], "game": g}
            merged.pop("minecraftArguments", None)
            merged["_jar_id"] = data.get("jar") or data.get("id") or vid
        merged["id"] = data.get("id") or vid
        return merged

    # ----- скачивание
    @staticmethod
    def _valid(path: str, sha1: str | None, size: int | None = None) -> bool:
        try:
            if not os.path.isfile(path):
                return False
            sz = os.path.getsize(path)
            if sz == 0:
                return False
            if size and sz != size:
                return False
            if sha1 and util.sha1_file(path).lower() != sha1.lower():
                return False
            return True
        except OSError:
            return False

    def _download(self, url: str, dest: str, sha1: str | None = None, size: int | None = None) -> None:
        if self._valid(dest, sha1, size):
            return
        last = None
        for _ in range(2):
            util.download(url, dest)
            if not sha1 or util.sha1_file(dest).lower() == sha1.lower():
                return
            last = RuntimeError(f"Контрольная сумма не совпала: {os.path.basename(dest)}")
            try:
                os.remove(dest)
            except OSError:
                pass
        raise last  # type: ignore[misc]

    def _run_jobs(self, jobs: list[dict], kind: str, label: str) -> None:
        """jobs: {url, dest, sha1, size}; параллельно, прогресс game:progress."""
        todo = [j for j in jobs if not self._valid(j["dest"], j.get("sha1"), j.get("size") if j.get("check_size", True) else None)]
        total = len(todo)
        if not total:
            return
        done = [0]
        step = max(1, total // 100)

        def work(j, _i):
            if not j.get("url"):
                raise RuntimeError(f"Нет файла и ссылки для его загрузки: {os.path.basename(j['dest'])}")
            self._download(j["url"], j["dest"], j.get("sha1"), j.get("size"))
            with self._lock:
                done[0] += 1
                n = done[0]
            if total <= 100 or n % step == 0 or n == total:
                self.progress({"task": n, "total": total, "type": kind, "label": label})

        util.pool(todo, self.threads, work)

    # ----- библиотеки
    def _features(self, window: dict | None = None) -> dict:
        w = window or {}
        return {"has_custom_resolution": bool(w.get("width") and w.get("height") and not w.get("fullscreen")),
                "is_demo_user": False, "has_quick_plays_support": False, "is_quick_play_singleplayer": False,
                "is_quick_play_multiplayer": False, "is_quick_play_realms": False}

    def collect_libraries(self, vjson: dict, features: dict | None = None) -> list[dict]:
        """-> [{name, path, url, sha1, size, classpath, native, exclude}]"""
        feats = features if features is not None else self._features()
        out: list[dict] = []
        for lib in vjson.get("libraries", []):
            if not rules_allow(lib.get("rules"), self.os, feats):
                continue
            name = lib["name"]
            dl = lib.get("downloads") or {}
            natives = lib.get("natives")
            excl = ["META-INF/"] + list((lib.get("extract") or {}).get("exclude") or [])
            base = (lib.get("url") or LIB_BASE).rstrip("/") + "/"
            art = dl.get("artifact")
            if natives:
                cls = natives.get(self.os["name"])
                if cls:
                    cls = cls.replace("${arch}", "32" if self.os["arch"] == "x86" else "64")
                    e = (dl.get("classifiers") or {}).get(cls)
                    if e:
                        rel, url, sha1, size = e.get("path") or maven_path(f"{name}:{cls}"), e.get("url"), e.get("sha1"), e.get("size")
                    else:
                        rel = maven_path(f"{name}:{cls}")
                        url, sha1, size = base + rel, None, None
                    out.append({"name": f"{name}:{cls}", "path": os.path.join(self.libs_dir, rel), "url": url, "sha1": sha1,
                                "size": size, "classpath": False, "native": True, "exclude": excl})
                if art and art.get("path") and art.get("url") is not None:  # обычный jar рядом с natives — в classpath
                    out.append(self._entry(name, art, base, classpath=True))
                continue
            if art:
                e = self._entry(name, art, base, classpath=True)
            elif dl:
                continue  # downloads без artifact (например, только classifiers) — для этой ОС нечего брать
            else:
                rel = maven_path(name)
                e = {"name": name, "path": os.path.join(self.libs_dir, rel), "url": base + rel, "sha1": None,
                     "size": None, "classpath": True, "native": False, "exclude": []}
            # новые нативные jar (1.19+): имя с классификатором natives-*
            parts = name.split("@")[0].split(":")
            if len(parts) > 3 and parts[3].startswith("natives-"):
                e["native"] = True
                e["exclude"] = excl
            out.append(e)
        return out

    def _entry(self, name: str, art: dict, base: str, classpath: bool) -> dict:
        rel = art.get("path") or maven_path(name)
        url = art.get("url")
        if url is None or url == "":
            url = None
        return {"name": name, "path": os.path.join(self.libs_dir, rel), "url": url, "sha1": art.get("sha1"),
                "size": art.get("size"), "classpath": classpath, "native": False, "exclude": []}

    def extract_natives(self, libs: list[dict], dest: str) -> int:
        os.makedirs(dest, exist_ok=True)
        n = 0
        for lib in libs:
            if not lib["native"]:
                continue
            try:
                zf = zipfile.ZipFile(lib["path"])
            except (OSError, zipfile.BadZipFile) as e:
                raise RuntimeError(f"Не удалось открыть библиотеку {os.path.basename(lib['path'])}: {e}")
            with zf:
                for info in zf.infolist():
                    nm = info.filename
                    if info.is_dir() or any(nm.startswith(x) for x in lib["exclude"]):
                        continue
                    try:
                        target = util.safe_join(dest, nm)
                    except ValueError:
                        continue
                    if os.path.isfile(target) and os.path.getsize(target) == info.file_size:
                        n += 1
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    try:
                        with zf.open(info) as src, open(target, "wb") as out:
                            shutil.copyfileobj(src, out)
                        n += 1
                    except PermissionError:
                        pass  # файл занят другой запущенной игрой
        return n

    # ----- ассеты
    def ensure_assets(self, vjson: dict, game_dir: str) -> dict:
        """-> {index_id, assets_root, game_assets}"""
        ai = vjson.get("assetIndex") or {}
        idx_id = ai.get("id") or vjson.get("assets") or "legacy"
        idx_path = os.path.join(self.assets_dir, "indexes", idx_id + ".json")
        if ai.get("url"):
            self._download(ai["url"], idx_path, ai.get("sha1"))
        index = util.read_json(idx_path, None)
        if not isinstance(index, dict):
            raise RuntimeError(f"Не найден индекс ресурсов {idx_id}")
        objects = index.get("objects") or {}
        jobs, seen = [], set()
        for h in (o.get("hash") for o in objects.values()):
            if not h or h in seen:
                continue
            seen.add(h)
            jobs.append({"url": f"{ASSET_BASE}{h[:2]}/{h}", "dest": os.path.join(self.assets_dir, "objects", h[:2], h),
                         "sha1": None, "size": None})
        # размер проверяем из индекса (дёшево), sha1 — нет
        sizes = {o.get("hash"): o.get("size") for o in objects.values()}
        for j in jobs:
            j["size"] = sizes.get(os.path.basename(j["dest"]))
        self._run_jobs(jobs, "assets", "Ресурсы")
        game_assets = self.assets_dir
        if index.get("map_to_resources"):
            game_assets = os.path.join(game_dir, "resources")
        elif index.get("virtual"):
            game_assets = os.path.join(self.assets_dir, "virtual", idx_id)
        if game_assets != self.assets_dir:
            for name, o in objects.items():
                src = os.path.join(self.assets_dir, "objects", o["hash"][:2], o["hash"])
                try:
                    dst = util.safe_join(game_assets, name)
                except ValueError:
                    continue
                if os.path.isfile(dst) and os.path.getsize(dst) == o.get("size", -1):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
        return {"index_id": idx_id, "assets_root": self.assets_dir, "game_assets": game_assets}

    # ----- подготовка файлов
    def prepare(self, version_id: str, game_dir: str, window: dict | None = None) -> dict:
        v = self.resolve(version_id)
        feats = self._features(window)
        jar_id = v["_jar_id"]
        jar = os.path.join(self.vdir(jar_id), jar_id + ".jar")
        client = (v.get("downloads") or {}).get("client")
        if client and client.get("url"):
            self._download_progress(client, jar)
        elif not os.path.isfile(jar):
            raise RuntimeError(f"Не найден файл игры {jar_id}.jar")
        libs = self.collect_libraries(v, feats)
        self._run_jobs([{"url": l["url"], "dest": l["path"], "sha1": l["sha1"], "size": l["size"]} for l in libs],
                       "classes", "Библиотеки")
        for l in libs:
            if not os.path.isfile(l["path"]):
                raise RuntimeError(f"Не найдена библиотека {l['name']}")
        natives_dir = os.path.join(self.vdir(version_id), "natives")
        self.extract_natives(libs, natives_dir)
        assets = self.ensure_assets(v, game_dir)
        log_cfg = None
        lc = ((v.get("logging") or {}).get("client")) or {}
        if lc.get("file") and lc["file"].get("url"):
            log_cfg = os.path.join(self.assets_dir, "log_configs", lc["file"].get("id") or "client-log4j.xml")
            self._download(lc["file"]["url"], log_cfg, lc["file"].get("sha1"))
        cp: list[str] = []
        for l in libs:
            if l["classpath"] and l["path"] not in cp:
                cp.append(l["path"])
        if jar not in cp:
            cp.append(jar)
        return {"vjson": v, "classpath": cp, "natives_dir": natives_dir, "jar": jar, "jar_id": jar_id,
                "assets": assets, "log_config": log_cfg, "log_arg": lc.get("argument")}

    def _download_progress(self, e: dict, dest: str) -> None:
        if self._valid(dest, e.get("sha1"), e.get("size")):
            return
        self.progress({"task": 0, "total": 1, "type": "client", "label": "Minecraft"})
        self._download(e["url"], dest, e.get("sha1"), e.get("size"))
        self.progress({"task": 1, "total": 1, "type": "client", "label": "Minecraft"})

    # ----- командная строка
    def _expand(self, entries: list, variables: dict, feats: dict) -> list[str]:
        out: list[str] = []
        for a in entries:
            if isinstance(a, str):
                out.append(substitute(a, variables))
            elif isinstance(a, dict):
                if not rules_allow(a.get("rules"), self.os, feats):
                    continue
                val = a.get("value", [])
                for s in ([val] if isinstance(val, str) else val):
                    out.append(substitute(s, variables))
        return out

    def command(self, prep: dict, *, java: str, auth: dict, game_dir: str, memory_mb: int,
                jvm_args: list[str] | None = None, window: dict | None = None,
                quick: dict | None = None, version_type: str = "release", mc_version: str | None = None) -> list[str]:
        """Полная командная строка [java, ...]. quick = {host, port} — быстрый вход на сервер."""
        v = prep["vjson"]
        w = window or {}
        feats = self._features(w)
        legacy_jvm = not v["arguments"]["jvm"]
        variables = {
            "auth_player_name": auth["name"], "auth_uuid": auth["uuid"], "auth_access_token": auth["access_token"],
            "auth_session": auth["access_token"], "user_type": auth.get("user_type") or "legacy",
            "user_properties": auth.get("user_properties") or "{}", "version_name": prep["jar_id"],
            "game_directory": game_dir, "assets_root": prep["assets"]["assets_root"],
            "game_assets": prep["assets"]["game_assets"], "assets_index_name": prep["assets"]["index_id"],
            "version_type": version_type or v.get("type") or "release", "natives_directory": prep["natives_dir"],
            "launcher_name": LAUNCHER_NAME, "launcher_version": self.launcher_version,
            "classpath": self.sep.join(prep["classpath"]), "classpath_separator": self.sep,
            "library_directory": self.libs_dir, "primary_jar": prep["jar"],
            "resolution_width": str(w.get("width") or ""), "resolution_height": str(w.get("height") or ""),
            "clientid": auth.get("client_token") or "0", "auth_xuid": auth.get("xuid") or "0",
            "quickPlayPath": "", "quickPlaySingleplayer": "", "quickPlayMultiplayer": "", "quickPlayRealms": "",
        }
        jvm_src = LEGACY_JVM if legacy_jvm else v["arguments"]["jvm"]
        jvm = self._expand(jvm_src, variables, feats)
        if prep.get("log_config") and prep.get("log_arg"):
            jvm.append(substitute(prep["log_arg"], {**variables, "path": prep["log_config"]}))
        game = self._expand(v["arguments"]["game"], variables, feats)
        # окно
        if w.get("fullscreen"):
            if "--fullscreen" not in game:
                game.append("--fullscreen")
        elif w.get("width") and w.get("height") and "--width" not in game:
            game += ["--width", str(w["width"]), "--height", str(w["height"])]
        # быстрый вход
        if quick:
            host, port = quick["host"], quick["port"]
            ver = mc_version or prep["jar_id"]
            game += (["--quickPlayMultiplayer", f"{host}:{port}"] if supports_quick_play(ver)
                     else ["--server", host, "--port", str(port)])
        mem = [f"-Xmx{memory_mb}M", f"-Xms{min(memory_mb, 1024)}M"]
        main = v.get("mainClass")
        if not main:
            raise RuntimeError("В version.json нет mainClass")
        return [java, *mem, *(jvm_args or []), *jvm, main, *game]
