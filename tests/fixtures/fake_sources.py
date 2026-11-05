"""Fake game sources for the tests: serves a ScummVM freeware zip and DOS game zips, like downloads.scummvm.org and
archive.org/download would (with partial requests, as archive.org), and Internet Archive's search and metadata
for these items: a DOS game with its installer, a Windows-only game, a ScummVM game, a game on a CD image (.iso)
and a zip holding the game as .7z with its manual and cover (made with the 7-Zip program when it is installed).
Prints the port and keeps running."""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import iso9660  # noqa: E402
DOS = (ROOT / "tools/dos/PAINT.COM").read_bytes()
WIN = b"MZ" + b"\0" * 0x3A + (0x80).to_bytes(4, "little") + b"\0" * 0x40 + b"PE\0\0" + b"\0" * 2000  # a Windows (PE) program


def zbytes(files, deflate=False):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED if deflate else zipfile.ZIP_STORED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


FILES = {
    "/frs/extras/sky.zip": zbytes({"BASS/sky.dnr": b"d" * 100, "BASS/sky.dsk": b"k" * 100}),
    "/download/pixelcave/CAVE.ZIP": zbytes({"CAVE/CAVE.COM": DOS}),
    "/download/msdos_quest_1991/QUEST.ZIP": zbytes({"QUEST/QUEST.EXE": DOS}),
    "/download/msdos_quest_1991/QUEST_EXTRAS.ZIP": zbytes({"QUEST/INSTALL.EXE": DOS, "QUEST/MANUAL.TXT": b"x" * 50}),
    "/download/win_quest_1998/WINQUEST.ZIP": zbytes({"WINQUEST/WINQUEST.EXE": WIN, "WINQUEST/DATA.CAB": b"c" * 3000}, deflate=True),
    "/download/sky_full/SKY.ZIP": zbytes({"SKY/SKY.DNR": b"d" * 100, "SKY/SKY.DSK": b"k" * 100}, deflate=True),
}
ITEMS = {
    "msdos_quest_1991": {"title": "Quest for the Museum (1991)", "year": "1991", "creator": "Some Studio",
                         "collection": ["softwarelibrary_msdos_games"], "emulator": "dosbox", "emulator_start": "QUEST/QUEST.EXE"},
    "win_quest_1998": {"title": "Quest for the Museum: Windows Edition (1998)", "year": "1998", "creator": "Some Studio",
                       "collection": ["softwarelibrary_msdos_games"]},
    "sky_full": {"title": "Beneath a Steel Sky (1994)", "year": "1994", "creator": "Revolution Software",
                 "collection": ["softwarelibrary_msdos_games"]},
}
FILES["/download/cd_quest_1995/QUESTCD.ISO"] = iso9660.build({"QUEST/QUEST.EXE": DOS, "QUEST/INSTALL.EXE": DOS, "README.TXT": b"CD"})
ITEMS["cd_quest_1995"] = {"title": "Quest for the Museum CD (1995)", "year": "1995", "creator": "Some Studio",
                          "collection": ["softwarelibrary_msdos_games"]}


def seven(files):
    """A .7z made with the 7-Zip program (Python cannot write them); None without it."""
    exe = next((b for b in ("7z", "7zz", "7za") if shutil.which(b)), None)
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        for n, d in files.items():
            (Path(tmp) / n).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp) / n).write_bytes(d)
        subprocess.run([exe, "a", "-bd", "-y", "game.7z", *files], cwd=tmp, capture_output=True, check=True)
        return (Path(tmp) / "game.7z").read_bytes()


packed = seven({"SKULLS/SKULLS.EXE": DOS, "SKULLS/SKULLS.DAT": b"d" * 4000})
if packed:  # like "3 Skulls of the Toltecs.zip": manual, cover, metadata and the game itself as a .7z
    FILES["/download/skulls_7z/Skulls.zip"] = zbytes({"Skulls/Skulls - Manual.pdf": b"%PDF" + b"m" * 300, "Skulls/Skulls.7z": packed,
                                                      "Skulls/Skulls_01.png": b"\x89PNG" + b"p" * 200, "Skulls/metadata.json": b"{}", "Skulls/README.txt": b"r"})
    ITEMS["skulls_7z"] = {"title": "Skulls of the Museum (1996)", "year": "1996", "creator": "Some Studio", "collection": ["softwarelibrary_msdos_games"]}
    # an item whose only file is the .7z itself (like "3 Skulls Of The Toltecs PC CD 1996 Spanish")
    FILES["/download/skulls_cd_7z/Skulls_PC_CD_1996.7z"] = packed
    ITEMS["skulls_cd_7z"] = {"title": "Skulls of the Museum PC CD 1996", "year": "1996", "creator": "Some Studio", "collection": ["softwarelibrary_msdos_games"]}
SEARCH = {"response": {"docs": [dict(m, identifier=i) for i, m in ITEMS.items()]}}


def meta(ident):
    files = [{"name": p.rsplit("/", 1)[1], "size": str(len(d)), "format": "ZIP"} for p, d in FILES.items() if p.startswith(f"/download/{ident}/")]
    files.append({"name": f"{ident}_meta.xml", "size": "300", "source": "metadata", "format": "Metadata"})
    return {"metadata": dict(ITEMS[ident], identifier=ident), "files": files}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        m = re.fullmatch(r"/metadata/([\w.-]+)", path)
        if path == "/advancedsearch.php":
            data = json.dumps(SEARCH).encode()
        elif m:
            data = json.dumps(meta(m.group(1)) if m.group(1) in ITEMS else {}).encode()
        else:
            data = FILES.get(path)
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "") or "")
        if data and rng:  # partial requests, as archive.org's servers answer them
            a, b = rng.groups()
            start, end = (max(0, len(data) - int(b)), len(data) - 1) if a == "" else (int(a), min(int(b or len(data) - 1), len(data) - 1))
            part = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.send_header("Content-Length", str(len(part)))
            self.end_headers()
            self.wfile.write(part)
            return
        self.send_response(200 if data else 404)
        self.send_header("Content-Length", str(len(data or b"")))
        self.end_headers()
        self.wfile.write(data or b"")


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print(srv.server_address[1], flush=True)
srv.serve_forever()
