#!/usr/bin/env python3
"""What is inside an Internet Archive item, before adding it to the catalogue.

    python3 tools/ia_inspect.py <identifier>

For each zip of the item it reads only the zip's index (the central directory at the end of the file, with HTTP
range requests) and the first bytes of each program, never the whole download. From that:

  · ScummVM data (the same file signatures as tools/add_game.py), and whether that engine is in our build;
  · DOS programs (.EXE/.COM/.BAT), Windows programs (PE header) and installers, with the one most likely to start
    the game first (the same ranking as add_game.candidates);
  · a verdict: dosbox, scummvm, windows (DOSBox cannot run it), nested (a zip inside the zip), none, too-big.

Other files (ISO, 7z, RAR, disk images) are listed but not usable yet. Used by the control panel
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
import sync_catalog  # noqa: E402

TAIL = 65536 + 22           # the end-of-central-directory record is within the last 64 KB
HEAD = 4096                 # bytes of each program read to tell DOS from Windows
MAX_PROGRAMS = 16           # programs whose header is read, per zip
MAX_ZIPS = 4                # zips looked at per item (largest first)
OTHER = re.compile(r"\.(iso|cue|bin|img|ima|7z|rar|exe|dsk|adf|d64|st)$", re.I)


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


class Head(bytes):
    """The first bytes of a program, with the size of the whole file (what add_game.candidates looks at)."""
    def __new__(cls, data: bytes, size: int):
        obj = super().__new__(cls, data)
        obj.full = size
        return obj

    def __len__(self):
        return self.full


def look_at_zip(url: str, size: int, title: str, start: str | None) -> dict:
    entries = central_directory(url, size)
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
                data = head(url, e)
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
    inner = [n for n in names if n.lower().endswith(".zip")]
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


def inspect(ident: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", ident):
        raise InspectError("bad Internet Archive identifier")
    meta = sync_catalog.http_json(f"{sync_catalog.IA}/metadata/{urllib.parse.quote(ident)}")
    md = meta.get("metadata") or {}
    if not md:
        raise InspectError("no such item")
    title = str(sync_catalog.as_list(md.get("title"))[0] if md.get("title") else ident)
    files = [f for f in meta.get("files", []) if f.get("source") != "metadata" or str(f.get("name", "")).lower().endswith(".zip")]
    zips = sorted((f for f in files if str(f.get("name", "")).lower().endswith(".zip")), key=lambda f: -int(f.get("size") or 0))
    report = {"identifier": ident, "title": title, "page": f"https://archive.org/details/{ident}",
              "year": sync_catalog.year_of(md), "creator": md.get("creator"), "rights": sync_catalog.ia_rights(md),
              "start": md.get("emulator_start"), "zips": [],
              "other": [{"name": f["name"], "size": int(f.get("size") or 0)} for f in files if OTHER.search(str(f.get("name", ""))) and not str(f["name"]).lower().endswith(".zip")][:10]}
    for f in zips[:MAX_ZIPS]:
        size = int(f.get("size") or 0)
        z = {"name": f["name"], "size": size, "md5": f.get("md5"), "sha1": f.get("sha1"),
             "url": f"{sync_catalog.IA}/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(f['name'])}"}
        if size > game_fetch.MAX_BYTES:
            z["verdict"] = "too-big"
        else:
            try:
                z.update(look_at_zip(z["url"], size, title, md.get("emulator_start")))
            except Exception as e:  # one zip that cannot be read does not hide the others
                z["verdict"], z["error"] = "error", f"{type(e).__name__}: {e}"[:200]
        report["zips"].append(z)
    rank = {"dosbox": 0, "scummvm": 0, "nested": 1}
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
