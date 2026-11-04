#!/usr/bin/env python3
"""Games inbox: drop .zip (or .jsdos) files in a folder on the server and they appear in the DOSBox room.

    python3 tools/games_inbox.py ~/games --once                  # import what is there, build dist/ and exit
    python3 tools/games_inbox.py /inbox --site /site --watch 15  # what the Docker "builder" service runs

Every few seconds it looks at the folder (sub-folders too). When a file is new, changed or gone:
  1. each new or changed file goes through tools/add_game.py (ScummVM if it recognises the data and ScummVM is built,
     otherwise DOSBox with the best executable guess) and the result is kept in a cache, so that a game is only
     converted once;
     Then tools/identify_game.py works out which game it is (data files such as MONKEY2.000, the names of the zip
     and its folders, against the timeline and the ScummVM catalogue) for its title, year, studio and, for the
     museum's own games, their description; and finds its original box art (the museum's checked cover, or the
     PC box from libretro-thumbnails on GitHub, with its credit);
  2. the local catalogue (data/arcade.local.json, assets/games/, assets/scummvm/) gets the inbox games; games you
     added yourself with add_game.py are kept and never overwritten;
  3. the site is built again, with only these games in the DOSBox room (--all-games keeps the museum's own list).
     With --site it is built in a new folder and swapped in at once through the symlink <site>/current, so
     visitors never see a half-written site; without it, it is built into dist/.

Files still being copied are left for the next look (their size or date must stay the same between two looks).
Optional settings for one game go in a JSON file next to it with the same name (Game.zip -> Game.json):
    {"title": "My Game", "year": 1993, "studio": "Studio", "exe": "GAME/START.BAT", "cycles": 20000,
     "engine": "dosbox", "license": "Freeware", "desc": "…", "source": "https://…", "icon": "floppy", "cover": false}
("cover": false leaves the cover out; a title given here is also used to find the cover.)

Only put games there that you are allowed to share: everything in the folder is served to every visitor.
Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import add_game  # noqa: E402
import identify_game  # noqa: E402

ASSETS = ROOT / "assets"
KINDS = (".zip", ".jsdos")
OPTIONS = ("title", "year", "studio", "exe", "cycles", "engine", "license", "desc", "source", "icon", "cover")
SETTLE = 5.0  # seconds a file must stay untouched before it is imported


def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def scan(inbox: Path) -> dict[str, tuple]:
    """relative path -> (size, mtime_ns, settings text) of every game file in the inbox."""
    found = {}
    for p in sorted(inbox.rglob("*")):
        rel = p.relative_to(inbox)
        if any(part.startswith(".") for part in rel.parts) or not p.is_file() or p.suffix.lower() not in KINDS:
            continue
        side = p.with_suffix(".json")
        st = p.stat()
        found[rel.as_posix()] = (st.st_size, st.st_mtime_ns, side.read_text("utf-8") if side.is_file() else "")
    return found


def settings(text: str, name: str) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError as e:
        log(f"  {name}: settings file ignored ({e})")
        return {}
    return {k: v for k, v in data.items() if k in OPTIONS} if isinstance(data, dict) else {}


MEDIA = ROOT / "data" / "media.json"
COVER_RETRY = 86400  # a cover not found (no network, GitHub limit) is looked for again a day later


def museum_cover(timeline_id: str) -> bool:
    """The museum already shows a (checked) cover of this game: data/media.json, downloaded."""
    items = json.loads(MEDIA.read_text("utf-8"))["items"]
    return any(i["group"] == "games" and i["id"] == timeline_id and i["role"] == "cover" and i.get("file") for i in items)


def enrich(entry: dict, path: Path, opts: dict, dest: Path, cache: Path) -> dict:
    """Works out which game it is (title, year, studio, the museum's description) and finds its original cover."""
    official = {g["id"] for g in json.loads((ROOT / "data/arcade.json").read_text("utf-8"))["games"]}
    if "identified" not in entry:
        try:
            names = identify_game.zip_names(path)
        except (OSError, zipfile.BadZipFile):
            names = []
        r = identify_game.identify(names, path.stem, entry.get("svmEngine"), opts.get("title"))
        entry["identified"] = {"score": r["score"], "why": r["why"]} if r else None
        if r and entry["id"] not in official:  # official freeware zips already brought their own record
            entry["title"] = opts.get("title") or r["title"]
            entry["year"] = opts.get("year") or r.get("year")
            entry["studio"] = opts.get("studio") or r.get("studio") or entry.get("studio")
            # short, stable ids: the museum's own (kings-quest-5), else the title before its subtitle
            entry["id"] = (r.get("timeline") if not opts.get("title") else None) or add_game.slugify(
                re.split(r"[:–]| - ", entry["title"])[0].replace("'", ""))
            if r.get("timeline"):
                entry["timeline"] = r["timeline"]
                if not opts.get("desc") and r.get("desc"):
                    entry["desc"] = {lang: v["d"] for lang, v in r["desc"].items()}
                    entry.pop("autoDesc", None)
            log(f"  identified: {entry['title']} ({entry.get('year') or '?'}) from {r['why']}")
        elif not r and opts.get("title"):
            log(f"  not in the museum's lists: listed as {opts['title']} (from its .json)")
        elif not r:
            log("  not identified: listed with the name of the file (add a .json next to it to fix it)")
    if opts.get("cover") is False or entry.get("cover"):
        return entry
    if entry.get("timeline") and museum_cover(entry["timeline"]):
        entry["cover"] = {"media": f"games/{entry['timeline']}/cover"}
        return entry
    if time.time() - entry.get("coverChecked", 0) < COVER_RETRY or entry["id"] in official and not entry.get("identified"):
        return entry
    entry["coverChecked"] = int(time.time())
    try:
        spec = identify_game.find_cover(entry["title"], entry.get("year"), cache / "covers-index")
        if spec:
            meta = identify_game.fetch_cover(spec, dest / "cover.png")
            entry["cover"] = dict(meta, file="cover.png", role="cover", rights="boxart")
            log(f"  cover: {spec.rsplit('/', 1)[-1]}")
    except Exception as e:  # no network: the game works without its cover, we try again later
        log(f"  cover not available now ({type(e).__name__}: {str(e)[:80]}); trying again in a day")
    return entry


def convert(path: Path, opts: dict, cache: Path, key: str) -> dict | None:
    """Runs add_game on one file; the bundle and its catalogue entry are kept in cache/<key>/."""
    dest = cache / key
    if (dest / "entry.json").exists():
        entry = json.loads((dest / "entry.json").read_text("utf-8"))
        before = json.dumps(entry, sort_keys=True)
        entry = enrich(entry, path, opts, dest, cache)
        if json.dumps(entry, sort_keys=True) != before:
            (dest / "entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")
        return entry
    if (dest / "error.txt").exists():
        return None
    work = Path(tempfile.mkdtemp(prefix="convert-", dir=cache))
    args = SimpleNamespace(title=opts.get("title"), id=None, year=opts.get("year"), studio=opts.get("studio"),
                           license=opts.get("license", ""), desc=opts.get("desc"), source=opts.get("source"),
                           icon=opts.get("icon", "floppy"), cycles=opts.get("cycles") and str(opts["cycles"]),
                           engine=opts.get("engine", "auto"), exe=opts.get("exe"), yes=True, force=True)
    data = {"games": []}
    saved = add_game.GAMES_DIR, add_game.SVM_DIR
    add_game.GAMES_DIR, add_game.SVM_DIR = work / "games", work / "scummvm"
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            ok = add_game.add(path, args, data)
    except SystemExit as e:  # add_game stops with a message when it finds nothing to run
        ok, out = False, io.StringIO(out.getvalue() + str(e.code or "") + "\n")
    except Exception as e:  # a damaged zip must not stop the watcher
        ok, out = False, io.StringIO(out.getvalue() + f"  error: {type(e).__name__}: {e}\n")
    finally:
        add_game.GAMES_DIR, add_game.SVM_DIR = saved
    report = out.getvalue().strip()
    dest.mkdir(parents=True, exist_ok=True)
    if not ok or not data["games"]:
        (dest / "error.txt").write_text(report + "\n", "utf-8")
        shutil.rmtree(work, ignore_errors=True)
        log(f"  {path.name}: not imported\n" + "\n".join("    " + line for line in report.splitlines()[1:]))
        return None
    entry = dict(data["games"][0], inbox=True)
    for folder in ("games", "scummvm"):
        for f in (work / folder).glob("*"):
            shutil.move(str(f), dest / f.name)
            entry["bundle"] = f"{folder}/{f.name}"
    shutil.rmtree(work, ignore_errors=True)
    log("  " + (report.splitlines()[-1].strip() if report else f"{path.name}: imported"))
    entry = enrich(entry, path, opts, dest, cache)
    (dest / "entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")
    return entry


def install(entries: list[tuple[str, dict]], cache: Path) -> list[dict]:
    """Writes the inbox games into the local catalogue, keeping the games added by hand."""
    local = add_game.load_local()
    for g in local["games"]:  # remove what the inbox installed last time
        if g.get("inbox"):
            (ASSETS / g["bundle"]).unlink(missing_ok=True)
            if (g.get("cover") or {}).get("file"):
                (ASSETS / g["cover"]["file"]).unlink(missing_ok=True)
    mine = [g for g in local["games"] if not g.get("inbox")]
    taken, games = {g["id"] for g in mine} | {Path(g["bundle"]).stem for g in mine}, []
    official = {g["id"] for g in json.loads((ROOT / "data/arcade.json").read_text("utf-8"))["games"] if g.get("bundle")}
    for key, e in entries:
        gid, n = e["id"], 2
        while gid in taken or gid in official:  # two zips with the same title, or a title the museum already has
            gid, n = f"{e['id']}-{n}", n + 1
        folder, name = e["bundle"].split("/", 1)
        target = ASSETS / folder / (gid + Path(name).suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache / key / name, target)
        g = dict(e, id=gid, bundle=f"{folder}/{target.name}")
        if (e.get("cover") or {}).get("file"):  # the box art found for it, next to the bundles
            cover = ASSETS / "games" / "covers" / f"{gid}.png"
            cover.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cache / key / e["cover"]["file"], cover)
            g["cover"] = dict(e["cover"], file=f"games/covers/{gid}.png")
        games.append(g)
        taken.add(gid)
    add_game.save_local({**local, "games": mine + games})
    return games


def build(site: Path | None, extra: list[str]) -> bool:
    """Builds the site; with a site folder, into a new folder that replaces <site>/current at once."""
    cmd = [sys.executable, str(ROOT / "build.py"), *extra]
    target = None
    if site:
        site.mkdir(parents=True, exist_ok=True)
        target = site / time.strftime("build-%Y%m%d-%H%M%S")
        cmd += ["--out", str(target)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        log("build failed:\n" + (r.stderr or r.stdout)[-2000:])
        if target:
            shutil.rmtree(target, ignore_errors=True)
        return False
    if site:
        link = site / "current.new"
        link.unlink(missing_ok=True)
        link.symlink_to(target.name)
        os.replace(link, site / "current")  # atomic: nginx sees the old site or the new one, never a mix
        for old in sorted(site.glob("build-*"))[:-2]:  # keep the previous one for requests still being served
            if old != target:
                shutil.rmtree(old, ignore_errors=True)
    log((r.stdout.strip().splitlines() or ["built"])[-1])
    return True


def cache_key(rel: str, size: int, mtime: int, side: str) -> str:
    return hashlib.sha256(f"{rel}|{size}|{mtime}|{side}".encode()).hexdigest()[:20]


def sync(inbox: Path, cache: Path, site: Path | None, extra: list[str], files: dict) -> bool:
    entries, used = [], set()
    for rel, (size, mtime, side) in files.items():
        key = cache_key(rel, size, mtime, side)
        used.add(key)
        if not (cache / key).exists():
            log(f"importing {rel}")
        e = convert(inbox / rel, settings(side, rel), cache, key)
        if e:
            entries.append((key, e))
    games = install(entries, cache)
    log(f"{len(games)} game(s) from the inbox in the catalogue")
    for d in cache.iterdir():  # forget the conversions of files that left the inbox (or changed)
        if d.is_dir() and d.name not in used and not d.name.startswith("convert-"):
            shutil.rmtree(d, ignore_errors=True)
    return build(site, extra)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inbox", type=Path, help="folder where you drop the game files")
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache" / "games-inbox", help="converted games (default .cache/games-inbox)")
    ap.add_argument("--site", type=Path, help="build into <site>/build-* and point <site>/current at it (default: dist/)")
    ap.add_argument("--watch", type=float, default=15, help="seconds between looks at the folder (default 15)")
    ap.add_argument("--once", action="store_true", help="import, build and exit")
    ap.add_argument("--base-url", help="passed on to build.py")
    ap.add_argument("--catalog-every", type=float, default=0, metavar="HOURS",
                    help="also refresh the automatic catalogue (tools/sync_catalog.py) every HOURS and rebuild (0 = never)")
    ap.add_argument("--catalog-cache", type=Path, default=ROOT / ".cache" / "games-proxy",
                    help="where the catalogue sync keeps the games it validates (shared with server/games.py)")
    ap.add_argument("--all-games", action="store_true",
                    help="also list the museum's demo and the freeware it knows (default: only the games you have)")
    args = ap.parse_args()
    extra = (["--base-url", args.base_url] if args.base_url else []) + ([] if args.all_games else ["--arcade-local-only"])
    inbox, cache = args.inbox.expanduser(), args.cache.expanduser()
    inbox.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    for d in cache.glob("convert-*"):  # left over by an interrupted run
        shutil.rmtree(d, ignore_errors=True)
    log(f"games inbox: {inbox}")

    refreshed = threading.Event()
    if args.catalog_every > 0:
        def refresh_catalog():  # in the background: the inbox keeps working while the sources are read
            while True:
                log("catalogue: refreshing from ScummVM, Internet Archive and GOG")
                r = subprocess.run([sys.executable, str(ROOT / "tools" / "sync_catalog.py"), "--cache", str(args.catalog_cache)],
                                   cwd=ROOT, capture_output=True, text=True)
                for line in (r.stdout + r.stderr).strip().splitlines()[-12:]:
                    log("  " + line)
                refreshed.set()
                time.sleep(args.catalog_every * 3600)
        threading.Thread(target=refresh_catalog, daemon=True).start()

    last = done = None
    while True:
        try:
            if refreshed.is_set() and done is not None:
                refreshed.clear()
                build(args.site, extra)
            now = scan(inbox)
            if args.once:
                return 0 if sync(inbox, cache, args.site, extra, now) else 1
            settled = all(time.time() - m / 1e9 > SETTLE for _, m, _ in now.values())
            # import once nothing has moved since the last look (files still being copied wait for the next one)
            if settled and (now == last or last is None) and now != done:
                sync(inbox, cache, args.site, extra, now)
                done = now  # a failed build is tried again when the folder changes
            last = now
        except OSError as e:  # e.g. the folder is being unmounted: try again later
            log(f"cannot read the inbox ({e})")
        time.sleep(args.watch if done is not None else min(args.watch, 3))


if __name__ == "__main__":
    raise SystemExit(main())
