"""A small reader of ISO 9660 CD images (the format of the CD-ROMs of the 90s), standard library only.

It works on any `read(offset, length) -> bytes`, so the same code lists a local .iso and one on Internet Archive
through HTTP range requests (tools/ia_inspect.py), without downloading the whole image. It reads the primary
volume descriptor's directory tree (8.3 names, which is what DOS games use) and also writes small images for
the tests (`build`)."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable

SECTOR = 2048
MAX_ENTRIES = 50000
MAX_DIRS = 400

Reader = Callable[[int, int], bytes]


class IsoError(Exception):
    pass


def is_iso(head: bytes) -> bool:
    """True for the first 32 KB + 6 bytes of an ISO 9660 image (its descriptor is at sector 16)."""
    return len(head) >= 16 * SECTOR + 6 and head[16 * SECTOR + 1:16 * SECTOR + 6] == b"CD001"


def file_reader(path: Path) -> Reader:
    def read(offset: int, length: int) -> bytes:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read(length)
    return read


def _record(buf: bytes, p: int) -> tuple[int, dict | None]:
    n = buf[p]
    if n == 0:
        return 0, None
    lba, size = struct.unpack("<I", buf[p + 2:p + 6])[0], struct.unpack("<I", buf[p + 10:p + 14])[0]
    flags, nl = buf[p + 25], buf[p + 32]
    raw = buf[p + 33:p + 33 + nl]
    if raw in (b"\x00", b"\x01"):
        return n, {"self": True}
    name = raw.decode("ascii", "replace").split(";")[0].rstrip(".")
    return n, {"name": name, "lba": lba, "size": size, "dir": bool(flags & 2)}


def listing(read: Reader) -> list[dict]:
    """Every file of the image: {"name": "GAME/GAME.EXE", "size": n, "lba": sector}."""
    pvd = read(16 * SECTOR, SECTOR)
    if len(pvd) < 190 or pvd[1:6] != b"CD001" or pvd[0] != 1:
        raise IsoError("not an ISO 9660 image")
    root_lba, root_size = struct.unpack("<I", pvd[158:162])[0], struct.unpack("<I", pvd[166:170])[0]  # root directory record
    out: list[dict] = []
    todo, seen = [("", root_lba, root_size)], 0
    while todo:
        prefix, lba, size = todo.pop(0)
        seen += 1
        if seen > MAX_DIRS:
            raise IsoError("too many folders")
        buf = read(lba * SECTOR, min(size, 4 << 20))
        p = 0
        while p < len(buf):
            n, rec = _record(buf, p)
            if n == 0:  # records do not cross sectors: jump to the next one
                p = (p // SECTOR + 1) * SECTOR
                continue
            p += n
            if not rec or rec.get("self"):
                continue
            path = f"{prefix}{rec['name']}"
            if rec["dir"]:
                todo.append((path + "/", rec["lba"], rec["size"]))
            else:
                out.append({"name": path, "size": rec["size"], "lba": rec["lba"]})
                if len(out) > MAX_ENTRIES:
                    raise IsoError("too many files")
    return out


def read_file(read: Reader, entry: dict, limit: int | None = None) -> bytes:
    n = entry["size"] if limit is None else min(limit, entry["size"])
    return read(entry["lba"] * SECTOR, n)


def build(files: dict[str, bytes], label: str = "MUSEUM") -> bytes:
    """A minimal ISO 9660 image (one level of folders, 8.3 names). For the tests."""
    dirs: dict[str, dict[str, bytes]] = {"": {}}
    for name, data in files.items():
        parts = name.upper().split("/")
        if len(parts) > 2:
            raise ValueError("one level of folders only")
        if len(parts) == 2:
            dirs.setdefault(parts[0], {})[parts[1]] = data
            dirs[""].setdefault(parts[0] + "/", b"")
        else:
            dirs[""][parts[0]] = data
    sec = 18  # 16 system + PVD + terminator
    dir_lba = {d: sec + i for i, d in enumerate(dirs)}
    sec += len(dirs)
    file_lba: dict[tuple[str, str], int] = {}
    for d, entries in dirs.items():
        for n, data in entries.items():
            if not n.endswith("/"):
                file_lba[(d, n)] = sec
                sec += max(1, -(-len(data) // SECTOR))

    def rec(name: bytes, lba: int, size: int, is_dir: bool) -> bytes:
        nl = len(name)
        body = struct.pack("<BB", 0, 0) + struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", size) + struct.pack(">I", size)
        body += bytes(7) + bytes([2 if is_dir else 0, 0, 0]) + struct.pack("<H", 1) + struct.pack(">H", 1) + bytes([nl]) + name
        if len(body) % 2:
            body += b"\0"
        return bytes([len(body)]) + body[1:]

    def dir_block(d: str) -> bytes:
        parent = "" if d == "" else ""
        out = rec(b"\x00", dir_lba[d], SECTOR, True) + rec(b"\x01", dir_lba[parent], SECTOR, True)
        for n, data in sorted(dirs[d].items()):
            if n.endswith("/"):
                out += rec(n[:-1].encode(), dir_lba[n[:-1]], SECTOR, True)
            else:
                out += rec((n + ";1").encode(), file_lba[(d, n)], len(data), False)
        if len(out) > SECTOR:
            raise ValueError("too many files in one folder for this small writer")
        return out.ljust(SECTOR, b"\0")

    img = bytearray(sec * SECTOR)
    pvd = bytearray(SECTOR)
    pvd[0], pvd[1:6], pvd[6] = 1, b"CD001", 1
    pvd[40:72] = label.encode().ljust(32)
    pvd[80:88] = struct.pack("<I", sec) + struct.pack(">I", sec)
    pvd[128:132] = struct.pack("<H", SECTOR) + struct.pack(">H", SECTOR)
    pvd[156:156 + 34] = rec(b"\x00", dir_lba[""], SECTOR, True)
    img[16 * SECTOR:17 * SECTOR] = pvd
    img[17 * SECTOR:17 * SECTOR + 6] = bytes([255]) + b"CD001"
    for d, lba in dir_lba.items():
        img[lba * SECTOR:(lba + 1) * SECTOR] = dir_block(d)
    for (d, n), lba in file_lba.items():
        data = dirs[d][n]
        img[lba * SECTOR:lba * SECTOR + len(data)] = data
    return bytes(img)
