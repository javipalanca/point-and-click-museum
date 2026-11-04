#!/usr/bin/env python3
"""Download proxy of the DOSBox/ScummVM room: brings a game from its source the first time a visitor opens it.

    GET /api/games/health
    GET /api/games/<edition key>      -> the js-dos bundle (.jsdos) or the ScummVM data (.zip) of that edition

Why a proxy: Internet Archive and ScummVM's download server do not always let a page read their files with fetch()
(CORS), and a game must be checked and turned into a js-dos bundle with its dosbox.conf before DOSBox can run it.
Only editions of the catalogue (PCM_CATALOG, written daily by tools/sync_catalog.py) that are "playable" — rights
that allow it and the automatic checks passed — are served; anything else answers 404. It never downloads from a
host outside tools/game_fetch.ALLOWED_HOSTS, never serves a path given by the visitor, keeps at most GAMES_CACHE_MB
of games (least recently used go first) and limits how many new downloads an IP can start (GAMES_RATE per hour).

Environment: GAMES_PORT (8081), PCM_CATALOG (data/catalog.json), GAMES_CACHE (.cache/games-proxy),
GAMES_CACHE_MB (2048), GAMES_RATE (20), GAMES_TRUST_PROXY (1 behind the bundled nginx). Standard library only.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import game_fetch  # noqa: E402

log = logging.getLogger("games")
CATALOG = Path(os.environ.get("PCM_CATALOG", ROOT / "data" / "catalog.json"))
CACHE = Path(os.environ.get("GAMES_CACHE", ROOT / ".cache" / "games-proxy"))
CACHE_MB = int(os.environ.get("GAMES_CACHE_MB", "2048"))
RATE = int(os.environ.get("GAMES_RATE", "20"))
KEY = re.compile(r"^/api/games/([a-z0-9][a-z0-9-]{0,80})(?:\.(?:jsdos|zip))?$")


class Catalog:
    """The playable editions of the catalogue, reloaded when the file changes."""
    def __init__(self, path: Path):
        self.path, self.mtime, self.editions, self.lock = path, None, {}, threading.Lock()

    def get(self, key: str) -> dict | None:
        with self.lock:
            try:
                m = self.path.stat().st_mtime
            except OSError:
                return None
            if m != self.mtime:
                doc = json.loads(self.path.read_text("utf-8"))
                self.editions = {ed["key"]: {"id": ed["key"], "title": g["title"], **ed}
                                 for g in doc.get("games", []) for ed in g.get("editions", []) if ed.get("status") == "playable"}
                self.mtime = m
                log.info("catalogue loaded: %d playable editions", len(self.editions))
            return self.editions.get(key)


CAT = Catalog(CATALOG)
LOCKS: dict[str, threading.Lock] = {}
LOCKS_GUARD = threading.Lock()
HITS: dict[str, list[float]] = {}


def lock_for(key: str) -> threading.Lock:
    with LOCKS_GUARD:
        return LOCKS.setdefault(key, threading.Lock())


def allow(ip: str) -> bool:
    now = time.time()
    with LOCKS_GUARD:
        hits = [t for t in HITS.get(ip, []) if now - t < 3600]
        if len(hits) >= RATE:
            HITS[ip] = hits
            return False
        HITS[ip] = hits + [now]
        return True


def cached(ed: dict) -> Path | None:
    p = CACHE / (f"{ed['id']}.svm.zip" if ed.get("emulator") == "scummvm" else f"{ed['id']}.jsdos")
    return p if p.exists() and (CACHE / f"{ed['id']}.json").exists() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "PCMGames/1.0"

    def log_message(self, fmt, *args):
        log.info("%s %s", self.client_ip(), fmt % args)

    def client_ip(self) -> str:
        if os.environ.get("GAMES_TRUST_PROXY") == "1" and self.headers.get("X-Real-IP"):
            return self.headers["X-Real-IP"]
        return self.client_address[0]

    def send_json(self, code: int, obj: dict):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/games/health":
            return self.send_json(200, {"ok": True, "cacheMB": CACHE_MB})
        m = KEY.match(path)
        ed = CAT.get(m.group(1)) if m else None
        if not ed:
            return self.send_json(404, {"error": "not a playable game"})
        f = cached(ed)
        if not f:
            if not allow(self.client_ip()):
                return self.send_json(429, {"error": "too many new games in an hour; try again later"})
            with lock_for(ed["id"]):  # a second visitor waits for the first download instead of starting another
                f = cached(ed)
                if not f:
                    try:
                        CACHE.mkdir(parents=True, exist_ok=True)
                        f = Path(game_fetch.prepare(ed, CACHE)["file"])
                        log.info("prepared %s (%d KB)", ed["id"], f.stat().st_size // 1024)
                        game_fetch.trim_cache(CACHE, CACHE_MB)
                    except game_fetch.GameError as e:
                        log.warning("cannot prepare %s: %s", ed["id"], e)
                        return self.send_json(422, {"error": str(e)})
                    except OSError as e:  # the source is down: the visitor can try again later
                        log.warning("download of %s failed: %s", ed["id"], type(e).__name__)
                        return self.send_json(502, {"error": "the game's source did not answer; try again later"})
        f.touch()
        etag = '"%x-%x"' % (int(f.stat().st_mtime), f.stat().st_size)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(f.stat().st_size))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("ETag", etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with open(f, "rb") as fh:
            while chunk := fh.read(1 << 20):
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    srv = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("GAMES_PORT", "8081"))), Handler)
    log.info("games proxy on :%d · catalogue %s · cache %s (%d MB)", srv.server_address[1], CATALOG, CACHE, CACHE_MB)
    srv.serve_forever()


if __name__ == "__main__":
    main()
