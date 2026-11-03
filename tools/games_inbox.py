#!/usr/bin/env python3
"""Games inbox: drop .zip (or .jsdos) files in a folder on the server and they appear in the DOSBox room.

    python3 tools/games_inbox.py ~/games --once                  # import what is there, build dist/ and exit
    python3 tools/games_inbox.py /inbox --site /site --watch 15  # what the Docker "builder" service runs

Every few seconds it looks at the folder (sub-folders too). When a file is new, changed or gone:
  1. each new or changed file goes through tools/add_game.py (ScummVM if it recognises the data and ScummVM is built,
     otherwise DOSBox with the best executable guess) and the result is kept in a cache, so that a game is only
     converted once;
  2. the local catalogue (data/arcade.local.json, assets/games/, assets/scummvm/) gets the inbox games; games you
     added yourself with add_game.py are kept and never overwritten;
  3. the site is built again. With --site it is built in a new folder and swapped in at once through the symlink
     <site>/current, so visitors never see a half-written site; without it, it is built into dist/.

Files still being copied are left for the next look (their size or date must stay the same between two looks).
Optional settings for one game go in a JSON file next to it with the same name (Game.zip -> Game.json):
    {"title": "My Game", "year": 1993, "studio": "Studio", "exe": "GAME/START.BAT", "cycles": 20000,
     "engine": "dosbox", "license": "Freeware", "desc": "…", "source": "https://…", "icon": "floppy"}

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
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import add_game  # noqa: E402

ASSETS = ROOT / "assets"
KINDS = (".zip", ".jsdos")
OPTIONS = ("title", "year", "studio", "exe", "cycles", "engine", "license", "desc", "source", "icon")
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


def convert(path: Path, opts: dict, cache: Path, key: str) -> dict | None:
    """Runs add_game on one file; the bundle and its catalogue entry are kept in cache/<key>/."""
    dest = cache / key
    if (dest / "entry.json").exists():
        return json.loads((dest / "entry.json").read_text("utf-8"))
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
    (dest / "entry.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), "utf-8")
    log("  " + (report.splitlines()[-1].strip() if report else f"{path.name}: imported"))
    return entry


def install(entries: list[tuple[str, dict]], cache: Path) -> list[dict]:
    """Writes the inbox games into the local catalogue, keeping the games added by hand."""
    local = add_game.load_local()
    for g in local["games"]:  # remove what the inbox installed last time
        if g.get("inbox"):
            (ASSETS / g["bundle"]).unlink(missing_ok=True)
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
        games.append(dict(e, id=gid, bundle=f"{folder}/{target.name}"))
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
    args = ap.parse_args()
    extra = ["--base-url", args.base_url] if args.base_url else []
    inbox, cache = args.inbox.expanduser(), args.cache.expanduser()
    inbox.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    for d in cache.glob("convert-*"):  # left over by an interrupted run
        shutil.rmtree(d, ignore_errors=True)
    log(f"games inbox: {inbox}")

    last = done = None
    while True:
        try:
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
