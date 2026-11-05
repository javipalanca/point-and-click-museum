"""Control panel of the catalogue (behind a user and password), served by the games container (server/games.py).

    /admin/                         the panel (server/admin/index.html, admin.js, admin.css)
    POST /api/admin/login           {"user", "password"} -> session cookie (HttpOnly, SameSite=Strict)
    POST /api/admin/logout
    GET  /api/admin/me
    GET  /api/admin/catalog         every game and edition, whatever its state
    GET  /api/admin/status          last sync, its log, the download log, the server cache
    POST /api/admin/sync            {"only": ["scummvm"|"archive"|"gog"], "validate": n, "retryFailed": bool}
    GET  /api/admin/search?q=…      search Internet Archive by title (to attach an item to a game)
    POST /api/admin/games/<id>              {"gog": url|null, "forceRecord": bool}
    GET  /api/admin/inspect?archive=…       what an Internet Archive item holds (zips, 7z, CD images, DOS/Windows
                                            programs, ScummVM data), without downloading it (tools/ia_inspect.py);
                                            archive= is an identifier or an archive.org link (details/… or download/…)
    GET  /api/admin/try?archive=…&file=…&exe=…|engine=…   that zip, prepared for the panel's emulator, saving nothing
    POST /api/admin/games/<id>/attach       {"archive": identifier, "file"?: zip, "exe"?: program, "engine"?: scummvm engine}
    GET  /api/admin/editions/<key>/bundle   download and prepare any edition, for testing in the panel's emulator
    POST /api/admin/editions/<key>/validate run the automatic checks
    POST /api/admin/editions/<key>/rights   {"approved": true} makes it available on the web (your decision);
                                            {"rights": …, "source": url?, "note": text?}; {"rights": null} withdraws it
    POST /api/admin/editions/<key>/run      {"exe": "GAME/START.BAT", "cycles": 20000}
    POST /api/admin/editions/<key>/delete   remove an edition (the daily sync will not bring it back)
    POST /api/admin/games/<id>/restore      {"key": …} bring back an edition removed by mistake
    GET  /api/admin/stats?days=30           usage statistics: the site, this proxy and Murray (MURRAY_URL)

Credentials: ADMIN_USER and ADMIN_PASSWORD in the environment of the games container (.env, never in the
repository); without them the panel does not exist (404). Sessions live in memory for ADMIN_SESSION_HOURS (12).
Every POST needs the header X-PCM-Admin: 1 (with SameSite=Strict, against cross-site requests); 5 failed logins
per IP lock it for 15 minutes. What you decide (which games are available, how a game starts, GOG links) goes to
catalog.admin.json next to the catalogue, which the daily sync applies on top of the sources.

Testing a commercial game here downloads it to the server for you alone; the public proxy (/api/games/) keeps
serving only editions whose rights allow it. Standard library only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import game_fetch  # noqa: E402
import ia_inspect  # noqa: E402
import stats  # noqa: E402
import sync_catalog  # noqa: E402

UI = Path(__file__).resolve().parent / "admin"
USER = os.environ.get("ADMIN_USER", "")
_salt = secrets.token_bytes(16)
_pw = hashlib.pbkdf2_hmac("sha256", os.environ.get("ADMIN_PASSWORD", "").encode(), _salt, 200_000)
ENABLED = bool(USER and os.environ.get("ADMIN_PASSWORD"))
HOURS = float(os.environ.get("ADMIN_SESSION_HOURS", "12"))
SESSIONS: dict[str, float] = {}
FAILS: dict[str, list[float]] = {}
LOCK = threading.Lock()
DOWNLOADS: deque = deque(maxlen=300)
RIGHTS = sorted(game_fetch.RIGHTS_PLAYABLE | {"commercial", "unknown"})
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,80}")
IDENT = re.compile(r"[A-Za-z0-9._-]{1,120}")
INSPECTED: dict[str, tuple[float, dict]] = {}  # identifier -> (when, report), for 15 minutes


def inspect_item(ident: str) -> dict:
    hit = INSPECTED.get(ident)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    report = ia_inspect.inspect(ident)
    INSPECTED[ident] = (time.time(), report)
    if len(INSPECTED) > 300:
        INSPECTED.pop(next(iter(INSPECTED)))
    return report


def choose(report: dict, file: str | None, exe: str | None, engine: str | None) -> tuple[dict, dict]:
    """The zip of an inspected item and how to start it: the person's choice, or what the inspection suggests."""
    zips = {z["name"]: z for z in report["zips"]}
    z = zips.get(file or report.get("best") or "")
    if not z:
        raise ValueError("choose a zip of this item")
    if engine:
        if not re.fullmatch(r"[a-z0-9_]{1,24}", engine):
            raise ValueError("bad ScummVM engine")
        return z, {"emulator": "scummvm", "run": {"svmEngine": engine}}
    if exe:
        if not re.fullmatch(r"[\w .()/\\-]{1,160}", exe):
            raise ValueError("bad program name")
        return z, {"emulator": "dosbox", "run": {"exe": exe}}
    if (z.get("scummvm") or {}).get("engine"):
        return z, {"emulator": "scummvm", "run": {"svmEngine": z["scummvm"]["engine"]}}
    if z.get("suggested"):
        return z, {"emulator": "dosbox", "run": {"exe": z["suggested"]}}
    if z.get("verdict") in ("nested", "packed"):  # only known once it is opened: trying it tells (see TRIED)
        return z, TRIED.get((report["identifier"], z["name"])) or {"emulator": "auto", "run": {}}
    raise ValueError("this zip has no program to start: choose one")


TRIED: dict[tuple[str, str], dict] = {}  # (identifier, file) -> how it ran when it was tried (for 7z and archives inside zips)
LINK = re.compile(r"archive\.org/(?:details|download|embed)/([A-Za-z0-9._-]{1,120})(?:/([^?#]+))?")


def item_ref(value: str) -> tuple[str, str | None]:
    """An Internet Archive identifier, or a link to one of its pages or files -> (identifier, file or None)."""
    value = (value or "").strip()
    m = LINK.search(value)
    if m:
        file = urllib.parse.unquote(m.group(2)).split("/")[0] if m.group(2) else None
        return m.group(1), file if file and file.lower().endswith(game_fetch.ARCHIVES) else None
    if IDENT.fullmatch(value):
        return value, None
    raise ValueError("not an Internet Archive identifier or link (https://archive.org/details/…)")


# ---------------------------------------------------------------- files
def paths(catalog: Path, cache: Path) -> dict:
    return {"catalog": catalog, "admin": sync_catalog.admin_overrides_path(catalog), "cache": cache,
            "request": catalog.with_name("sync.request.json"), "status": catalog.with_name("sync.status.json"),
            "log": catalog.with_name("sync.log"), "downloads": cache / "downloads.jsonl"}


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", "utf-8")
    os.replace(tmp, p)


def record_download(P: dict, entry: dict):
    """Every download (public or from the panel), for the panel's log of downloads and errors."""
    entry = dict(entry, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    DOWNLOADS.append(entry)
    try:
        P["cache"].mkdir(parents=True, exist_ok=True)
        with open(P["downloads"], "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent_downloads(P: dict, n: int = 200) -> list[dict]:
    try:
        lines = P["downloads"].read_text("utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines][::-1]
    except (OSError, ValueError):
        return list(DOWNLOADS)[::-1][:n]


# ---------------------------------------------------------------- catalogue edits
def find(cat: dict, key: str):
    for g in cat.get("games", []):
        for ed in g.get("editions", []):
            if ed.get("key") == key:
                return g, ed
    return None, None


def edit(P: dict, change) -> dict:
    """Applies change(catalog, admin_overrides) under a lock and writes both files (the builder rebuilds the site
    when the catalogue changes)."""
    with LOCK:
        cat = read_json(P["catalog"], {"games": []})
        ov = read_json(P["admin"], {})
        result = change(cat, ov)
        cat["counts"] = {s: sum(g["status"] == s for g in cat["games"]) for s in sync_catalog.RANK}
        write_json(P["admin"], ov)
        write_json(P["catalog"], cat)
        return result


def ov_edition(ov: dict, gid: str, key: str) -> dict:
    return ov.setdefault(gid, {}).setdefault("editions", {}).setdefault(key, {})


# ---------------------------------------------------------------- request handling
def murray_stats(days: int) -> dict:
    """Murray keeps his own numbers (his container is apart); he hands them over only inside the Docker network."""
    base = os.environ.get("MURRAY_URL", "")
    if not base:
        return {"error": "off"}
    import urllib.request
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/api/murray/stats?days={days}", timeout=5) as r:
            doc = json.loads(r.read().decode("utf-8"))
        return doc if isinstance(doc.get("days"), dict) else {"error": "bad answer"}
    except (OSError, ValueError) as e:
        return {"error": f"no answer ({type(e).__name__})"}


def cookie_token(handler) -> str:
    for part in (handler.headers.get("Cookie") or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "pcm_admin":
            return v
    return ""


def logged_in(handler) -> bool:
    tok = cookie_token(handler)
    with LOCK:
        exp = SESSIONS.get(tok)
        if exp and exp > time.time():
            return True
        SESSIONS.pop(tok, None)
    return False


def body(handler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    if n > 64 * 1024:
        raise ValueError("body too large")
    data = json.loads(handler.rfile.read(n) or b"{}")
    if not isinstance(data, dict):
        raise ValueError("expected an object")
    return data


def send(handler, code: int, obj, headers: dict | None = None):
    data = json.dumps(obj, ensure_ascii=False).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Robots-Tag", "noindex")
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(data)


def send_file(handler, path: Path, ctype: str | None = None, headers: dict | None = None):
    handler.send_response(200)
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.send_header("Content-Type", ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    handler.send_header("Content-Length", str(path.stat().st_size))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Robots-Tag", "noindex")
    handler.send_header("X-Frame-Options", "SAMEORIGIN")
    handler.end_headers()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            handler.wfile.write(chunk)


def handle(handler, method: str, P: dict) -> bool:
    """True if the request was for the panel (and has been answered)."""
    path, _, query = handler.path.partition("?")
    if not (path.startswith("/admin") or path.startswith("/api/admin/")):
        return False
    if not ENABLED:
        send(handler, 404, {"error": "the control panel is off: set ADMIN_USER and ADMIN_PASSWORD"})
        return True
    if path in ("/admin", "/admin/") or re.fullmatch(r"/admin/(admin\.js|admin\.css)", path):
        name = "index.html" if path in ("/admin", "/admin/") else path.rsplit("/", 1)[1]
        send_file(handler, UI / name, {"js": "text/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "text/html; charset=utf-8"))
        return True
    ip = handler.client_ip()
    if method == "POST" and handler.headers.get("X-PCM-Admin") != "1":
        send(handler, 403, {"error": "missing X-PCM-Admin header"})
        return True
    if path == "/api/admin/login" and method == "POST":
        now = time.time()
        with LOCK:
            fails = [t for t in FAILS.get(ip, []) if now - t < 900]
            FAILS[ip] = fails
        if len(fails) >= 5:
            send(handler, 429, {"error": "too many attempts; wait 15 minutes"})
            return True
        try:
            b = body(handler)
        except ValueError as e:
            send(handler, 400, {"error": str(e)})
            return True
        ok_user = hmac.compare_digest(str(b.get("user", "")).encode(), USER.encode())
        ok_pw = hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", str(b.get("password", "")).encode(), _salt, 200_000), _pw)
        if not (ok_user and ok_pw):
            with LOCK:
                FAILS.setdefault(ip, []).append(now)
            time.sleep(1)
            send(handler, 401, {"error": "wrong user or password"})
            return True
        tok = secrets.token_urlsafe(32)
        with LOCK:
            SESSIONS[tok] = now + HOURS * 3600
        secure = "; Secure" if os.environ.get("ADMIN_COOKIE_SECURE") == "1" or handler.headers.get("X-Forwarded-Proto") == "https" else ""
        send(handler, 200, {"user": USER}, {"Set-Cookie": f"pcm_admin={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age={int(HOURS * 3600)}{secure}"})
        return True
    if not logged_in(handler):
        send(handler, 401, {"error": "log in first"})
        return True
    try:
        route(handler, method, path, urllib.parse.parse_qs(query), P)
    except ValueError as e:
        send(handler, 400, {"error": str(e)})
    except (BrokenPipeError, ConnectionResetError):
        pass
    return True


def route(h, method: str, path: str, q: dict, P: dict):
    if path == "/api/admin/logout" and method == "POST":
        with LOCK:
            SESSIONS.pop(cookie_token(h), None)
        return send(h, 200, {"ok": True}, {"Set-Cookie": "pcm_admin=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
    if path == "/api/admin/me":
        return send(h, 200, {"user": USER, "rights": RIGHTS, "playable": sorted(game_fetch.RIGHTS_PLAYABLE),
                             "engines": sorted(game_fetch.scummvm_engines())})
    if path == "/api/admin/catalog":
        cat = read_json(P["catalog"], {"games": []})
        src = cat.get("sources", {})
        cat["removed"] = {gid: o["removedEditions"] for gid, o in read_json(P["admin"], {}).items()
                          if isinstance(o, dict) and o.get("removedEditions")}
        cat["sources"] = {"scummvm": src.get("scummvm", {}), "gog": {"at": (src.get("gog") or {}).get("at")},
                          "archive": {k: v for k, v in (src.get("archive") or {}).items() if k != "meta"}}
        return send(h, 200, cat)
    if path == "/api/admin/status":
        cache = [p for p in P["cache"].glob("*") if p.suffix in (".jsdos", ".zip")] if P["cache"].exists() else []
        log_lines = P["log"].read_text("utf-8", "replace").splitlines()[-400:] if P["log"].exists() else []
        return send(h, 200, {"sync": read_json(P["status"], {}), "requested": read_json(P["request"], None), "log": log_lines,
                             "downloads": recent_downloads(P), "cache": {"files": len(cache),
                             "mb": round(sum(p.stat().st_size for p in cache) / 1048576, 1)}})
    if path == "/api/admin/stats":
        try:
            days = max(1, min(int((q.get("days") or ["30"])[0]), 400))
        except ValueError:
            days = 30
        for st in P.get("live", ()):
            st.flush()
        raw = stats.load(P.get("stats"), days)
        murray = murray_stats(days)
        for day, docs in murray.get("days", {}).items():
            raw["days"].setdefault(day, {}).update(docs)
        out = stats.summary(raw)
        out["murray"] = "ok" if murray.get("days") is not None and "error" not in murray else murray.get("error", "off")
        out["days"] = days
        return send(h, 200, out)
    if path == "/api/admin/sync" and method == "POST":
        b = body(h)
        req = {"only": [s for s in b.get("only") or [] if s in ("scummvm", "archive", "gog")],
               "validate": max(0, min(int(b.get("validate", 20)), 500)), "retryFailed": bool(b.get("retryFailed")),
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        write_json(P["request"], req)
        return send(h, 202, {"queued": req})
    if path == "/api/admin/inspect":
        ident, linked = item_ref((q.get("archive") or [""])[0])
        try:
            return send(h, 200, dict(inspect_item(ident), linked=linked))
        except ia_inspect.InspectError as e:
            return send(h, 422, {"error": str(e)})
        except Exception as e:
            return send(h, 502, {"error": f"Internet Archive did not answer ({type(e).__name__})"})
    if path == "/api/admin/try":
        ident, _ = item_ref((q.get("archive") or [""])[0])
        arg = lambda k: (q.get(k) or [""])[0] or None
        try:
            report = inspect_item(ident)
        except Exception as e:
            return send(h, 502, {"error": f"Internet Archive did not answer ({type(e).__name__})"})
        z, how = choose(report, arg("file"), arg("exe"), arg("engine"))
        key = "try-" + hashlib.sha1(json.dumps([ident, z["name"], how], sort_keys=True).encode()).hexdigest()[:16]
        game = {"id": key, "title": report["title"], "download": {"provider": "archive", "url": z["url"], "size": z["size"] or None,
                                                                  "md5": z.get("md5"), "sha1": z.get("sha1")}, **how}
        t0 = time.time()
        try:
            r = game_fetch.prepare(game, P["cache"], admin=True)
        except Exception as e:
            record_download(P, {"key": key, "title": f"{report['title']} · {z['name']} (prueba)", "ok": False, "by": "panel", "error": str(e)[:300],
                                "network": not isinstance(e, game_fetch.GameError)})
            return send(h, 422 if isinstance(e, game_fetch.GameError) else 502, {"error": str(e)})
        record_download(P, {"key": key, "title": f"{report['title']} · {z['name']} (prueba)", "ok": True, "by": "panel",
                            "seconds": round(time.time() - t0, 1), "bytes": r.get("bytes"), "checks": r["checks"]})
        ran = {"emulator": "scummvm", "run": {"svmEngine": r.get("engine") or how["run"].get("svmEngine")}} if r["kind"] == "svm" \
            else {"emulator": "dosbox", "run": {"exe": r.get("exe")}}
        TRIED[(ident, z["name"])] = ran  # adding it after trying keeps what ran
        return send_file(h, Path(r["file"]), "application/zip", {"X-PCM-Emulator": ran["emulator"], "X-PCM-Engine": ran["run"].get("svmEngine") or "",
                                                                 "X-PCM-Exe": urllib.parse.quote(ran["run"].get("exe") or "")})
    if path == "/api/admin/search":
        title = (q.get("q") or [""])[0].strip()[:120]
        if not title:
            raise ValueError("q is empty")
        cfg = json.loads((ROOT / "data" / "catalog.sources.json").read_text("utf-8"))["archive"]
        coll = " OR ".join(cfg["collections"]) if (q.get("all") or ["0"])[0] != "1" else ""
        query = (f"collection:({coll}) AND " if coll else "mediatype:software AND ") + f'title:("{title.replace(chr(34), "")}")'
        try:
            docs = sync_catalog.ia_search(query, 50)
        except Exception as e:
            return send(h, 502, {"error": f"Internet Archive did not answer ({type(e).__name__})"})
        return send(h, 200, {"query": query, "results": [{"identifier": d["identifier"], "title": d.get("title"), "year": sync_catalog.year_of(d),
                                                          "creator": d.get("creator"), "collection": d.get("collection"),
                                                          "page": f"https://archive.org/details/{d['identifier']}",
                                                          "rights": sync_catalog.ia_rights(d)} for d in docs]})
    m = re.fullmatch(r"/api/admin/games/([a-z0-9][a-z0-9-]{0,80})/restore", path)
    if m and method == "POST":
        gid, key = m.group(1), str(body(h).get("key", ""))

        def restore(cat, ov):
            g = next((x for x in cat["games"] if x["id"] == gid), None)
            removed = (ov.get(gid) or {}).get("removedEditions") or {}
            if not g or key not in removed:
                raise ValueError("no such removed edition")
            ed = removed.pop(key)
            if not any(e["key"] == key for e in g["editions"]):
                g["editions"].append(ed)
            sync_catalog.restatus(g, ov.get(gid))
            return ed
        return send(h, 200, {"edition": edit(P, restore)})
    m = re.fullmatch(r"/api/admin/games/([a-z0-9][a-z0-9-]{0,80})(/attach)?", path)
    if m and method == "POST":
        gid, attach, b = m.group(1), m.group(2), body(h)
        if attach:
            ident, _ = item_ref(str(b.get("archive", "")))
            try:
                meta, doc = sync_catalog.ia_meta(ident), sync_catalog.http_json(f"{sync_catalog.IA}/metadata/{urllib.parse.quote(ident)}")
            except Exception as e:
                return send(h, 502, {"error": f"Internet Archive did not answer ({type(e).__name__})"})
            entry = sync_catalog.ia_entry(dict(doc.get("metadata", {}), identifier=ident), meta)
            if b.get("file") or b.get("exe") or b.get("engine"):
                report = inspect_item(ident)
                z, how = choose(report, b.get("file"), b.get("exe"), b.get("engine"))
                if how["emulator"] == "auto":
                    raise ValueError("pruébalo antes de añadirlo: hasta abrir este archivo no se sabe qué contiene")
                entry["download"] = {"provider": "archive", "file": z["name"], "size": z["size"] or None, "md5": z.get("md5"),
                                     "sha1": z.get("sha1"), "url": z["url"]}
                entry.update(how)
                stem = re.sub(r"\.zip$", "", z["name"], flags=re.I)
                many = len(report["zips"]) > 1
            else:
                stem, many = "", False
            entry["key"] = sync_catalog.add_game.slugify(f"{gid}-{entry['kind']}-{ident}" + (f"-{stem}" if many else ""))[:80].strip("-")
            entry["added"] = "panel"

            def change(cat, ov):
                g = next((x for x in cat["games"] if x["id"] == gid), None)
                if not g:
                    raise ValueError("no such game")
                adds = ov.setdefault(gid, {}).setdefault("addEditions", [])
                adds[:] = [e for e in adds if e.get("key") != entry["key"]] + [entry]
                ed = {k: entry[k] for k in ("key", "kind", "rights", "rightsHint", "emulator", "run", "edition", "download", "archive", "page", "iaTitle", "added") if entry.get(k)}
                g["editions"] = [e for e in g["editions"] if e["key"] != ed["key"]] + [ed]
                if "archive" not in g.setdefault("sources", []):
                    g["sources"].append("archive")
                sync_catalog.restatus(g)
                return ed
            return send(h, 200, {"edition": edit(P, change)})

        def change(cat, ov):
            g = next((x for x in cat["games"] if x["id"] == gid), None)
            if not g:
                raise ValueError("no such game")
            o = ov.setdefault(gid, {})
            if "gog" in b:
                if b["gog"] and not re.match(r"^https://(www\.)?gog\.com/", str(b["gog"])):
                    raise ValueError("a GOG link starts with https://www.gog.com/")
                o["gog"] = b["gog"] or None
                g["gog"] = b["gog"] or None
            if "forceRecord" in b:
                o["status"] = "record" if b["forceRecord"] else None
                sync_catalog.restatus(g, {"status": o["status"]})
            return g
        return send(h, 200, {"game": edit(P, change)})
    m = re.fullmatch(r"/api/admin/editions/([a-z0-9][a-z0-9-]{0,80})/(bundle|validate|rights|run|delete)", path)
    if not m:
        return send(h, 404, {"error": "unknown"})
    key, action = m.groups()
    cat = read_json(P["catalog"], {"games": []})
    g, ed = find(cat, key)
    if not ed:
        return send(h, 404, {"error": "no such edition"})
    if action in ("bundle", "validate"):
        if action == "validate" and method != "POST":
            return send(h, 405, {"error": "POST"})
        t0 = time.time()
        try:
            r = game_fetch.prepare({"id": key, "title": g["title"], **ed}, P["cache"], admin=True)
            record_download(P, {"key": key, "title": g["title"], "ok": True, "by": "panel", "seconds": round(time.time() - t0, 1),
                                "bytes": r.get("bytes"), "checks": r["checks"]})
        except Exception as e:  # GameError or network: shown in the panel
            record_download(P, {"key": key, "title": g["title"], "ok": False, "by": "panel", "error": str(e)[:300],
                                "network": not isinstance(e, game_fetch.GameError)})
            if action == "validate" and isinstance(e, game_fetch.GameError):
                def fail(cat, ov):
                    g2, ed2 = find(cat, key)
                    ed2["validated"] = {"ok": False, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "error": str(e)[:200], "by": "panel"}
                    sync_catalog.restatus(g2)
                edit(P, fail)
            return send(h, 422 if isinstance(e, game_fetch.GameError) else 502, {"error": str(e)})
        if action == "bundle":
            return send_file(h, Path(r["file"]), "application/zip")

        def ok(cat, ov):
            g2, ed2 = find(cat, key)
            ed2["validated"] = {"ok": True, "at": r["at"], "checks": r["checks"], "by": "panel"}
            sync_catalog.restatus(g2)
            return ed2
        return send(h, 200, {"edition": edit(P, ok), "kind": r["kind"], "files": r.get("files"), "exe": r.get("exe")})
    b = body(h)
    if action == "delete":
        def remove(cat, ov):
            g2, ed2 = find(cat, key)
            o = ov.setdefault(g2["id"], {})
            o.setdefault("removedEditions", {})[key] = {k: v for k, v in ed2.items() if k != "status"}
            o["addEditions"] = [e for e in o.get("addEditions", []) if e.get("key") != key]
            (o.get("editions") or {}).pop(key, None)
            g2["editions"] = [e for e in g2["editions"] if e["key"] != key]
            for f in P["cache"].glob(f"{key}.*"):  # its download goes too
                f.unlink(missing_ok=True)
            sync_catalog.restatus(g2, o)
            return g2
        return send(h, 200, {"game": edit(P, remove)})
    if action == "rights":
        rights = b.get("rights")
        if rights is not None and rights not in RIGHTS:
            raise ValueError(f"rights: one of {', '.join(RIGHTS)} or null")
        source = str(b.get("source") or "").strip()
        if source and not re.match(r"^https?://", source):
            raise ValueError("the optional link must start with http:// or https://")
        approved = b.get("approved")
        fields = ("rights", "rightsSource", "rightsNote", "rightsBy", "rightsAt", "approved")

        def change(cat, ov):
            g2, ed2 = find(cat, key)
            fix = ov_edition(ov, g2["id"], key)
            ed2.setdefault("rightsOriginal", ed2.get("rights"))
            if rights is None and not approved:  # withdraw: back to what the source says
                for k in fields:
                    fix.pop(k, None)
                    if k != "rights":
                        ed2.pop(k, None)
                ed2["rights"] = ed2.get("rightsOriginal") or "unknown"
            else:  # your decision: available on the web (you have done the authorisation)
                new = rights or ("permission" if ed2["rights"] not in game_fetch.RIGHTS_PLAYABLE else ed2["rights"])
                fix.update(rights=new, approved=bool(approved) if approved is not None else new in game_fetch.RIGHTS_PLAYABLE,
                           rightsBy=USER, rightsAt=time.strftime("%Y-%m-%d"))
                if source:
                    fix["rightsSource"] = source
                if b.get("note") is not None:
                    fix["rightsNote"] = str(b.get("note") or "")[:500]
                ed2.update({k: fix[k] for k in fields if k in fix})
            sync_catalog.restatus(g2, ov.get(g2["id"]))
            return ed2
        return send(h, 200, {"edition": edit(P, change)})
    if action == "run":
        run = {}
        if b.get("exe"):
            if not re.fullmatch(r"[\w .\-\\/]{1,120}", str(b["exe"])):
                raise ValueError("exe: a path inside the zip, e.g. GAME/START.BAT")
            run["exe"] = str(b["exe"])
        if b.get("cycles"):
            run["cycles"] = int(b["cycles"])
        if b.get("svmEngine"):
            run["svmEngine"] = re.sub(r"[^a-z0-9_]", "", str(b["svmEngine"]))

        def change(cat, ov):
            g2, ed2 = find(cat, key)
            new = dict(ed2.get("run") or {}, **run)
            ov_edition(ov, g2["id"], key)["run"] = new
            ed2["run"] = new
            ed2.pop("validated", None)  # it starts differently now: check it again
            for f in P["cache"].glob(f"{key}.*"):
                f.unlink(missing_ok=True)
            sync_catalog.restatus(g2, ov.get(g2["id"]))
            return ed2
        return send(h, 200, {"edition": edit(P, change)})
