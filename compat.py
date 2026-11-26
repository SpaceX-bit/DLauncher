"""Проверка совместимости модов выбранного профиля (порт lib/compat.js).

Работает без интернета: читает данные, которые сам мод хранит внутри jar (fabric.mod.json, quilt.mod.json,
META-INF/mods.toml, neoforge.mods.toml, mcmod.info), и сверяет их с версией игры и загрузчиком профиля.
Ищет: мод не для того загрузчика, не для этой версии игры, не хватает нужных модов, один и тот же мод
лежит в двух файлах, моды, которые запрещают друг друга.
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import zipfile
from typing import Any

MAX_JAR = 250 * 1024 * 1024        # больше не читаем
MAX_NESTED = 40 * 1024 * 1024
MAX_NESTED_COUNT = 300
MAX_TEXT = 16 * 1024 * 1024        # метаданные мода крупнее — подозрительно
MAX_NESTED_UNPACKED = 200 * 1024 * 1024

# То, что даёт сама игра или загрузчик: такие «моды» в папке искать не надо
BUILTIN = {
    "minecraft", "java", "fabricloader", "fabric-loader", "fabric_loader", "quilt_loader", "quilt-loader",
    "forge", "neoforge", "javafml", "lowcodefml", "mclanguage", "fml", "fml_core", "neoforgespi",
}
# Старое имя Fabric API и Quilted Fabric API закрывают зависимость «fabric-api» друг за друга
FABRIC_API = ["fabric-api", "fabric", "quilted_fabric_api"]

# Какие форматы модов запускает каждый загрузчик. «soft» — может работать, но не гарантировано.
LOADER_OK = {"fabric": ["fabric"], "quilt": ["quilt", "fabric"], "forge": ["forge", "legacy-forge"], "neoforge": ["neoforge"]}
LOADER_SOFT = {"neoforge": ["forge"]}
LOADER_NAME = {"fabric": "Fabric", "quilt": "Quilt", "forge": "Forge", "neoforge": "NeoForge",
               "legacy-forge": "Forge (старый)", "vanilla": "Vanilla"}


def _s(x: Any) -> str:
    return "" if x is None else str(x)


def cut(s: Any, n: int = 80) -> str:
    s = _s(s)
    return s[: n - 1] + "…" if len(s) > n else s


def range_text(r: Any, join: str = " или ") -> str:
    """Диапазон версий в короткий текст для сообщений."""
    if isinstance(r, list):
        return cut(join.join(_s(x) for x in r), 40)
    if isinstance(r, dict):
        return cut(json.dumps(r, ensure_ascii=False, separators=(",", ":")), 40)
    return cut(r, 40)


# ---------------- версии и диапазоны ----------------
def parse_ver(s: Any) -> list[int] | None:
    """«1.20.1-rc1+build» -> [1,20,1]; непонятное -> None."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", _s(s).strip())
    return [int(x) for x in m.group(1).split(".")] if m else None


def _cmp(a: list[int], b: list[int]) -> int:
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x != y:
            return -1 if x < y else 1
    return 0


def _bump(v: list[int], idx: int) -> list[int]:
    out = v[: idx + 1]
    out[idx] += 1
    return out


def _one_comparator(tok: str, ver: list[int]):
    """Одно условие в стиле Fabric/Quilt: >=1.20, ~1.20.1, ^1.2, 1.20.x, 1.20.1, *"""
    if tok in ("*", "x", "X"):
        return True
    m = re.match(r"^(>=|<=|>|<|=|~|\^)?(.+)$", tok)
    if not m:
        return None
    op = m.group(1) or ""
    rest = m.group(2)
    if re.search(r"[xX*]", rest):
        fixed: list[int] = []
        for h in rest.split("."):
            if re.fullmatch(r"[xX*]", h):
                break
            if not re.fullmatch(r"\d+", h):
                return None
            fixed.append(int(h))
        if not fixed:
            return True
        return all((ver[i] if i < len(ver) else 0) == x for i, x in enumerate(fixed))
    v = parse_ver(rest)
    if not v or not re.fullmatch(r"v?\d+(\.\d+)*([-+].*)?", rest.strip()):
        return None
    if op == ">=":
        return _cmp(ver, v) >= 0
    if op == ">":
        return _cmp(ver, v) > 0
    if op == "<=":
        return _cmp(ver, v) <= 0
    if op == "<":
        return _cmp(ver, v) < 0
    if op == "~":
        return _cmp(ver, v) >= 0 and _cmp(ver, _bump(v, 1) if len(v) >= 2 else _bump(v, 0)) < 0
    if op == "^":
        idx = next((i for i, x in enumerate(v) if x != 0), -1)
        if idx < 0:
            idx = len(v) - 1
        return _cmp(ver, v) >= 0 and _cmp(ver, _bump(v, idx)) < 0
    return _cmp(ver, v) == 0  # «1.20.1» и «=1.20.1»: ровно эта версия


def _maven_range(s: str, ver: list[int]):
    """Диапазон Maven (Forge/NeoForge): [1.20,1.21) [1.20.1] (,1.21) [1.0,2.0),[3.0,)"""
    parts = re.findall(r"[\[(][^\])]*[\])]", s)
    if not parts:
        return None
    unknown = False
    for p in parts:
        inner = p[1:-1]
        lo = p[0] == "["
        hi = p[-1] == "]"
        if "," not in inner:
            v = parse_ver(inner)
            if not v:
                unknown = True
                continue
            if _cmp(ver, v) == 0:
                return True
            continue
        pieces = [x.strip() for x in inner.split(",")]
        a, b = pieces[0], (pieces[1] if len(pieces) > 1 else "")
        ok = True
        if a:
            va = parse_ver(a)
            if not va:
                unknown = True
                continue
            c = _cmp(ver, va)
            if (c < 0) if lo else (c <= 0):
                ok = False
        if ok and b:
            vb = parse_ver(b)
            if not vb:
                unknown = True
                continue
            c = _cmp(ver, vb)
            if (c > 0) if hi else (c >= 0):
                ok = False
        if ok:
            return True
    return None if unknown else False


def satisfies(rng: Any, ver: list[int] | None, soft: bool = False, depth: int = 0):
    """True — подходит, False — не подходит, None — не удалось понять (тогда ничего не утверждаем).
    soft: у Forge голая версия без скобок значит «желательно не ниже», это не запрет."""
    if not ver:
        return None
    if rng is None:
        return True
    if depth > 4:
        return None
    if isinstance(rng, list):
        if not rng:
            return True
        unknown = False
        for r in rng:
            x = satisfies(r, ver, soft, depth + 1)
            if x is True:
                return True
            if x is None:
                unknown = True
        return None if unknown else False
    if isinstance(rng, dict):
        if isinstance(rng.get("all"), list):
            unknown = False
            for r in rng["all"]:
                x = satisfies(r, ver, soft, depth + 1)
                if x is False:
                    return False
                if x is None:
                    unknown = True
            return None if unknown else True
        if isinstance(rng.get("any"), list):
            return satisfies(rng["any"], ver, soft, depth + 1)
        if rng.get("versions") is not None:
            return satisfies(rng["versions"], ver, soft, depth + 1)
        return None
    s = _s(rng).strip()
    if not s or s == "*":
        return True
    if re.match(r"^[\[(]", s):
        return _maven_range(s, ver)
    if soft:
        return True
    unknown = False
    for alt in s.split("||"):
        toks = [t for t in re.split(r"[\s,]+", re.sub(r"(>=|<=|>|<|=|~|\^)\s+", r"\1", alt).strip()) if t]
        if not toks:
            return True
        ok, unk = True, False
        for t in toks:
            x = _one_comparator(t, ver)
            if x is False:
                ok = False
                break
            if x is None:
                unk = True
        if ok and not unk:
            return True
        if ok and unk:
            unknown = True
    return None if unknown else False


# ---------------- чтение метаданных ----------------
def parse_toml(text: str) -> dict:
    """Минимальный разбор TOML, достаточный для mods.toml (таблицы, массивы таблиц, строки, числа, true/false)."""
    root: dict = {}
    cur = root

    def unq(k: str) -> str:
        return re.sub(r"^[\"']|[\"']$", "", k.strip())

    def walk(parts: list[str], as_array: bool) -> dict:
        o = root
        for i, k in enumerate(parts):
            last = i == len(parts) - 1
            if last and as_array:
                if not isinstance(o.get(k), list):
                    o[k] = []
                n: dict = {}
                o[k].append(n)
                return n
            nxt = o.get(k)
            if isinstance(nxt, list):
                nxt = nxt[-1] if nxt else None
            if not isinstance(nxt, dict):
                nxt = {}
                o[k] = nxt
            o = nxt
        return o

    def split_path(s: str) -> list[str]:
        return [unq(x) for x in re.findall(r"\"[^\"]*\"|'[^']*'|[^.\s]+", s)]

    def value(raw: str):
        v = raw.strip()
        if v[:1] in ('"', "'"):
            q = v[0]
            out = []
            i = 1
            while i < len(v):
                if q == '"' and v[i] == "\\" and i + 1 < len(v):
                    i += 1
                    out.append(v[i])
                    i += 1
                    continue
                if v[i] == q:
                    return "".join(out)
                out.append(v[i])
                i += 1
            return "".join(out)
        bare = re.sub(r"\s+#.*$", "", v).strip()
        if bare == "true":
            return True
        if bare == "false":
            return False
        if re.fullmatch(r"-?\d+(\.\d+)?", bare):
            return float(bare) if "." in bare else int(bare)
        return bare

    multi: str | None = None
    for line in re.split(r"\r?\n", str(text)):
        if multi:
            if multi in line:
                multi = None
            continue
        l = line.strip()
        if not l or l[0] == "#":
            continue
        m = re.match(r"^\[\[\s*([^\]]+?)\s*\]\]", l)
        if m:
            cur = walk(split_path(m.group(1)), True)
            continue
        m = re.match(r"^\[\s*([^\]]+?)\s*\]", l)
        if m:
            cur = walk(split_path(m.group(1)), False)
            continue
        m = re.match(r"^(\"[^\"]*\"|'[^']*'|[A-Za-z0-9_-]+)\s*=\s*(.*)$", l)
        if m:
            rest = m.group(2).strip()
            mark = re.match(r"^(\"\"\"|''')", rest)
            if mark:
                if mark.group(1) not in rest[3:]:
                    multi = mark.group(1)
                cur[unq(m.group(1))] = ""
            else:
                cur[unq(m.group(1))] = value(rest)
    return root


def _as_list(x: Any) -> list:
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _id_part(i: Any) -> str:
    return _s(i).split(":")[-1]


def _from_fabric(j: Any):
    if not isinstance(j, dict) or not isinstance(j.get("id"), str):
        return None
    deps, breaks = [], []
    d = j.get("depends")
    if isinstance(d, dict):
        deps = [{"id": k, "range": v} for k, v in d.items()]
    b = j.get("breaks")
    if isinstance(b, dict):
        breaks = [{"id": k, "range": v} for k, v in b.items()]
    provides = []
    for x in _as_list(j.get("provides")):
        v = x if isinstance(x, str) else (x.get("id") if isinstance(x, dict) else None)
        if v:
            provides.append(v)
    jars = []
    for x in _as_list(j.get("jars")):
        f = x.get("file") if isinstance(x, dict) else None
        if isinstance(f, str):
            jars.append(f)
    return {"loader": "fabric", "ids": [j["id"]], "version": j.get("version"), "name": j.get("name"),
            "deps": deps, "breaks": breaks, "conflicts": [], "provides": provides, "jars": jars}


def _from_quilt(j: Any):
    q = j.get("quilt_loader") if isinstance(j, dict) else None
    if not isinstance(q, dict) or not isinstance(q.get("id"), str):
        return None
    deps, breaks = [], []
    for d in _as_list(q.get("depends")):
        if isinstance(d, str):
            deps.append({"id": _id_part(d), "range": None})
        elif isinstance(d, dict) and d.get("id") and d.get("optional") is not True:
            deps.append({"id": _id_part(d["id"]), "range": d.get("versions")})
    for d in _as_list(q.get("breaks")):
        if isinstance(d, str):
            breaks.append({"id": _id_part(d), "range": None})
        elif isinstance(d, dict) and d.get("id"):
            breaks.append({"id": _id_part(d["id"]), "range": d.get("versions")})
    provides = []
    for x in _as_list(q.get("provides")):
        v = _id_part(x) if isinstance(x, str) else (_id_part(x.get("id")) if isinstance(x, dict) and x.get("id") else None)
        if v:
            provides.append(v)
    meta = q.get("metadata")
    return {"loader": "quilt", "ids": [q["id"]], "version": q.get("version"),
            "name": meta.get("name") if isinstance(meta, dict) else None,
            "deps": deps, "breaks": breaks, "conflicts": [], "provides": provides,
            "jars": [x for x in _as_list(q.get("jars")) if isinstance(x, str)]}


def _from_toml(t: dict, loader: str, jar_version: str | None):
    mods = [m for m in _as_list(t.get("mods")) if isinstance(m, dict) and isinstance(m.get("modId"), str)]
    if not mods:
        return None
    info = {"loader": loader, "ids": [m["modId"] for m in mods], "version": None, "name": mods[0].get("displayName"),
            "deps": [], "breaks": [], "conflicts": [], "provides": [], "jars": []}
    ver = mods[0].get("version")
    info["version"] = (jar_version or None) if isinstance(ver, str) and "${" in ver else ver
    all_deps = t.get("dependencies") if isinstance(t.get("dependencies"), dict) else {}
    for m in mods:
        for d in _as_list(all_deps.get(m["modId"])):
            if not isinstance(d, dict) or not isinstance(d.get("modId"), str):
                continue
            typ = d["type"].lower() if isinstance(d.get("type"), str) else None
            side = d["side"].upper() if isinstance(d.get("side"), str) else "BOTH"
            item = {"id": d["modId"], "range": d.get("versionRange"), "soft": True}
            if typ == "incompatible":
                info["breaks"].append(item)
            elif typ == "discouraged":
                info["conflicts"].append(item)
            elif typ == "optional":
                continue
            elif (typ == "required" or d.get("mandatory") is True) and side != "SERVER":
                info["deps"].append(item)
    return info


def _parse_json(s: str):
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        return None


class _Zip:
    """Чтение jar: путь к файлу или байты (вложенный jar). Имена нормализуются: «\\» -> «/»."""

    def __init__(self, src, lang: str = "ru"):
        try:
            self.zf = zipfile.ZipFile(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
        except zipfile.BadZipFile:
            raise ValueError("Это не ZIP-архив" if lang != "en" else "Not a ZIP archive") from None
        self.entries = {i.filename.replace("\\", "/"): i for i in self.zf.infolist()}

    def read_text(self, name: str) -> str | None:
        i = self.entries.get(name)
        if i is None or i.file_size > MAX_TEXT:
            return None
        try:
            return self.zf.read(i).decode("utf-8", "replace").lstrip("﻿")
        except Exception:  # noqa: BLE001
            return None

    def close(self):
        self.zf.close()


def read_jar(src, depth: int = 0, lang: str = "ru") -> dict:
    """Читает один jar (путь или bytes). Возвращает {loaders:set, infos:[...], nested:[...]}."""
    zip_ = _Zip(src, lang)
    try:
        out: dict = {"loaders": set(), "infos": [], "nested": []}
        mf = zip_.read_text("META-INF/MANIFEST.MF")
        jv = re.search(r"^Implementation-Version:\s*(.+)$", mf, re.I | re.M) if mf else None
        jar_version = jv.group(1).strip() if jv else None

        fab = zip_.read_text("fabric.mod.json")
        if fab:
            i = _from_fabric(_parse_json(fab))
            if i:
                out["loaders"].add("fabric")
                out["infos"].append(i)
        qui = zip_.read_text("quilt.mod.json")
        if qui:
            i = _from_quilt(_parse_json(qui))
            if i:
                out["loaders"].add("quilt")
                out["infos"].append(i)
        neo = zip_.read_text("META-INF/neoforge.mods.toml")
        if neo:
            i = _from_toml(parse_toml(neo), "neoforge", jar_version)
            if i:
                out["loaders"].add("neoforge")
                out["infos"].append(i)
        frg = zip_.read_text("META-INF/mods.toml")
        if frg:
            i = _from_toml(parse_toml(frg), "forge", jar_version)
            if i:
                out["loaders"].add("forge")
                out["infos"].append(i)
        if not out["loaders"]:
            old = zip_.read_text("mcmod.info")
            j = _parse_json(old) if old else None
            lst = j if isinstance(j, list) else (j.get("modList") if isinstance(j, dict) and isinstance(j.get("modList"), list) else [])
            ids = [m for m in lst if isinstance(m, dict) and isinstance(m.get("modid"), str)]
            if ids:
                out["loaders"].add("legacy-forge")
                out["infos"].append({"loader": "legacy-forge", "ids": [m["modid"] for m in ids],
                                     "version": ids[0].get("version"), "name": ids[0].get("name"),
                                     "deps": [], "breaks": [], "conflicts": [], "provides": [], "jars": []})

        # Вложенные jar (Fabric/Quilt: META-INF/jars, Forge: META-INF/jarjar) тоже дают моды-зависимости
        if depth < 2:
            paths: list[str] = []
            for i in out["infos"]:
                for j in i.get("jars") or []:
                    p = _s(j).replace("\\", "/")
                    if p not in paths:
                        paths.append(p)
            for name in zip_.entries:
                if re.fullmatch(r"META-INF/jarjar/[^/]+\.jar", name, re.I) and name not in paths:
                    paths.append(name)
            n = 0
            for p in paths:
                if n >= MAX_NESTED_COUNT:
                    break
                n += 1
                e = zip_.entries.get(p)
                if e is None or e.compress_size > MAX_NESTED or e.file_size > MAX_NESTED_UNPACKED:
                    continue
                try:
                    nested = read_jar(zip_.zf.read(e), depth + 1, lang)
                    out["nested"].extend(nested["infos"])
                    out["nested"].extend(nested["nested"])
                except Exception:  # noqa: BLE001
                    pass  # вложенный файл не читается — пропускаем
        return out
    finally:
        zip_.close()


# ---------------- сама проверка ----------------
def check_mods(profile: dict, dir: str, lang: str = "ru") -> dict:  # noqa: A002
    """Проверка папки модов. Принимает и вызов check_mods({'profile':..,'dir':..,'lang':..}) — как в JS."""
    if isinstance(profile, dict) and "profile" in profile and "dir" not in profile and dir is None:
        raise TypeError("используйте check_mods(profile, dir, lang)")
    en = lang == "en"

    def L(ru: str, e: str) -> str:
        return e if en else ru

    loader = profile.get("loader") if profile.get("loader") in ("fabric", "quilt", "forge", "neoforge") else "vanilla"
    lname = lambda l: LOADER_NAME.get(l, l)  # noqa: E731
    pver = _s(profile.get("version"))
    mc_ver = parse_ver(pver) if re.fullmatch(r"\d+\.\d+(\.\d+)?", pver) else None

    names: list[str] = []
    try:
        with os.scandir(dir) as it:
            names = [e.name for e in it if e.is_file() and re.search(r"\.jar(\.disabled)?$", e.name, re.I)]
    except OSError:
        pass  # папки модов ещё нет
    names.sort(key=lambda s: (s.casefold(), s))

    problems: list[dict] = []

    def add(**p):
        problems.append({"fixes": [], "file": None, **p})

    mods: list[dict] = []
    disabled = 0
    for file in names:
        if re.search(r"\.disabled$", file, re.I):
            disabled += 1
            continue
        abs_ = os.path.join(dir, file)
        try:
            size = os.path.getsize(abs_)
        except OSError:
            continue
        if size > MAX_JAR:
            add(level="info", code="big", file=file,
                text=L(f"Файл «{file}» очень большой — не проверялся.", f'"{file}" is very large and was not checked.'))
            continue
        try:
            mods.append({"file": file, "jar": read_jar(abs_, 0, lang)})
        except Exception as err:  # noqa: BLE001
            add(level="warn", code="unreadable", file=file,
                text=L(f"Не удалось прочитать «{file}»: {cut(str(err), 90)}. Если мод не грузится, скачай его заново.",
                       f'Could not read "{file}": {cut(str(err), 90)}. If the mod does not load, download it again.'),
                fixes=[{"type": "disable", "file": file, "label": L("Выключить", "Disable")}])

    # Какие моды (id) предоставлены: id -> {version, raw, file}
    provided: dict[str, dict] = {}

    def provide(i, version, file):
        if i and i not in provided:
            provided[i] = {"version": parse_ver(version), "raw": _s(version), "file": file}

    for m in mods:
        for info in list(m["jar"]["infos"]) + list(m["jar"]["nested"]):
            for i in info["ids"]:
                provide(i, info.get("version"), m["file"])
            for i in info["provides"]:
                provide(i, info.get("version"), m["file"])

    def have(i: str) -> bool:
        return i in provided or (i in ("fabric", "fabric-api") and any(x in provided for x in FABRIC_API))

    def display(m: dict) -> str:
        infos = m["jar"]["infos"]
        i = infos[0] if infos else None
        return cut((i and (i.get("name") or i["ids"][0])) or m["file"], 50)

    if loader == "vanilla" and any(m["jar"]["infos"] for m in mods):
        add(level="warn", code="vanilla",
            text=L("В профиле выбран Vanilla — моды в нём не загружаются. Создай профиль с Fabric, Forge, NeoForge или Quilt.",
                   "This profile is Vanilla — mods will not load. Create a profile with Fabric, Forge, NeoForge or Quilt."))

    # Один мод в двух файлах
    by_id: dict[str, list[dict]] = {}
    for m in mods:
        infos = m["jar"]["infos"]
        if not infos or not infos[0]["ids"] or not infos[0]["ids"][0]:
            continue
        by_id.setdefault(infos[0]["ids"][0], []).append(m)
    dup_files: set[str] = set()
    for i, lst in by_id.items():
        if len(lst) < 2:
            continue
        for m in lst:
            dup_files.add(m["file"])
        files = ", ".join(m["file"] for m in lst)
        add(level="error", code="dup", file=lst[0]["file"],
            text=L(f"Мод «{display(lst[0])}» ({cut(i, 40)}) лежит в {len(lst)} файлах: {files}. Игра не запустится — оставь один.",
                   f'Mod "{display(lst[0])}" ({cut(i, 40)}) is in {len(lst)} files: {files}. The game will not start — keep only one.'),
            fixes=[{"type": "disable", "file": m["file"],
                    "label": L(f"Выключить {cut(m['file'], 28)}", f"Disable {cut(m['file'], 28)}")} for m in lst])

    for m in mods:
        jar, file = m["jar"], m["file"]
        if not jar["infos"]:
            if loader != "vanilla":
                add(level="warn", code="nometa", file=file,
                    text=L(f"В «{file}» нет данных о моде — загрузчик может его проигнорировать. Возможно, это не мод, а библиотека или архив не того формата.",
                           f'"{file}" has no mod metadata — the loader may ignore it. It may be a library or a file of another kind.'),
                    fixes=[{"type": "disable", "file": file, "label": L("Выключить", "Disable")}])
            continue
        if loader == "vanilla":
            continue
        name = display(m)
        loaders = sorted(jar["loaders"], key=lambda x: ["fabric", "quilt", "neoforge", "forge", "legacy-forge"].index(x)
                         if x in ("fabric", "quilt", "neoforge", "forge", "legacy-forge") else 9)

        # 1. Загрузчик
        ok = any(l in LOADER_OK[loader] for l in loaders)
        soft = not ok and any(l in LOADER_SOFT.get(loader, []) for l in loaders)
        if not ok and not soft:
            ln = "/".join(lname(l) for l in loaders)
            add(level="error", code="loader", file=file,
                text=L(f"«{name}» сделан для {ln}, а в профиле {lname(loader)} — такой мод не загрузится.",
                       f'"{name}" is built for {ln}, but the profile uses {lname(loader)} — it will not load.'),
                fixes=[{"type": "disable", "file": file, "label": L("Выключить мод", "Disable mod")}])
            continue
        if soft:
            add(level="warn", code="loader-soft", file=file,
                text=L(f"«{name}» сделан для Forge, а в профиле NeoForge. На новых версиях игры такой мод может не загрузиться.",
                       f'"{name}" is built for Forge but the profile uses NeoForge. On newer game versions it may not load.'),
                fixes=[{"type": "disable", "file": file, "label": L("Выключить мод", "Disable mod")}])

        # Проверяем те описания мода, которые подходят нашему загрузчику
        infos = [i for i in jar["infos"] if i["loader"] in LOADER_OK[loader] or i["loader"] in LOADER_SOFT.get(loader, [])]
        for info in (infos or jar["infos"]):
            # 2. Версия игры
            mc_dep = next((d for d in info["deps"] if d["id"] == "minecraft"), None)
            if mc_dep and mc_ver:
                if satisfies(mc_dep["range"], mc_ver, bool(mc_dep.get("soft"))) is False:
                    add(level="error", code="mc", file=file,
                        text=L(f"«{name}» рассчитан на Minecraft {range_text(mc_dep['range'])}, а в профиле {profile.get('version')}.",
                               f'"{name}" requires Minecraft {range_text(mc_dep["range"], " or ")}, but the profile is {profile.get("version")}.'),
                        fixes=[{"type": "disable", "file": file, "label": L("Выключить мод", "Disable mod")}])
                    continue  # остальные претензии к моду не по делу
            # 3. Нужные моды
            for d in info["deps"]:
                if d["id"] in BUILTIN or d["id"] == "minecraft":
                    continue
                if not have(d["id"]):
                    add(level="error", code="dep", file=file,
                        text=L(f"«{name}» требует мод «{cut(d['id'], 40)}», но его нет в папке модов.",
                               f'"{name}" requires the mod "{cut(d["id"], 40)}", which is not in the mods folder.'),
                        fixes=[{"type": "search", "query": d["id"], "label": L(f"Найти «{cut(d['id'], 24)}»", f'Find "{cut(d["id"], 24)}"')},
                               {"type": "disable", "file": file, "label": L("Выключить мод", "Disable mod")}])
                else:
                    p = provided.get(d["id"])
                    if p and p["version"] and d["range"] is not None and satisfies(d["range"], p["version"], bool(d.get("soft"))) is False:
                        add(level="warn", code="depver", file=file,
                            text=L(f"«{name}» требует «{cut(d['id'], 40)}» версии {range_text(d['range'])}, а установлена {cut(p['raw'], 30)}. Обнови или замени его.",
                                   f'"{name}" requires "{cut(d["id"], 40)}" {range_text(d["range"], " or ")}, but {cut(p["raw"], 30)} is installed. Update or replace it.'),
                            fixes=[{"type": "search", "query": d["id"], "label": L(f"Найти «{cut(d['id'], 24)}»", f'Find "{cut(d["id"], 24)}"')}])
            # 4. Запрещённые сочетания
            for lst, level, code in ((info["breaks"], "error", "breaks"), (info.get("conflicts") or [], "warn", "conflicts")):
                for b in lst:
                    p = provided.get(b["id"])
                    if not p or p["file"] == file or file in dup_files:
                        continue
                    any_ver = b["range"] is None or b["range"] == "*"
                    if not any_ver and not p["version"]:
                        continue
                    if satisfies(b["range"], p["version"] or [0], bool(b.get("soft")) and b["range"] is not None) is True:
                        other = next((x for x in mods if x["file"] == p["file"]), None)
                        oname = display(other) if other else cut(b["id"], 40)
                        verb_ru = "несовместим" if level == "error" else "плохо работает"
                        verb_en = "is incompatible" if level == "error" else "may not work well"
                        fixes = [{"type": "disable", "file": file, "label": L(f"Выключить {cut(name, 24)}", f"Disable {cut(name, 24)}")}]
                        if other:
                            fixes.append({"type": "disable", "file": other["file"],
                                          "label": L(f"Выключить {display(other)[:24]}", f"Disable {display(other)[:24]}")})
                        add(level=level, code=code, file=file,
                            text=L(f"«{name}» {verb_ru} с «{oname}».", f'"{name}" {verb_en} with "{oname}".'),
                            fixes=fixes)

    # убираем повторы (мод с двумя описаниями мог дать одинаковую претензию)
    seen: set[str] = set()
    uniq = []
    for p in problems:
        k = f"{p['code']}|{p['file']}|{p['text']}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    rank = {"error": 0, "warn": 1, "info": 2}
    uniq.sort(key=lambda p: rank[p["level"]])
    return {
        "problems": uniq,
        "scanned": len(mods),
        "disabled": disabled,
        "summary": {"errors": sum(1 for p in uniq if p["level"] == "error"),
                    "warnings": sum(1 for p in uniq if p["level"] == "warn")},
    }


# ---------------- обработчики ----------------
def handlers(ctx):
    running: dict[str, dict] = {}
    lock = threading.Lock()

    def compat_check(payload=None):
        payload = payload or {}
        p = ctx.find_profile(payload.get("profileId") or ctx.settings.get("currentProfile"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        with lock:
            job = running.get(p["id"])
            mine = job is None
            if mine:
                job = {"event": threading.Event(), "result": None}
                running[p["id"]] = job
        if not mine:
            job["event"].wait(120)
            return job["result"] or {"ok": False, "error": "Проверка не завершилась"}
        try:
            r = check_mods(p, os.path.join(ctx.instance_dir(p["id"]), "mods"), ctx.settings.get("lang", "ru"))
            job["result"] = {"ok": True, **r, "profile": {"id": p["id"], "name": p["name"], "version": p["version"], "loader": p["loader"]}}
        except Exception as e:  # noqa: BLE001
            job["result"] = {"ok": False, "error": str(e)}
        finally:
            with lock:
                running.pop(p["id"], None)
            job["event"].set()
        return job["result"]

    return {"compat:check": compat_check}
