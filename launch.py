"""Запуск игры: порт 'game:launch' из main.js на собственном движке (core/minecraft.py)."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time

from . import java as javamod
from . import loaders, minecraft, util
from .base import parse_jvm_args

_SERVER_RE = re.compile(r"Connecting to ([^\s,]+), (\d{2,5})")


def _redact(ctx, text: str) -> str:
    try:
        from . import gamelog
        return gamelog.redact(text)
    except Exception:  # noqa: BLE001
        return re.sub(r"(--accessToken\s+)\S+", r"\1***", text)


def _track_server(ctx, profile: dict, text: str) -> None:
    found = _SERVER_RE.findall(text)
    if not found:
        return
    host, port = found[-1]
    last = profile.get("lastServer")
    if last and last.get("host") == host and str(last.get("port")) == port:
        return
    profile["lastServer"] = {"host": host, "port": int(port), "at": int(time.time() * 1000)}
    ctx.save_settings()
    ctx.send("server:last", {"profileId": profile["id"], "lastServer": profile["lastServer"]})


def _check_server(host, port):
    try:
        from . import servers
        return servers.check_server(host, port)
    except ImportError:
        pass
    host = str(host or "").strip()
    port = int(port or 25565)
    if not host or not re.fullmatch(r"[A-Za-z0-9._-]+", host) or not 1 <= port <= 65535:
        raise ValueError("Неверный адрес сервера")
    return {"host": host, "port": port}


def _svc(ctx, name):
    return getattr(ctx, name, None)


def handlers(ctx):
    def log(src, text):
        gl = _svc(ctx, "gamelog")
        if gl:
            gl.push(src, text)

    def finish(profile, code):
        ctx.launching = False
        gl, st, pr = _svc(ctx, "gamelog"), _svc(ctx, "stats"), _svc(ctx, "presence")
        if gl:
            gl.flush()
        if st:
            st.end()
        if pr:
            pr.set_idle()
        ctx.send("game:closed", {"code": code, "profileId": profile["id"]})

    def pump(proc, profile):
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace")
                if not line.strip():
                    continue
                log("game", line)
                ctx.send("game:log", _redact(ctx, line))
                _track_server(ctx, profile, line)
        except Exception as e:  # noqa: BLE001
            ctx.diag(f"game output reader: {e}")
        code = proc.wait()
        finish(profile, code)

    def game_launch(arg=None):
        arg = arg or {}
        if ctx.launching:
            return {"ok": False, "error": "Игра уже запускается"}
        S = ctx.settings
        profile = ctx.find_profile(arg.get("profileId") or S.get("currentProfile"))
        if not profile:
            return {"ok": False, "error": "Сначала создай профиль (вкладка «Профили»)."}
        ctx.launching = True
        pr, gl = _svc(ctx, "presence"), _svc(ctx, "gamelog")
        if pr:
            pr.set_launching(profile)
        loader = profile.get("loader")
        if gl:
            gl.start(f"{profile['name']} · {profile['version']}" + (f" · {loader}" if loader and loader != "vanilla" else ""))
        try:
            root = ctx.root
            os.makedirs(root, exist_ok=True)
            game_dir = ctx.ensure_instance(profile["id"])

            # Аккаунт
            if S.get("accountMode") == "microsoft":
                ms = _svc(ctx, "msauth")
                if ms is None:
                    raise RuntimeError("Вход через Microsoft недоступен")
                auth = ms.get_launch_auth()
            else:
                auth = minecraft.offline_auth(S.get("nickname") or "Player")

            ram_mb = int(round(float(profile.get("ram") or S.get("ram") or 4) * 1024))
            jvm = parse_jvm_args(profile.get("jvmArgs"))
            window = None
            if profile.get("fullscreen"):
                window = {"fullscreen": True}
            elif profile.get("width") and profile.get("height"):
                window = {"width": int(profile["width"]), "height": int(profile["height"])}

            # Java: своя или автоматическая
            java = (profile.get("javaPath") or S.get("javaPath") or "").strip()
            if not java:
                java = javamod.ensure_java(ctx, javamod.required_java(ctx, profile["version"]))

            ctx.send("game:status", "Подготовка загрузчика..." if loader != "vanilla" else "Загрузка файлов игры...")
            custom = loaders.prepare_loader(ctx, loader, profile["version"], profile.get("loaderVersion") or "", java)
            version_id = custom or profile["version"]

            quick = None
            if arg.get("quickJoin"):
                srv = arg.get("server")
                quick = _check_server(srv["host"], srv.get("port")) if srv else profile.get("lastServer")
                if not quick:
                    raise ValueError("Неверный адрес сервера")

            profile["lastPlayed"] = int(time.time() * 1000)
            ctx.save_settings()

            # Резервные копии миров (ошибка не останавливает игру)
            if S.get("autoBackup") and _svc(ctx, "worlds"):
                try:
                    ctx.send("game:status", ctx.t("Резервные копии миров...", "Backing up worlds..."))
                    b = ctx.worlds.auto_backup(profile, keep=S.get("backupKeep", 5))
                    if b.get("made"):
                        log("launcher", "Backups: " + ", ".join(b["made"]))
                    if b.get("skipped"):
                        log("launcher", "Backup skipped (too big): " + ", ".join(b["skipped"]))
                    if b.get("failed"):
                        log("launcher", "Backup failed: " + ", ".join(str(f.get("world")) for f in b["failed"]))
                except Exception as e:  # noqa: BLE001
                    log("launcher", f"Backup error: {e}")

            def dbg(m):
                log("launcher", str(m))
                ctx.send("game:log", _redact(ctx, str(m)))

            eng = minecraft.Engine(
                root, manifest=ctx.get_manifest,
                progress=lambda p: ctx.send("game:progress", p),
                status=lambda s: ctx.send("game:status", s), debug=dbg,
                launcher_version=ctx.app_version)
            ctx.send("game:status", "Загрузка файлов игры...")
            prep = eng.prepare(version_id, game_dir, window)
            cmd = eng.command(prep, java=java, auth=auth, game_dir=game_dir, memory_mb=ram_mb, jvm_args=jvm,
                              window=window, quick=quick, version_type=profile.get("versionType") or "release",
                              mc_version=profile["version"])
            log("launcher", "Launch: " + " ".join(_redact(ctx, c) if "token" in c.lower() else c for c in cmd[:6]) + " ...")
            try:
                proc = subprocess.Popen(cmd, cwd=game_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        creationflags=util.NO_WINDOW)
            except OSError as e:
                raise RuntimeError(f"Не удалось запустить игру. Проверь путь к Java в настройках. ({e})")
            st = _svc(ctx, "stats")
            if pr:
                pr.set_playing(profile)
            if st:
                st.begin(profile["id"])
            threading.Thread(target=pump, args=(proc, profile), daemon=True, name="dl-game").start()
            ctx.send("game:status", "Игра запущена")
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            ctx.launching = False
            if pr:
                pr.set_idle()
            log("launcher", f"Launch error: {e}")
            return {"ok": False, "error": str(e)}

    return {"game:launch": game_launch}
