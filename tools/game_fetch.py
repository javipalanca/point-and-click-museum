#!/usr/bin/env python3
"""Download, check and prepare one game of data/catalog.json for the browser (shared by the catalogue sync, which
validates new games, and the download proxy server/games.py, which prepares them when a visitor opens one).

    python3 tools/game_fetch.py <catalog-id> [--cache DIR]     # download, validate and prepare one game

Only from the hosts in ALLOWED_HOSTS and only games whose rights allow it (see RIGHTS_PLAYABLE). Checks, in order:
  size (declared and maximum) · checksum (md5/sha1 from Internet Archive's metadata, when known) · it is a valid zip
  · DOSBox: a DOS program to start (the catalogue's `run.exe`, Internet Archive's emulator_start, or the best
  guess of tools/add_game.py), not a Windows executable · ScummVM: the engine is in our ScummVM build and its data
  files are there.
Output, in the cache: <id>.jsdos (a js-dos bundle with its dosbox.conf) or <id>.svm.zip (the ScummVM game data,
without the enclosing folder), plus <id>.json with what was checked. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import add_game  # noqa: E402
from tools.jsdos import make_bundle  # noqa: E402

UA = "PointAndClickMuseum-games/1.0 (+https://github.com/javipalanca/point-and-click-museum)"
ALLOWED_HOSTS = {"downloads.scummvm.org", "archive.org"}  # and Internet Archive's servers (*.archive.org)
RIGHTS_PLAYABLE = {"freeware", "shareware", "demo", "public-domain", "open-license", "permission"}
MAX_BYTES = int(os.environ.get("GAMES_MAX_MB", "400")) * 1024 * 1024
SVM_FAMILY = {"scumm": {"scumm", "scumm_7_8"}, "sci": {"sci", "sci32"}}


class GameError(Exception):
    """A game that cannot be offered: the message says why (shown in the catalogue as the validation result)."""


def scummvm_engines() -> set[str]:
    """Engines of our ScummVM build: vendor/scummvm/ENGINES once built, else the defaults of tools/build_scummvm.sh."""
    built = Path(os.environ.get("PCM_SCUMMVM_VENDOR", ROOT / "vendor" / "scummvm")) / "ENGINES"
    if built.exists():
        return {e.strip() for e in built.read_text().split(",") if e.strip()}
    m = re.search(r'ENGINES="\$\{ENGINES:-([^}]*)\}"', (ROOT / "tools" / "build_scummvm.sh").read_text())
    return {e.strip() for e in (m.group(1) if m else "").split(",") if e.strip()}


def engine_built(engine: str) -> bool:
    have = scummvm_engines()
    return bool(SVM_FAMILY.get(engine, {engine}) & have)


def host_allowed(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    test_hosts = {h for h in os.environ.get("PCM_GAMES_TEST_HOSTS", "").split(",") if h}  # the tests' fake servers
    return url.startswith("https://") and (host in ALLOWED_HOSTS or host.endswith(".archive.org")) or host in test_hosts


def download(url: str, dest: Path, size: int | None = None) -> Path:
    """Streams a file to dest (atomic), refusing other hosts and files over MAX_BYTES."""
    if not host_allowed(url):
        raise GameError(f"host not allowed: {urllib.parse.urlparse(url).hostname}")
    if size and size > MAX_BYTES:
        raise GameError(f"too big: {size // 1048576} MB (GAMES_MAX_MB={MAX_BYTES // 1048576})")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    got = 0
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        final = r.geturl()
        if not host_allowed(final):  # a redirect to somewhere else
            raise GameError(f"redirected to a host not allowed: {urllib.parse.urlparse(final).hostname}")
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if got > MAX_BYTES:
                f.close()
                tmp.unlink(missing_ok=True)
                raise GameError(f"too big: over {MAX_BYTES // 1048576} MB")
            f.write(chunk)
    if size and got != size:
        tmp.unlink(missing_ok=True)
        raise GameError(f"size mismatch: {got} bytes, expected {size}")
    os.replace(tmp, dest)
    return dest


def check_hash(path: Path, dl: dict) -> str | None:
    for algo in ("sha1", "md5"):
        if dl.get(algo):
            h = hashlib.new(algo)
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != dl[algo].lower():
                raise GameError(f"{algo} mismatch: the file is not the one the catalogue describes")
            return algo
    return None


def read_files(path: Path) -> dict[str, bytes]:
    if not zipfile.is_zipfile(path):
        raise GameError("not a zip file")
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                raise GameError(f"damaged zip ({bad})")
            if sum(i.file_size for i in z.infolist()) > MAX_BYTES * 3:
                raise GameError("unpacks to too much data")
        return add_game.read_zip(path)
    except zipfile.BadZipFile as e:
        raise GameError(f"damaged zip ({e})") from None


def strip_folder(files: dict[str, bytes]) -> tuple[dict[str, bytes], str]:
    """Removes a single enclosing folder ('GAME/…' -> '…'), as ScummVM wants the data at --path."""
    tops = {PurePosixPath(n).parts[0] for n in files}
    if len(tops) == 1 and all(len(PurePosixPath(n).parts) > 1 for n in files):
        top = tops.pop()
        return {n[len(top) + 1:]: d for n, d in files.items()}, top
    return files, ""


def find_exe(files: dict[str, bytes], wanted: str | None, stem: str) -> str:
    if wanted:
        w = wanted.replace("\\", "/").lower()
        for n in files:
            if n.lower() == w or n.lower().endswith("/" + w):
                if add_game.is_windows_exe(files[n]):
                    raise GameError(f"{n} is a Windows program: DOSBox runs DOS programs")
                return n
        raise GameError(f"{wanted} is not in the archive")
    cands = add_game.candidates(files, stem)
    if not cands:
        if any(add_game.is_windows_exe(d) for n, d in files.items() if n.lower().endswith(".exe")):
            raise GameError("a Windows game: DOSBox runs DOS programs")
        raise GameError("no DOS program (.EXE/.COM/.BAT) to start")
    return cands[0][1]


def prepare(game: dict, cache: Path) -> dict:
    """Downloads and prepares a catalogue game. -> {"file": path, "kind": "jsdos"|"svm", "checks": [...]}"""
    gid = game["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", gid):
        raise GameError("bad id")
    if game.get("rights") not in RIGHTS_PLAYABLE:
        raise GameError(f"not authorised to run on the web (rights: {game.get('rights')})")
    dl = game.get("download") or {}
    if not dl.get("url"):
        raise GameError("no download")
    emulator = game.get("emulator", "dosbox")
    kind = "svm" if emulator == "scummvm" else "jsdos"
    out = cache / (f"{gid}.jsdos" if kind == "jsdos" else f"{gid}.svm.zip")
    report = cache / f"{gid}.json"
    stamp = dl.get("sha1") or dl.get("md5") or f"{dl['url']}|{dl.get('size')}"
    if out.exists() and report.exists():
        rep = json.loads(report.read_text("utf-8"))
        if rep.get("stamp") == stamp:
            out.touch()  # recently used (LRU)
            return dict(rep, file=str(out))
    checks = []
    if emulator == "scummvm" and not engine_built(game.get("run", {}).get("svmEngine", "")):
        raise GameError(f"ScummVM engine '{game.get('run', {}).get('svmEngine')}' is not in our build (tools/build_scummvm.sh ENGINES)")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        src = download(dl["url"], Path(tmp) / "download.zip", dl.get("size"))
        checks.append(f"downloaded {src.stat().st_size} bytes from {urllib.parse.urlparse(dl['url']).hostname}")
        algo = check_hash(src, dl)
        checks.append(f"{algo} matches" if algo else "no checksum published")
        files = read_files(src)
        checks.append(f"valid zip, {len(files)} files")
        run = game.get("run", {})
        if kind == "svm":
            data, top = strip_folder(files)
            engine, folder = add_game.detect_engine(files)
            if engine and folder:
                prefix = folder + "/"
                data = {n[len(prefix):]: d for n, d in files.items() if n.startswith(prefix)}
            checks.append(f"ScummVM engine {run.get('svmEngine')}" + (f", data in {folder or top}/" if folder or top else ""))
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for n, d in sorted(data.items()):
                    z.writestr(n, d)
            blob, extra = buf.getvalue(), {"files": sorted(data)}
        else:
            exe = find_exe(files, run.get("exe"), game.get("title", gid))
            if add_game.is_windows_exe(files[exe]):
                raise GameError(f"{exe} is a Windows program")
            checks.append(f"DOSBox runs {exe}")
            blob, extra = make_bundle(files, exe, run.get("cycles") and str(run["cycles"])), {"exe": exe}
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = Path(tmp) / out.name
        tmp_out.write_bytes(blob)
        os.replace(tmp_out, out)
    rep = {"id": gid, "kind": kind, "stamp": stamp, "checks": checks, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "bytes": out.stat().st_size, **extra}
    report.write_text(json.dumps(rep, indent=1), "utf-8")
    return dict(rep, file=str(out))


def trim_cache(cache: Path, max_mb: int) -> list[str]:
    """Least recently used bundles go first, until the cache fits in max_mb."""
    files = sorted((p for p in cache.glob("*") if p.suffix in (".jsdos", ".zip")), key=lambda p: p.stat().st_mtime)
    total, gone = sum(p.stat().st_size for p in files), []
    while files and total > max_mb * 1048576:
        p = files.pop(0)
        total -= p.stat().st_size
        p.unlink(missing_ok=True)
        gone.append(p.name)
    return gone


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("id")
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache" / "games-proxy")
    ap.add_argument("--catalog", type=Path, default=ROOT / "data" / "catalog.json")
    a = ap.parse_args()
    game = next((g for g in json.loads(a.catalog.read_text("utf-8"))["games"] if g["id"] == a.id), None)
    if not game:
        print(f"{a.id}: not in the catalogue")
        return 1
    try:
        r = prepare(game, a.cache)
    except (GameError, OSError) as e:
        print(f"{a.id}: {e}")
        return 1
    print("\n".join([f"{a.id}: ready -> {r['file']}"] + ["  · " + c for c in r["checks"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
