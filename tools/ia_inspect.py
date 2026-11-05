#!/usr/bin/env python3
"""What is inside an Internet Archive item, before adding it to the catalogue.

    python3 tools/ia_inspect.py <identifier>

For each zip of the item it reads only the zip's index (the central directory at the end of the file, with HTTP
range requests) and the first bytes of each program, never the whole download; for a CD image (.iso) its directory
tree, the same way (tools/iso9660.py). A 7z or RAR cannot be listed without downloading it: it is marked "packed" and
opened when it is tried (tools/game_fetch.py, with the 7-Zip program). From that:

  · ScummVM data (the same file signatures as tools/add_game.py), and whether that engine is in our build;
  · DOS programs (.EXE/.COM/.BAT), Windows programs (PE header) and installers, with the one most likely to start
    the game first (the same ranking as add_game.candidates);
  · a verdict: dosbox, scummvm, windows (DOSBox cannot run it), nested (another archive inside the zip: a .7z,
    an .iso…), packed (a 7z/RAR), none, too-big.

Other files (BIN/CUE, disk images) are listed but not usable yet. Used by the control panel
(GET /api/admin/inspect) so that a person sees what an item holds, tries it and only then adds it.
Standard library only."""
from __future__ import annotations

import json
import re
import struct
import sys
import urllib.parse
import urllib.request
import zlib
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import add_game  # noqa: E402
import game_fetch  # noqa: E402
import iso9660  # noqa: E402
import sync_catalog  # noqa: E402

TAIL = 65536 + 22           # the end-of-central-directory record is within the last 64 KB
HEAD = 4096                 # bytes of each program read to tell DOS from Windows
MAX_PROGRAMS = 16           # programs whose header is read, per zip
MAX_ZIPS = 4                # zips looked at per item (largest first)
OTHER = re.compile(r"\.(ima|dsk|adf|d64|st|mdf|mds|nrg|ccd|chd)$", re.I)


class InspectError(Exception):
    pass


def ranged(url: str, start: int | None, end: int | None, limit: int) -> bytes:
    """Bytes start..end (inclusive) of a remote file; start=None asks for the last `end` bytes."""
    if not game_fetch.host_allowed(url):
        raise InspectError(f"host not allowed: {urllib.parse.urlparse(url).hostname}")
    rng = f"bytes=-{end}" if start is None else f"bytes={start}-{end}"
    req = urllib.request.Request(url, headers={"User-Agent": game_fetch.UA, "Range": rng})
    with urllib.request.urlopen(req, timeout=60) as r:
        if not game_fetch.host_allowed(r.geturl()):
            raise InspectError("redirected to a host not allowed")
        data = r.read(limit + 1)
        if r.status != 206 and len(data) > limit:
            raise InspectError("the server does not answer partial requests")
    return data[:limit]


def central_directory(url: str, size: int) -> list[dict]:
    """The entries of a remote zip: name, size, compressed size, method, offset of its local header."""
    tail = ranged(url, None, min(TAIL, size), TAIL)
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise InspectError("not a zip (no end of central directory)")
    count, cd_size, cd_off = struct.unpack("<HII", tail[i + 10:i + 20])
    if cd_off == 0xFFFFFFFF or count == 0xFFFF:  # zip64: its own record comes just before
        j = tail.rfind(b"PK\x06\x06", 0, i)
        if j < 0:
            raise InspectError("zip64 without its record")
        count, cd_size, cd_off = struct.unpack("<QQQ", tail[j + 32:j + 56])
    if cd_size > 8 << 20:
        raise InspectError("index too large")
    start = size - len(tail)
    cd = tail[cd_off - start:cd_off - start + cd_size] if cd_off >= start else ranged(url, cd_off, cd_off + cd_size - 1, cd_size)
    out, p = [], 0
    while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02" and len(out) < count:
        # central directory entry: flags @8, method @10, sizes @20/@24, name/extra/comment lengths @28, local offset @42
        flags, method = struct.unpack("<HH", cd[p + 8:p + 12])
        csize, usize = struct.unpack("<II", cd[p + 20:p + 28])
        nl, xl, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        off = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + nl].decode("utf-8" if flags & 0x800 else "cp437", "replace").replace("\\", "/")
        if 0xFFFFFFFF in (csize, usize, off):  # zip64 extra field
            extra, q, vals = cd[p + 46 + nl:p + 46 + nl + xl], 0, []
            while q + 4 <= len(extra):
                hid, hl = struct.unpack("<HH", extra[q:q + 4])
                if hid == 1:
                    vals = list(struct.unpack(f"<{hl // 8}Q", extra[q + 4:q + 4 + hl // 8 * 8]))
                q += 4 + hl
            if usize == 0xFFFFFFFF and vals:
                usize = vals.pop(0)
            if csize == 0xFFFFFFFF and vals:
                csize = vals.pop(0)
            if off == 0xFFFFFFFF and vals:
                off = vals.pop(0)
        if not name.endswith("/") and not name.startswith("__MACOSX/"):
            out.append({"name": name, "size": usize, "csize": csize, "method": method, "offset": off})
        p += 46 + nl + xl + cl
    return out


def head(url: str, e: dict) -> bytes:
    """The first bytes of one file of a remote zip (stored or deflated)."""
    want = min(e["csize"], HEAD * 2) + 30 + 1024
    data = ranged(url, e["offset"], e["offset"] + want - 1, want)
    if data[:4] != b"PK\x03\x04":
        return b""
    nl, xl = struct.unpack("<HH", data[26:30])
    body = data[30 + nl + xl:]
    if e["method"] == 0:
        return body[:HEAD]
    if e["method"] == 8:
        try:
            return zlib.decompressobj(-15).decompress(body, HEAD)
        except zlib.error:
            return b""
    return b""


Head = game_fetch.Head


def look_at_zip(url: str, size: int, title: str, start: str | None) -> dict:
    entries = central_directory(url, size)
    out = analyse(entries, lambda e: head(url, e), title, start)
    if out["verdict"] in ("dosbox", "scummvm"):
        return out
    cd = cd_in_zip(url, entries, title, start)  # a CD image inside the zip (.cue + .bin, .iso)
    return dict(out, **cd) if cd else out


def member_reader(url: str, e: dict):
    """Random access to a file stored (not compressed) inside a remote zip: where its bytes start, then ranges."""
    local = ranged(url, e["offset"], e["offset"] + 29, 30)
    nl, xl = struct.unpack("<HH", local[26:30])
    base = e["offset"] + 30 + nl + xl
    return lambda off, n: ranged(url, base + off, base + off + n - 1, n)


def cd_in_zip(url: str, entries: list[dict], title: str, start: str | None) -> dict | None:
    by_name = {e["name"].lower(): e for e in entries}
    image, mode, first, audio, note = None, None, 0, 0, None
    for e in entries:
        if e["name"].lower().endswith(".cue"):
            try:
                tracks = iso9660.parse_cue(head(url, e).decode("latin-1"))
            except Exception:
                continue
            folder = str(PurePosixPath(e["name"]).parent)
            prefix = "" if folder == "." else folder + "/"
            data = iso9660.data_track(tracks)
            bin_entry = data and by_name.get((prefix + PurePosixPath(data["file"].replace("\\", "/")).name).lower())
            if bin_entry:
                image, mode, first, audio, note = bin_entry, data["mode"], data["start"], sum(t["mode"] == "AUDIO" for t in tracks), e["name"]
                break
    if not image:
        isos = [e for e in entries if e["name"].lower().endswith((".iso", ".bin", ".img"))]
        if not isos:
            return None
        image = max(isos, key=lambda e: e["size"])
        note = image["name"]
    if image["method"] != 0:  # compressed inside the zip: it cannot be read in place, trying it opens it
        return {"verdict": "nested", "inner": [note]}
    read_raw = member_reader(url, image)
    if mode is None:
        headb = read_raw(0, game_fetch.RAW_HEAD)
        mode = "MODE1/2048" if iso9660.is_iso(headb) else iso9660.raw_mode(headb)
        if not mode:
            return None
    read = iso9660.track_reader(read_raw, mode, first)
    out = analyse(iso9660.listing(read), lambda e: iso9660.read_file(read, e, HEAD), title, start)
    return dict(out, cd=True, cdInZip=note, audioTracks=audio)


def look_at_iso(url: str, title: str, start: str | None) -> dict:
    read = lambda off, n: ranged(url, off, off + n - 1, n)
    out = analyse(iso9660.listing(read), lambda e: iso9660.read_file(read, e, HEAD), title, start)
    out["cd"] = True  # DOSBox mounts it as drive D:
    return out


def analyse(entries: list[dict], first_bytes, title: str, start: str | None) -> dict:
    names = [e["name"] for e in entries]
    out = {"files": len(entries), "sample": sorted(names, key=lambda n: (n.count("/"), n.lower()))[:12]}
    # ScummVM data, by file names (as add_game.detect_engine, without reading them)
    by_dir: dict[str, set] = {}
    for n in names:
        p = PurePosixPath(n)
        by_dir.setdefault(str(p.parent) if str(p.parent) != "." else "", set()).add(p.name.lower())
    for engine, test in add_game.SCUMMVM_SIGNATURES:
        hit = next((d for d, ns in sorted(by_dir.items(), key=lambda kv: kv[0].count("/")) if test(ns)), None)
        if hit is not None:
            out["scummvm"] = {"engine": engine, "folder": hit, "built": game_fetch.engine_built(engine)}
            break
    # programs: DOS or Windows (their header), installers, and the likely one to start the game
    progs = [e for e in entries if PurePosixPath(e["name"]).suffix.lower() in add_game.RUNNABLE]
    progs.sort(key=lambda e: (e["name"].count("/"), bool(add_game.NOT_THE_GAME.match(PurePosixPath(e["name"]).name)), -e["size"]))
    files, programs = {}, []
    for i, e in enumerate(progs):
        suffix = PurePosixPath(e["name"]).suffix.lower()
        data = b""
        if suffix == ".exe" and i < MAX_PROGRAMS:
            try:
                data = first_bytes(e)
            except Exception:  # network trouble on one program: it stays "unknown"
                data = b""
        # an .EXE without the MZ header is loaded by DOS as a .COM image: still a DOS program
        kind = ("windows" if add_game.is_windows_exe(data) else "dos" if data else "unknown") if suffix == ".exe" else "dos"
        files[e["name"]] = Head(data or b"MZ", e["size"]) if kind != "windows" else Head(data, e["size"])
        programs.append({"path": e["name"], "size": e["size"], "type": kind,
                         "installer": bool(add_game.NOT_THE_GAME.match(PurePosixPath(e["name"]).name))})
    ranked = [n for _, n in add_game.candidates(files, title)]
    if start:  # what the item's own emulator starts (Internet Archive's metadata), when it is in the zip
        s = start.replace("\\", "/").lower()
        ranked = [n for n in ranked if n.lower() == s or n.lower().endswith("/" + s)] + [n for n in ranked if not (n.lower() == s or n.lower().endswith("/" + s))]
    order = {n: i for i, n in enumerate(ranked)}
    programs.sort(key=lambda x: (order.get(x["path"], 999), x["path"]))
    out["programs"] = programs[:40]
    out["suggested"] = ranked[0] if ranked else None
    inner = [n for n in names if n.lower().endswith(game_fetch.ARCHIVES + (".cue",))]
    if out.get("scummvm"):
        out["verdict"] = "scummvm"
    elif ranked:
        out["verdict"] = "dosbox"
    elif any(p["type"] == "windows" for p in programs):
        out["verdict"] = "windows"
    elif inner:
        out["verdict"], out["inner"] = "nested", inner[:5]
    else:
        out["verdict"] = "none"
    return out


def look_at_cd(url: str, mode: str, start: int, title: str, emu_start: str | None) -> dict:
    """The data track of a raw image (or an .iso), read remotely sector by sector."""
    read = iso9660.track_reader(lambda off, n: ranged(url, off, off + n - 1, n), mode, start)
    out = analyse(iso9660.listing(read), lambda e: iso9660.read_file(read, e, HEAD), title, emu_start)
    out["cd"] = True  # DOSBox mounts it as drive D:; ScummVM gets its files
    return out


def inspect(ident: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", ident):
        raise InspectError("bad Internet Archive identifier")
    meta = sync_catalog.http_json(f"{sync_catalog.IA}/metadata/{urllib.parse.quote(ident)}")
    md = meta.get("metadata") or {}
    if not md:
        raise InspectError("no such item")
    title = str(sync_catalog.as_list(md.get("title"))[0] if md.get("title") else ident)
    emu_start = md.get("emulator_start")
    files = [f for f in meta.get("files", []) if f.get("source") != "metadata" or str(f.get("name", "")).lower().endswith(".zip")]
    url = lambda name: f"{sync_catalog.IA}/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(name)}"
    part = lambda f: {"name": f["name"], "size": int(f.get("size") or 0), "md5": f.get("md5"), "sha1": f.get("sha1"), "url": url(f["name"])}
    by_name = {PurePosixPath(str(f.get("name", ""))).name.lower(): f for f in files}
    report = {"identifier": ident, "title": title, "page": f"https://archive.org/details/{ident}",
              "year": sync_catalog.year_of(md), "creator": md.get("creator"), "rights": sync_catalog.ia_rights(md),
              "start": emu_start, "zips": [],
              "other": [{"name": f["name"], "size": int(f.get("size") or 0)} for f in files if OTHER.search(str(f.get("name", "")))][:10]}

    # CD images published as a cue sheet and its tracks (.bin): one candidate with all its parts
    in_cues: set[str] = set()
    for f in [f for f in files if str(f.get("name", "")).lower().endswith(".cue")][:MAX_ZIPS]:
        z = {"name": f["name"], "kind": "cue", "url": url(f["name"]), "size": int(f.get("size") or 0)}
        try:
            size = int(f.get("size") or 0)
            tracks = iso9660.parse_cue(ranged(z["url"], 0, max(size, 1) - 1, 65536).decode("latin-1"))
            bins = []
            for t in tracks:
                g = by_name.get(PurePosixPath(t["file"].replace("\\", "/")).name.lower())
                if not g:
                    raise InspectError(f"the cue sheet needs {t['file']}, which is not in the item")
                if g not in bins:
                    bins.append(g)
            in_cues.update(str(g["name"]) for g in bins)
            z["parts"] = [part(f)] + [part(g) for g in bins]
            z["size"] = sum(p["size"] for p in z["parts"])
            z["audioTracks"] = sum(t["mode"] == "AUDIO" for t in tracks)
            data = iso9660.data_track(tracks)
            if z["size"] > game_fetch.MAX_BYTES:
                z["verdict"] = "too-big"
            elif not data:
                z["verdict"] = "none"
            else:
                z.update(look_at_cd(url(by_name[PurePosixPath(data["file"].replace("\\", "/")).name.lower()]["name"]),
                                    data["mode"], data["start"], title, emu_start))
        except Exception as e:  # one image that cannot be read does not hide the rest
            z["verdict"], z["error"] = "error", f"{type(e).__name__}: {e}"[:200]
        report["zips"].append(z)

    candidates = [f for f in files if str(f.get("name", "")).lower().endswith(game_fetch.ARCHIVES + (".bin", ".img"))
                  and str(f["name"]) not in in_cues]
    for f in sorted(candidates, key=lambda f: -int(f.get("size") or 0))[:MAX_ZIPS]:
        size = int(f.get("size") or 0)
        z = dict(part(f))
        ext = PurePosixPath(f["name"]).suffix.lower()
        z["kind"] = ext[1:]
        if size > game_fetch.MAX_BYTES:
            z["verdict"] = "too-big"
        elif ext in (".7z", ".rar"):
            z["verdict"] = "packed"
        else:
            try:
                if ext in (".iso", ".bin", ".img"):  # an .iso, or a raw image without its cue sheet
                    head = ranged(z["url"], 0, game_fetch.RAW_HEAD - 1, game_fetch.RAW_HEAD)
                    mode = "MODE1/2048" if iso9660.is_iso(head) else iso9660.raw_mode(head)
                    if not mode:
                        continue  # a .bin that is not a CD image (data of something else)
                    z["kind"] = "iso" if mode == "MODE1/2048" else "bin"
                    z.update(look_at_cd(z["url"], mode, 0, title, emu_start))
                else:
                    z.update(look_at_zip(z["url"], size, title, emu_start))
            except Exception as e:  # one file that cannot be read does not hide the others
                z["verdict"], z["error"] = "error", f"{type(e).__name__}: {e}"[:200]
        report["zips"].append(z)
    rank = {"scummvm": 0, "dosbox": 0, "nested": 1, "packed": 1}
    report["zips"].sort(key=lambda z: (rank.get(z.get("verdict"), 2), -z["size"]))  # what can be played first
    usable = [z for z in report["zips"] if z.get("verdict") in ("dosbox", "scummvm")]
    report["best"] = usable[0]["name"] if usable else None
    return report


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    print(json.dumps(inspect(sys.argv[1]), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
