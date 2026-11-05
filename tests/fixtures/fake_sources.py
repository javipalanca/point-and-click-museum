"""Fake game sources for the tests: serves a ScummVM freeware zip and DOS game zips, like downloads.scummvm.org and
archive.org/download would (with partial requests, as archive.org), and Internet Archive's search and metadata
for three items: a DOS game with its installer, a Windows-only game and a ScummVM game. Prints the port and keeps
running."""
import io
import json
import re
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
