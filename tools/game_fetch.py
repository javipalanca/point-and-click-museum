#!/usr/bin/env python3
"""Download, check and prepare one game of data/catalog.json for the browser (shared by the catalogue sync, which
validates new games, and the download proxy server/games.py, which prepares them when a visitor opens one).

    python3 tools/game_fetch.py <catalog-id> [--cache DIR]     # download, validate and prepare one game

Only from the hosts in ALLOWED_HOSTS and only games whose rights allow it (see RIGHTS_PLAYABLE). Checks, in order:
  size (declared and maximum) · checksum (md5/sha1 from Internet Archive's metadata, when known) · it opens: a zip,
  a 7z or RAR (with the 7-Zip program, `7z`), or a CD image (.iso, read here and mounted in DOSBox as drive D:); a
  zip that holds no game but another archive (a .7z, an .iso…) is opened in turn
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
import shutil
import subprocess
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
import iso9660  # noqa: E402
from tools.jsdos import dosbox_conf, make_bundle  # noqa: E402

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


# ---------------------------------------------------------------- archives: zip, 7z / RAR, CD images
ARCHIVES = (".zip", ".7z", ".rar", ".iso")       # what may hold a game inside a zip (opened in turn)
CD_IMAGES = (".cue", ".iso", ".bin", ".img")     # CD images: .iso, .cue sheets with their .bin tracks, lone raw .bin
RAW_HEAD = 17 * 2352 + 40                         # enough of an image to recognise it (sector 16 holds the descriptor)


def sniff(path: Path) -> str | None:
    with open(path, "rb") as f:
        head = f.read(RAW_HEAD)
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if head[:4] == b"Rar!":
        return "rar"
    if iso9660.is_iso(head) or iso9660.raw_mode(head):
        return "cd"
    return None


def seven_zip() -> str | None:
    return next((b for b in ("7z", "7zz", "7za") if shutil.which(b)), None)


def unpack_7z(path: Path, work: Path) -> dict[str, bytes]:
    """A 7z or RAR file, opened with the 7-Zip program (Python's library cannot read them)."""
    exe = seven_zip()
    if not exe:
        raise GameError("this game comes as 7z/RAR: the 7-Zip program (7z) is needed on the server "
                        "(apt install p7zip-full, or brew install sevenzip)")
    listed = subprocess.run([exe, "l", "-slt", "-ba", str(path)], capture_output=True, text=True, timeout=120)
    if listed.returncode != 0:
        raise GameError("damaged or unsupported 7z/RAR archive" + (" (RAR needs a 7-Zip build with RAR support)" if path.suffix.lower() == ".rar" else ""))
    total = sum(int(m) for m in re.findall(r"^Size = (\d+)", listed.stdout, re.M))
    if total > MAX_BYTES * 3:
        raise GameError("unpacks to too much data")
    out = work / ("x-" + path.stem)
    out.mkdir(parents=True, exist_ok=True)
    done = subprocess.run([exe, "x", "-y", "-bd", f"-o{out}", str(path)], capture_output=True, text=True, timeout=900)
    if done.returncode != 0:
        raise GameError("could not unpack the 7z/RAR archive")
    files = read_folder(out)
    shutil.rmtree(out, ignore_errors=True)
    return files


def read_folder(folder: Path) -> dict[str, bytes]:
    files, base = {}, folder.resolve()
    for f in sorted(folder.rglob("*")):
        if f.is_symlink() or not f.is_file() or base not in f.resolve().parents:
            continue
        files[f.relative_to(folder).as_posix()] = f.read_bytes()
    return files


class CD:
    """A CD image on disk: an .iso, a .cue sheet with its .bin tracks, or a lone raw .bin / .img.
    DOSBox mounts it as drive D: (imgmount, CD audio included); ScummVM, which cannot read images, gets its files and
    its audio tracks as trackNN.wav (what ScummVM looks for: backends/audiocd/default/default-audiocd.cpp)."""

    def __init__(self, path: Path):
        self.path, self.tracks = path, []
        if path.suffix.lower() == ".cue":
            self.tracks = iso9660.parse_cue(path.read_text("latin-1"))
            for t in self.tracks:
                t["path"] = self._sibling(t["file"])
            data = iso9660.data_track(self.tracks)
            if not data:
                raise GameError(f"{path.name}: the cue sheet has no data track")
            self.data, self.mode, self.start = data["path"], data["mode"], data["start"]
        else:
            with open(path, "rb") as f:
                head = f.read(RAW_HEAD)
            self.mode = "MODE1/2048" if iso9660.is_iso(head) else iso9660.raw_mode(head)
            if not self.mode:
                raise GameError(f"{path.name} is not a CD image")
            self.data, self.start = path, 0

    def _sibling(self, name: str) -> Path:
        want = PurePosixPath(name.replace("\\", "/")).name.lower()
        for f in self.path.parent.iterdir():
            if f.name.lower() == want:
                return f
        raise GameError(f"{self.path.name} needs {name}, which is not there")

    def reader(self):
        return iso9660.track_reader(iso9660.file_reader(self.data), self.mode, self.start)

    def listing(self) -> list[dict]:
        try:
            return iso9660.listing(self.reader())
        except iso9660.IsoError as e:
            raise GameError(f"CD image: {e}") from None

    def files(self) -> dict[str, bytes]:
        read = self.reader()
        return {e["name"]: iso9660.read_file(read, e) for e in self.listing()}

    def audio(self) -> dict[str, bytes]:
        """The CD-DA tracks as trackNN.wav (44.1 kHz, 16 bits, stereo, as on the disc)."""
        import wave
        out = {}
        for i, t in enumerate(self.tracks):
            if t["mode"] != "AUDIO":
                continue
            nxt = next((x for x in self.tracks[i + 1:] if x["path"] == t["path"]), None)
            with open(t["path"], "rb") as f:
                f.seek(t["start"] * 2352)
                pcm = f.read((nxt["start"] - t["start"]) * 2352) if nxt else f.read()
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(pcm)
            out[f"track{t['number']:02d}.wav"] = buf.getvalue()
        return out

    def describe(self) -> str:
        audio = sum(t["mode"] == "AUDIO" for t in self.tracks)
        return ("CD image " + ("(ISO 9660)" if self.mode == "MODE1/2048" and not self.tracks else f"({self.mode}"
                + (f", {audio} audio tracks" if audio else "") + ")"))

    def bundle(self) -> tuple[dict[str, Path | bytes], str]:
        """The files to put in a js-dos bundle and the name DOSBox mounts: cd.iso, or cd.cue with cdNN.bin."""
        if not self.tracks and self.mode == "MODE1/2048":
            return {"cd.iso": self.data}, "cd.iso"
        tracks = self.tracks or [{"path": self.data, "number": 1, "mode": self.mode, "start": 0}]
        names, cue = {}, []
        for t in tracks:
            if t["path"] not in names:
                names[t["path"]] = f"cd{len(names) + 1:02d}.bin"
                cue.append(f'FILE "{names[t["path"]]}" BINARY')
            s = t["start"]
            cue += [f"  TRACK {t['number']:02d} {t['mode']}", f"    INDEX 01 {s // 4500:02d}:{s // 75 % 60:02d}:{s % 75:02d}"]
        return {"cd.cue": ("\r\n".join(cue) + "\r\n").encode(), **{n: p for p, n in names.items()}}, "cd.cue"


def split_cd(files: dict[str, bytes], work: Path) -> tuple[dict[str, bytes], CD | None]:
    """Takes a CD image out of the files of an archive (written to disk: it can be large) -> (the rest, the CD)."""
    lower = {n.lower(): n for n in files}
    picks = []
    for cue in sorted(n for n in files if n.lower().endswith(".cue")):
        folder = str(PurePosixPath(cue).parent)
        prefix = "" if folder == "." else folder + "/"
        try:
            parts = [lower.get((prefix + PurePosixPath(t["file"].replace("\\", "/")).name).lower())
                     for t in iso9660.parse_cue(files[cue].decode("latin-1"))]
        except (ValueError, IndexError):
            continue
        if parts and all(parts):
            picks = [cue] + sorted(set(parts))
            break
    if not picks:
        images = sorted((n for n in files if n.lower().endswith((".iso", ".bin", ".img"))), key=lambda n: -len(files[n]))
        picks = next(([n] for n in images if iso9660.is_iso(files[n][:RAW_HEAD]) or iso9660.raw_mode(files[n][:RAW_HEAD])), [])
    if not picks:
        return files, None
    folder = work / "cd"
    folder.mkdir(parents=True, exist_ok=True)
    for n in picks:
        (folder / PurePosixPath(n).name).write_bytes(files.pop(n))
    return files, CD(folder / PurePosixPath(picks[0]).name)


def has_game(files: dict[str, bytes]) -> bool:
    return bool(add_game.candidates(files, "") or add_game.detect_engine(files)[0])


def unpack(path: Path, work: Path, depth: int = 0) -> tuple[dict[str, bytes], CD | None, str]:
    """(files for drive C:, a CD image for drive D:, how it was opened). `path` may be a folder (a cue sheet and its
    tracks, downloaded as separate files). A zip that holds no game but another archive is opened in turn."""
    if path.is_dir():
        cue = next((f for f in sorted(path.iterdir()) if f.suffix.lower() == ".cue"), None)
        if cue:
            cd = CD(cue)
            return {}, cd, cd.describe()
        files, how = read_folder(path), "files"
    else:
        kind = sniff(path)
        if kind == "zip":
            files, how = read_files(path), "valid zip"
        elif kind in ("7z", "rar"):
            files, how = unpack_7z(path, work), f"{kind} archive"
        elif kind == "cd":
            cd = CD(path)
            return {}, cd, cd.describe()
        else:
            raise GameError("not a zip, 7z, RAR or CD image")
    files, cd = split_cd(files, work)
    inner = sorted((n for n in files if n.lower().endswith((".zip", ".7z", ".rar"))), key=lambda n: -len(files[n]))
    if depth < 2 and inner and not has_game(files) and not cd:  # e.g. a zip with the manual, a cover and the game as .7z
        nested = work / f"inner{depth}{PurePosixPath(inner[0]).suffix.lower()}"
        nested.write_bytes(files[inner[0]])
        files.clear()
        sub, sub_cd, sub_how = unpack(nested, work, depth + 1)
        return sub, sub_cd, f"{how}, with {PurePosixPath(inner[0]).name} inside ({sub_how})"
    return files, cd, how + f", {len(files)} files" + (f" and a {cd.describe()}" if cd else "")


class Head(bytes):
    """The first bytes of a file, with the size of the whole file (what add_game.candidates looks at)."""
    def __new__(cls, data: bytes, size: int):
        obj = super().__new__(cls, data)
        obj.full = size
        return obj

    def __len__(self):
        return self.full


def cd_programs(cd: CD) -> tuple[dict[str, bytes], list[dict]]:
    """The programs of a CD image (their first 4 KB, to tell DOS from Windows) and its whole listing."""
    read, entries = cd.reader(), cd.listing()
    progs = {e["name"]: Head(iso9660.read_file(read, e, 4096) or b"MZ", e["size"]) for e in entries
             if PurePosixPath(e["name"]).suffix.lower() in add_game.RUNNABLE}
    return progs, entries


def cd_bundle(files: dict[str, bytes], cd: CD, exe: str, on_cd: bool, cycles: str | None, out: Path):
    """A js-dos bundle: the files as drive C: and the CD image mounted as D:, starting the game from where it is."""
    parts = [p for p in exe.replace("/", "\\").split("\\") if p]
    extra, mount = cd.bundle()
    autoexec = [f"imgmount d {mount} -t iso"] + (["d:"] if on_cd else []) + \
               (["cd \\" + "\\".join(parts[:-1])] if len(parts) > 1 else []) + [parts[-1]]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        z.writestr(".jsdos/dosbox.conf", dosbox_conf(None, cycles, autoexec))
        z.writestr(".jsdos/jsdos.json", json.dumps({"version": "js-dos-v8"}, indent=2))
        for name, data in sorted(files.items()):
            z.writestr(str(PurePosixPath(name)), data)
        for name, item in extra.items():
            z.write(item, name) if isinstance(item, Path) else z.writestr(name, item)


def detected(ed: dict, r: dict) -> bool:
    """After a check: an edition listed for DOSBox that turned out to be ScummVM data is played with ScummVM from now
    on (ScummVM first, always). Kept in the edition as "detected" so that the daily sync does not undo it."""
    if r.get("kind") != "svm" or ed.get("emulator") == "scummvm":
        return False
    ed["detected"] = {"emulator": "scummvm", "run": {"svmEngine": r["engine"]}}
    ed["emulator"], ed["run"] = "scummvm", {"svmEngine": r["engine"]}
    return True


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


def prepare(game: dict, cache: Path, admin: bool = False, switch: bool = False) -> dict:
    """Downloads and prepares a catalogue game. -> {"file": path, "kind": "jsdos"|"svm", "checks": [...]}
    admin=True (the control panel, behind its password): also editions whose rights are not confirmed, so that a
    person can test them before deciding; the public proxy never serves those.
    ScummVM first, always: with emulator "auto" (a 7z, an archive inside a zip: known only once open), or with
    switch=True (checks by the sync and the panel, which then record it with `detected`), ScummVM data whose engine is
    in our build is played with ScummVM even if there is also a DOS program; DOSBox otherwise. The public proxy
    (switch=False) keeps to what the edition says. The result says which ("kind", "engine")."""
    gid = game["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", gid):
        raise GameError("bad id")
    if not admin and not game.get("approved") and game.get("rights") not in RIGHTS_PLAYABLE:
        raise GameError(f"not authorised to run on the web (rights: {game.get('rights')})")
    dl = game.get("download") or {}
    if not dl.get("url") and not dl.get("parts"):
        raise GameError("no download")
    emulator = game.get("emulator", "dosbox")
    kind = "svm" if emulator == "scummvm" else "jsdos"
    output = lambda k: cache / (f"{gid}.jsdos" if k == "jsdos" else f"{gid}.svm.zip")
    report = cache / f"{gid}.json"
    stamp = dl.get("sha1") or dl.get("md5") or "|".join(f"{p['url']}|{p.get('size')}" for p in (dl.get("parts") or [dl]))
    if report.exists():
        rep = json.loads(report.read_text("utf-8"))
        done = output(rep.get("kind"))
        if rep.get("stamp") == stamp and done.exists() and (emulator == "auto" or switch or rep.get("kind") == kind):
            done.touch()  # recently used (LRU)
            return dict(rep, file=str(done))
    checks = []
    if emulator == "scummvm" and not engine_built(game.get("run", {}).get("svmEngine", "")):
        raise GameError(f"ScummVM engine '{game.get('run', {}).get('svmEngine')}' is not in our build (tools/build_scummvm.sh ENGINES)")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        if dl.get("parts"):  # a cue sheet and its tracks, published as separate files
            if sum(int(p.get("size") or 0) for p in dl["parts"]) > MAX_BYTES:
                raise GameError(f"too big: over {MAX_BYTES // 1048576} MB (GAMES_MAX_MB)")
            src = Path(tmp) / "parts"
            for p in dl["parts"]:
                name = PurePosixPath(p["name"].replace("\\", "/")).name
                if not re.fullmatch(r"[\w .()\[\]&',+-]{1,160}", name):
                    raise GameError(f"bad file name: {name}")
                f = download(p["url"], src / name, p.get("size"))
                check_hash(f, p)
            checks.append(f"downloaded {len(dl['parts'])} files ({sum(f.stat().st_size for f in src.iterdir())} bytes) "
                          f"from {urllib.parse.urlparse(dl['parts'][0]['url']).hostname}")
        else:
            src = download(dl["url"], Path(tmp) / "download.bin", dl.get("size"))
            checks.append(f"downloaded {src.stat().st_size} bytes from {urllib.parse.urlparse(dl['url']).hostname}")
            algo = check_hash(src, dl)
            checks.append(f"{algo} matches" if algo else "no checksum published")
        files, cd, how = unpack(src, Path(tmp))
        checks.append(how)
        run = dict(game.get("run", {}))
        cd_list = cd.listing() if cd else []
        if emulator == "auto" or (switch and emulator != "scummvm"):  # ScummVM first, if it can
            names = dict(files, **{e["name"]: b"" for e in cd_list})
            engine = add_game.detect_engine(names)[0] if names else None
            dos = bool(run.get("exe") or add_game.candidates(files, "") or (cd and cd_programs(cd)[0] and add_game.candidates(cd_programs(cd)[0], "")))
            if engine and engine_built(engine):
                kind, run = "svm", {"svmEngine": engine}
            elif engine and not dos:
                raise GameError(f"ScummVM data (engine '{engine}'), but that engine is not in our build (tools/build_scummvm.sh ENGINES)")
            checks.append("contents: " + (f"ScummVM data, engine {engine}" if kind == "svm" else "a DOS game")
                          + (f" (ScummVM engine '{engine}' is not in our build: DOSBox)" if engine and kind != "svm" else ""))
        out = output(kind)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp_out = Path(tmp) / out.name
        if kind == "svm":
            audio = cd.audio() if cd else {}
            if cd:  # ScummVM cannot read CD images: their files, and the CD's music as trackNN.wav
                files = dict(files, **cd.files())
            data, top = strip_folder(files)
            engine, folder = add_game.detect_engine(files)
            if engine and folder:
                prefix = folder + "/"
                data = {n[len(prefix):]: d for n, d in files.items() if n.startswith(prefix)}
            data.update(audio)
            checks.append(f"ScummVM engine {run.get('svmEngine')}" + (f", data in {folder or top}/" if folder or top else "")
                          + (f", {len(audio)} CD audio tracks" if audio else ""))
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as z:
                for n, d in sorted(data.items()):
                    z.writestr(n, d)
            extra = {"files": sorted(data), "engine": run.get("svmEngine")}
        elif cd:
            progs = cd_programs(cd)[0]
            on_cd = False
            if run.get("exe"):
                try:
                    exe = find_exe(files, run["exe"], game.get("title", gid))
                except GameError:
                    exe, on_cd = find_exe(progs, run["exe"], game.get("title", gid)), True
            elif add_game.candidates(files, game.get("title", gid)):
                exe = find_exe(files, None, game.get("title", gid))
            else:
                exe, on_cd = find_exe(progs, None, game.get("title", gid)), True
            checks.append(f"{cd.describe()} with {len(cd_list)} files, mounted as D:; DOSBox runs "
                          + ("D:\\" if on_cd else "C:\\") + exe.replace("/", "\\"))
            cd_bundle(files, cd, exe, on_cd, run.get("cycles") and str(run["cycles"]), tmp_out)
            extra = {"exe": exe, "cd": True, "onCd": on_cd}
        else:
            exe = find_exe(files, run.get("exe"), game.get("title", gid))
            if add_game.is_windows_exe(files[exe]):
                raise GameError(f"{exe} is a Windows program")
            checks.append(f"DOSBox runs {exe}")
            tmp_out.write_bytes(make_bundle(files, exe, run.get("cycles") and str(run["cycles"])))
            extra = {"exe": exe}
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
