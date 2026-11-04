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


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        data = FILES.get(self.path)
        self.send_response(200 if data else 404)
        self.send_header("Content-Length", str(len(data or b"")))
        self.end_headers()
        self.wfile.write(data or b"")


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
print(srv.server_address[1], flush=True)
srv.serve_forever()
