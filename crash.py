"""Разбор вылетов: crash-report, logs/latest.log и консоль игры -> понятные причины (RU/EN). Порт lib/crash.js."""
from __future__ import annotations

import os
import re

MAX_READ = 400 * 1024


def tail_of(path: str, mx: int = MAX_READ) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - mx))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def latest_crash_report(game_dir: str):
    d = os.path.join(game_dir, "crash-reports")
    best = None
    try:
        for f in os.listdir(d):
            if not re.match(r"^crash-.*\.txt$", f, re.I):
                continue
            t = os.stat(os.path.join(d, f)).st_mtime * 1000
            if best is None or t > best["time"]:
                best = {"file": os.path.join(d, f), "name": f, "time": t}
    except OSError:
        pass
    return best


def _uniq(a):
    return list(dict.fromkeys(a))


def build_rules(T, profile):
    loader = (profile or {}).get("loader") or "vanilla"
    I = re.I

    def oom(s):
        if not re.search(r"java\.lang\.OutOfMemoryError|Java heap space|GC overhead limit exceeded", s, I):
            return None
        return {"id": "oom", "action": "ram",
                "title": T("Игре не хватило выделенной памяти", "The game ran out of allocated memory"),
                "text": T("Увеличь память в Настройках (ползунок «Выделенная память») или в настройках профиля. Для сборок с большим числом модов обычно нужно 6–8 ГБ.",
                          "Increase memory in Settings (the “Allocated memory” slider) or in the profile settings. Modpacks with many mods usually need 6–8 GB.")}

    def ram_too_much(s):
        if not re.search(r"Could not reserve enough space|Invalid maximum heap size|Error occurred during initialization of VM|There is insufficient memory for the Java Runtime|The paging file is too small", s, I):
            return None
        return {"id": "ram-too-much", "action": "ram",
                "title": T("Выделено больше памяти, чем доступно компьютеру", "More memory is allocated than the computer has"),
                "text": T("Уменьши память в Настройках: оставь компьютеру хотя бы 2–3 ГБ. Закрой лишние программы и браузер перед игрой.",
                          "Lower the memory in Settings: leave at least 2–3 GB for the system. Close other programs and the browser before playing.")}

    def java_version(s):
        need = None
        m = (re.search(r"compiled by a more recent version of the Java Runtime \(class file version (\d+)", s, I)
             or re.search(r"UnsupportedClassVersionError[^\n]*?class file version (\d+)", s, I))
        if m:
            need = int(m.group(1)) - 44
        m = re.search(r"requires (?:at least )?Java (\d+)", s, I)
        if not need and m:
            need = int(m.group(1))
        if not need or need < 8 or need > 40:
            return None
        return {"id": "java-version", "action": "java",
                "title": T(f"Нужна Java {need} или новее", f"Java {need} or newer is required"),
                "text": T(f"Эта версия игры или мод требует Java {need}. Очисти поле «Путь к Java» в Настройках и профиле: лаунчер скачает подходящую сам.",
                          f"This game version or mod needs Java {need}. Clear the “Java path” field in Settings and in the profile: the launcher will download the right one.")}

    def missing_dep(s):
        out = []
        for m in re.finditer(r"Mod '([^']+)' \(([^)]+)\)[^\n]*? requires ([^\n]*?), which is (?:missing|not installed)", s, I):
            out.append(f"{m.group(1)}: {re.sub(chr(92) + 's+', ' ', m.group(3)).strip()}")
        for m in re.finditer(r"Mod ID: '([^']+)', Requested by: '([^']+)'", s):
            out.append(T(f"{m.group(2)} требует мод {m.group(1)}", f"{m.group(2)} requires the mod {m.group(1)}"))
        if not out:
            return None
        lst = _uniq(out)[:6]
        return {"id": "missing-dep", "mods": lst,
                "title": T("Не хватает мода, нужного другим модам", "A mod needed by other mods is missing"),
                "text": T("Установи недостающий мод (часто это Fabric API / Cloth Config / Architectury) во вкладке «Моды»: " + "; ".join(lst),
                          "Install the missing mod (often Fabric API / Cloth Config / Architectury) in the Mods tab: " + "; ".join(lst))}

    def incompatible(s):
        if not re.search(r"Incompatible mods found|Mod(?:s)? (?:is|are) incompatible|conflicts? with mod", s, I):
            return None
        return {"id": "incompatible",
                "title": T("Моды конфликтуют между собой", "Mods conflict with each other"),
                "text": T("В логе есть сообщение о несовместимых модах. Отключи недавно добавленный мод во вкладке «Установлено» (кнопка «Выключить») и запусти снова.",
                          "The log reports incompatible mods. Disable the most recently added mod in the Installed tab (“Disable”) and launch again.")}

    def duplicate(s):
        m = re.search(r"Duplicate (?:mods? found|mod)[^\n]*|Found duplicate mods?[^\n]*|duplicate (?:mod )?id[^\n]*", s, I)
        if not m:
            return None
        return {"id": "duplicate",
                "title": T("Один и тот же мод установлен дважды", "The same mod is installed twice"),
                "text": T("Во вкладке «Установлено» найди два файла одного мода (разные версии) и удали лишний. " + m.group(0)[:120],
                          "In the Installed tab find two files of the same mod (different versions) and delete one. " + m.group(0)[:120])}

    def wrong_loader(s):
        m = re.search(r"Mod file [^\n]*?([\w.\-+]+\.jar) is missing (?:neoforge\.)?mods\.toml", s, I)
        if not m:
            return None
        nm = "NeoForge" if loader == "neoforge" else "Forge"
        return {"id": "wrong-loader", "mods": [m.group(1)],
                "title": T("Мод не для этого загрузчика", "This mod is not for this loader"),
                "text": T(f"Файл {m.group(1)} сделан не для {nm} (скорее всего, для Fabric). Удали его и скачай версию под свой загрузчик.",
                          f"{m.group(1)} is not built for {nm} (most likely it is for Fabric). Delete it and download the build for your loader.")}

    def corrupt(s):
        m = re.search(r"(?:ZipException|zip END header not found|invalid (?:LOC|CEN) header|Corrupted? (?:jar|zip))[^\n]*", s, I)
        if not m:
            return None
        jar = re.search(r"([\w.\-+]+\.jar)", s[max(0, m.start() - 400):m.start() + 400])
        j = jar.group(1) if jar else None
        r = {"id": "corrupt-file",
             "title": T("Повреждённый файл", "Corrupted file"),
             "text": T(f"Один из файлов игры или модов повреждён{' (' + j + ')' if j else ''}. Удали его и скачай заново: так бывает при обрыве загрузки.",
                       f"One of the game or mod files is corrupted{' (' + j + ')' if j else ''}. Delete it and download again: this happens after an interrupted download.")}
        if j:
            r["mods"] = [j]
        return r

    def opengl(s):
        if not re.search(r"GLFW error 6554[23]|WGL: The driver does not appear to support OpenGL|Pixel format not accelerated|OpenGL (?:is )?not supported|GLFW error 65545", s, I):
            return None
        return {"id": "opengl",
                "title": T("Видеокарта или драйвер не поддерживает OpenGL", "The graphics card or driver does not support OpenGL"),
                "text": T("Обнови драйвер видеокарты (сайты NVIDIA, AMD, Intel). Если у тебя две видеокарты, запускай лаунчер на дискретной. Это также бывает при запуске через удалённый рабочий стол.",
                          "Update your graphics driver (NVIDIA, AMD or Intel). With two GPUs, run the launcher on the discrete one. This also happens over a remote desktop.")}

    def disk_full(s):
        if not re.search(r"No space left on device|Not enough space on disk|There is not enough space on the disk", s, I):
            return None
        return {"id": "disk-full",
                "title": T("Закончилось место на диске", "The disk is full"),
                "text": T("Освободи место на диске с игрой (нужно несколько ГБ) или смени корневую папку в Настройках.",
                          "Free some space on the game drive (a few GB are needed) or change the root folder in Settings.")}

    def locked(s):
        if not re.search(r"AccessDeniedException|Access is denied|being used by another process|Failed to delete file", s, I):
            return None
        return {"id": "file-locked",
                "title": T("Файл занят или нет прав на запись", "A file is locked or write access is denied"),
                "text": T("Закрой другие копии игры и лаунчера, проверь, не блокирует ли файлы антивирус, и не лежит ли игра в защищённой папке (например, Program Files).",
                          "Close other game/launcher instances, check that your antivirus is not locking files and that the game is not in a protected folder (such as Program Files).")}

    def auth(s):
        if not re.search(r"Invalid session \(Try restarting your game\)|Failed to verify username|Authentication servers are down|You have been logged out", s, I):
            return None
        return {"id": "auth",
                "title": T("Проблема со входом в аккаунт", "Account sign-in problem"),
                "text": T("Войди в аккаунт Microsoft заново в Настройках либо переключись на офлайн-режим для игры без лицензии.",
                          "Sign in to your Microsoft account again in Settings, or switch to offline mode to play without a licence.")}

    def suspects(s):
        crit = re.search(r"Suspected Mods?:\s*([^\n]+(?:\n\t[^\n]+)*)", s, I)
        mods = [m.group(1) for m in re.finditer(r"-- Mod loading issue for: ([\w.\-]+) --", s)]
        if crit and not re.match(r"^none", crit.group(1).strip(), I):
            mods += [re.sub(r"\s*\(.*$", "", l.strip()).strip() for l in crit.group(1).split("\n") if l.strip()]
        mods = _uniq([m for m in mods if m])[:6]
        if not mods:
            return None
        return {"id": "suspects", "mods": mods,
                "title": T("Подозрительные моды", "Suspect mods"),
                "text": T("Игра сама указала, какие моды могли вызвать вылет: " + ", ".join(mods) + ". Попробуй их отключить, обновить или заменить.",
                          "The game itself pointed at these mods: " + ", ".join(mods) + ". Try disabling, updating or replacing them.")}

    def mismatch(s):
        m = re.search(r"(NoClassDefFoundError|NoSuchMethodError|NoSuchFieldError|ClassNotFoundException|AbstractMethodError)(?::\s*|\s+)['\"]?([^\n]{1,100})", s)
        if not m:
            return None
        det = re.sub(r"['\"]+$", "", m.group(2))[:80]
        return {"id": "mod-mismatch",
                "title": T("Моды не подходят друг к другу или к версии игры", "Mods do not match each other or the game version"),
                "text": T(f"Игре не хватило части кода ({m.group(1)}: {det}). Обычно это мод для другой версии Minecraft либо устаревшая версия мода. Обнови моды (вкладка «Установлено» → «Обновить все»).",
                          f"The game could not find some code ({m.group(1)}: {det}). Usually it is a mod for another Minecraft version or an outdated mod. Update your mods (Installed → “Update all”).")}

    return [oom, ram_too_much, java_version, missing_dep, incompatible, duplicate, wrong_loader, corrupt, opengl,
            disk_full, locked, auth, suspects, mismatch]


def summarize(s: str) -> str:
    d = re.search(r"^Description:\s*(.+)$", s, re.M)
    ex = re.search(r"^((?:[\w$]+\.)+[\w$]*(?:Exception|Error)(?::[^\n]*)?)$", s, re.M)
    return " — ".join(x for x in [d and d.group(1).strip(), ex and ex.group(1).strip()] if x)[:240]


def analyze(text, profile=None, lang="ru", code=None) -> dict:
    T = (lambda ru, en: en) if lang == "en" else (lambda ru, en: ru)
    s = str(text or "")
    findings = []
    for rule in build_rules(T, profile):
        try:
            f = rule(s)
            if f:
                findings.append(f)
        except Exception:  # noqa: BLE001
            pass
    if not findings:
        c_ru = f"Игра завершилась с кодом {code}. " if code is not None else ""
        c_en = f"The game exited with code {code}. " if code is not None else ""
        findings.append({"id": "unknown",
                         "title": T("Причину автоматически определить не удалось", "The cause could not be identified automatically"),
                         "text": T(c_ru + "Открой «Консоль» и посмотри последние строки, а также crash-report. Если вылет случился после установки мода, отключи его и проверь снова.",
                                   c_en + "Open the Console and read the last lines, and the crash report. If it started after installing a mod, disable that mod and check again.")})
    return {"findings": findings[:6], "summary": summarize(s)}


def handlers(ctx):
    def analyze_h(arg=None):
        arg = arg or {}
        p = ctx.find_profile(arg.get("profileId") or ctx.settings.get("currentProfile"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        d = ctx.instance_dir(p["id"])
        crash = latest_crash_report(d)
        parts, source = [], "console"
        if crash:
            parts.append(tail_of(crash["file"]))
            source = "crash-report"
        parts.append(tail_of(os.path.join(d, "logs", "latest.log")))
        gl = getattr(ctx, "gamelog", None)
        parts.append((gl.text() if gl else "")[-MAX_READ:])
        text = "\n".join(x for x in parts if x)
        if not text.strip():
            return {"ok": True, "empty": True, "findings": [], "summary": "", "hasReport": False}
        r = analyze(text, profile=p, lang=ctx.settings.get("lang"), code=arg.get("code"))
        return {"ok": True, **r, "source": source, "hasReport": bool(crash),
                "report": {"name": crash["name"], "time": crash["time"]} if crash else None}

    def open_h(arg=None):
        p = ctx.find_profile((arg or {}).get("profileId") or ctx.settings.get("currentProfile"))
        if not p:
            return {"ok": False, "error": "Профиль не найден"}
        crash = latest_crash_report(ctx.instance_dir(p["id"]))
        if not crash:
            return {"ok": False, "error": "Отчётов о вылетах нет"}
        ctx.ui.open_path(crash["file"])
        return {"ok": True}

    return {"crash:analyze": analyze_h, "crash:open": open_h}
