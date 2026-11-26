"""Новости Minecraft: патчноуты Mojang; запасной вариант — последние версии из манифеста. Порт lib/news.js."""
from __future__ import annotations

import html as _html
import json
import re
import threading
import time
import urllib.parse

from . import util

HOST = "https://launchercontent.mojang.com"
FEEDS = [f"{HOST}/v2/javaPatchNotes.json", f"{HOST}/javaPatchNotes.json"]
CACHE_S = 30 * 60
TYPES = {"release", "snapshot"}


def clean(s, n: int) -> str:
    return re.sub(r"\s+", " ", str("" if s is None else s)).strip()[:n]


def html_to_text(h) -> str:
    s = str(h or "")
    s = re.sub(r"<(script|style)[\s\S]*?</\1>", "", s, flags=re.I)
    s = re.sub(r"<img[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</(p|div|h[1-6]|ul|ol|table|tr)>", "\n\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n• ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ")
    s = _html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def safe_path(p) -> bool:
    return isinstance(p, str) and bool(re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", p)) and ".." not in p.split("/") and not p.startswith("/")


def _date(s) -> int:
    try:
        import datetime
        return int(datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:  # noqa: BLE001
        return 0


def parse_feed(j) -> list[dict]:
    raw = j if isinstance(j, list) else (j.get("entries") if isinstance(j, dict) and isinstance(j.get("entries"), list) else [])
    items = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        title = clean(e.get("title") or (f"Minecraft {e['version']}" if e.get("version") else ""), 120)
        if not title:
            continue
        body = html_to_text(e["body"])[:8000] if isinstance(e.get("body"), str) else ""
        items.append({
            "id": clean(e.get("id") or e.get("version") or title, 80), "title": title,
            "type": e["type"] if e.get("type") in TYPES else "release", "version": clean(e.get("version"), 40),
            "date": _date(e.get("date")), "text": clean(e.get("shortText") or body, 300), "body": body,
            "path": e["contentPath"] if safe_path(e.get("contentPath")) else "",
        })
    items.sort(key=lambda x: -x["date"])
    return items


def from_manifest(m) -> list[dict]:
    out = []
    for v in ((m or {}).get("versions") or []):
        if v.get("type") in TYPES:
            out.append({"id": clean(v["id"], 40), "title": f"Minecraft {clean(v['id'], 40)}", "type": v["type"],
                        "version": clean(v["id"], 40), "date": _date(v.get("releaseTime")),
                        "text": "Snapshot" if v["type"] == "snapshot" else "Release", "body": "", "path": ""})
        if len(out) >= 12:
            break
    return out


def handlers(ctx):
    state = {"cache": None, "by_id": {}}
    lock = threading.Lock()

    def lst(arg=None):
        force = bool((arg or {}).get("force"))
        c = state["cache"]
        if not force and c and time.time() - c["at"] < CACHE_S:
            return {"ok": True, "items": c["items"][:20], "source": c["source"]}
        items, source = [], "mojang"
        for url in FEEDS:
            try:
                items = parse_feed(util.get_json(url, timeout=10))
            except Exception:  # noqa: BLE001
                items = []
            if items:
                break
        if not items:
            try:
                items = from_manifest(ctx.get_manifest())
                source = "manifest"
            except Exception:  # noqa: BLE001
                items = []
        if not items:
            return {"ok": False, "error": "Не удалось загрузить новости. Проверь подключение к интернету."}
        with lock:
            state["cache"] = {"at": time.time(), "items": items, "source": source}
            state["by_id"] = {it["id"]: it for it in items}
        return {"ok": True, "items": items[:20], "source": source}

    def read(arg=None):
        it = state["by_id"].get(str((arg or {}).get("id")))
        if not it:
            return {"ok": False, "error": "Запись не найдена: обнови список."}
        if it["body"]:
            return {"ok": True, "title": it["title"], "body": it["body"], "date": it["date"]}
        if not it["path"]:
            return {"ok": True, "title": it["title"], "body": it["text"], "date": it["date"]}
        try:
            _, hdr, data = util.request(f"{HOST}/v2/{it['path']}", timeout=10)
            ct = {k.lower(): v for k, v in hdr.items()}.get("content-type", "")
            if "json" in ct.lower():
                j = json.loads(data.decode("utf-8"))
                body = html_to_text(j.get("body") or j.get("content") or "")
            else:
                body = html_to_text(data.decode("utf-8", "replace"))
            return {"ok": True, "title": it["title"], "body": (body or it["text"])[:8000], "date": it["date"]}
        except Exception:  # noqa: BLE001
            return {"ok": True, "title": it["title"], "body": it["text"], "date": it["date"], "partial": True}

    return {"news:list": lst, "news:read": read}
