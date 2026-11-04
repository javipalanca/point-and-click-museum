"""Fake game sources for tests/catalog.test.js: serves a ScummVM freeware zip and a DOS game zip, like
downloads.scummvm.org and archive.org/download would. Prints the port and keeps running."""
import io
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def zbytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


FILES = {
    "/frs/extras/sky.zip": zbytes({"BASS/sky.dnr": b"d" * 100, "BASS/sky.dsk": b"k" * 100}),
    "/download/pixelcave/CAVE.ZIP": zbytes({"CAVE/CAVE.COM": (ROOT / "tools/dos/PAINT.COM").read_bytes()}),
}


FILES["/download/msdos_quest_1991/QUEST.ZIP"] = zbytes({"QUEST/QUEST.EXE": (ROOT / "tools/dos/PAINT.COM").read_bytes()})
SEARCH = {"response": {"docs": [{"identifier": "msdos_quest_1991", "title": "Quest for the Museum (1991)", "year": "1991",
                                 "creator": "Some Studio", "collection": ["softwarelibrary_msdos_games"]}]}}
META = {"metadata": {"identifier": "msdos_quest_1991", "title": "Quest for the Museum (1991)", "creator": "Some Studio",
                     "collection": ["softwarelibrary_msdos_games"], "emulator": "dosbox", "emulator_start": "QUEST/QUEST.EXE"},
        "files": [{"name": "QUEST.ZIP", "size": str(len(FILES["/download/msdos_quest_1991/QUEST.ZIP"]))}]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        import json
        path = self.path.split("?")[0]
        if path == "/advancedsearch.php":
            data = json.dumps(SEARCH).encode()
        elif path == "/metadata/msdos_quest_1991":
            data = json.dumps(META).encode()
        else:
            data = FILES.get(path)
        self.send_response(200 if data else 404)
        self.send_header("Content-Length", str(len(data or b"")))
        self.end_headers()
        self.wfile.write(data or b"")


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print(srv.server_address[1], flush=True)
srv.serve_forever()
