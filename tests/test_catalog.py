"""Tests of the automatic catalogue: tools/sync_catalog.py, tools/game_fetch.py and server/games.py, against fake
ScummVM, Internet Archive and GOG servers (python3 -m unittest discover -s tests)."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))


def zbytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


PAINT = (ROOT / "tools/dos/PAINT.COM").read_bytes()
FILES = {
    "/frs/extras/Beneath%20a%20Steel%20Sky/bass-cd-1.2.zip": zbytes({"bass/sky.dnr": b"d", "bass/sky.dsk": b"k", "bass/readme.txt": b"r"}),
    "/frs/demos/scumm/monkey1-dos-ega-demo-en.zip": zbytes({"000.LFL": b"x", "901.LFL": b"y"}),
    "/download/shareware_cave/CAVE.ZIP": zbytes({"CAVE/CAVE.EXE": PAINT, "CAVE/INSTALL.EXE": b"i"}),
    "/download/cc_quest/QUEST.ZIP": zbytes({"QUEST.EXE": b"MZ" + b"\0" * 58 + b"\x40\0\0\0" + b"PE\0\0"}),  # a Windows program
}
IA_DOCS = [
    {"identifier": "msdos_Monkey_Island_1990", "title": "The Secret of Monkey Island", "year": "1990", "creator": "Lucasfilm Games",
     "subject": ["adventure"], "collection": ["softwarelibrary_msdos_games"]},
    {"identifier": "shareware_cave", "title": "Cave Quest (shareware)", "year": "1992", "subject": ["adventure", "shareware"]},
    {"identifier": "cc_quest", "title": "Quest of Freedom", "year": "1995", "licenseurl": "https://creativecommons.org/licenses/by/4.0/"},
]
IA_META = {
    "shareware_cave": {"metadata": {"emulator": "dosbox", "emulator_start": "CAVE/CAVE.EXE"},
                       "files": [{"name": "CAVE.ZIP", "size": str(len(FILES["/download/shareware_cave/CAVE.ZIP"])),
                                  "md5": hashlib.md5(FILES["/download/shareware_cave/CAVE.ZIP"]).hexdigest()}]},
    "cc_quest": {"metadata": {}, "files": [{"name": "QUEST.ZIP", "size": str(len(FILES["/download/cc_quest/QUEST.ZIP"]))}]},
}
YAML_GAMES = """# generated
-
    category: games
    game_id: 'sky:sky'
    url: 'Beneath a Steel Sky/bass-cd-1.2.zip'
    name: 'Freeware CD Version'
-
    category: games
    game_id: 'drascula:drascula'
    url: 'Drascula_ The Vampire Strikes Back/drascula-audio-2.0.zip'
    name: 'Freeware Version (Music AddOn, OGG format)'
"""
YAML_DEMOS = """# generated
-
    id: 'scumm:monkey'
    platform: dos
    category: EGA
    language: en
    url: /frs/demos/scumm/monkey1-dos-ega-demo-en.zip
"""


class Fake(BaseHTTPRequestHandler):
    hits = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Fake.hits.append(self.path)
        p = self.path.split("?")[0]
        if p.startswith("/advancedsearch.php"):
            return self.out(200, json.dumps({"response": {"docs": IA_DOCS}}).encode(), "application/json")
        if p.startswith("/metadata/"):
            m = IA_META.get(p.split("/")[-1], {"metadata": {}, "files": []})
            return self.out(200, json.dumps(m).encode(), "application/json")
        if p.startswith("/gog"):
            products = [{"title": "The Secret of Monkey Island: Special Edition", "slug": "the_secret_of_monkey_island_special_edition"},
                        {"title": "Beneath a Steel Sky", "storeLink": "https://www.gog.com/en/game/beneath_a_steel_sky"}]
            return self.out(200, json.dumps({"products": products}).encode(), "application/json")
        if p in FILES:
            return self.out(200, FILES[p], "application/zip")
        self.out(404, b"no", "text/plain")

    def out(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        os.environ.update(PCM_SCUMMVM_DL=cls.base, PCM_IA_BASE=cls.base, PCM_GAMES_TEST_HOSTS="127.0.0.1")
        import sync_catalog, game_fetch  # noqa: E402  (after the environment)
        cls.sc, cls.gf = sync_catalog, game_fetch
        sync_catalog.SVM_DL, sync_catalog.IA = cls.base, cls.base
        sync_catalog.http_text = lambda url, timeout=60: YAML_GAMES if url.endswith("game_downloads.yaml") else YAML_DEMOS

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out, self.cache = self.tmp / "catalog.json", self.tmp / "cache"
        self.cfg = {"scummvm": {"commit": "abc"}, "archive": {"collections": ["x"], "subjects": ["adventure"], "titleQueries": 0, "pause": 0},
                    "gog": {"search": self.base + "/gog?q={query}", "pause": 0}}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sync(self, validate=10, overrides=None):
        sc = self.sc
        found, _ = sc.scummvm_source(self.cfg["scummvm"], {})
        ia, _ = sc.archive_source(self.cfg["archive"], [], {})
        games = sc.merge(found + ia, {}, overrides or {})
        cached = {}
        for g in games:
            link = sc.gog_link(g["title"], self.cfg["gog"], cached)
            if link:
                g["gog"] = link
        sc.validate(games, self.cache, validate)
        return {g["id"]: g for g in games}

    def test_states_rights_and_links(self):
        g = self.sync()
        bass = g["beneath-a-steel-sky"]  # ScummVM freeware: checked and playable; GOG still sells it
        self.assertEqual((bass["status"], bass["editions"][0]["rights"]), ("playable", "freeware"))
        self.assertEqual(bass["gog"], "https://www.gog.com/en/game/beneath_a_steel_sky")
        self.assertTrue(any("ScummVM engine sky" in c for c in bass["editions"][0]["validated"]["checks"]))
        mi = g["monkey-island"]  # commercial on Internet Archive: never playable; its ScummVM demo is
        self.assertEqual(mi["status"], "playable")
        self.assertEqual(mi["editions"][0]["kind"], "demo")
        self.assertIn("record", [e["status"] for e in mi["editions"]])
        self.assertNotIn("gog", mi)  # only the Special Edition is sold: not the same game
        cave = g["cave-quest"]  # "shareware" said by the uploader: pending until a person confirms it
        self.assertEqual((cave["status"], cave["editions"][0]["rightsHint"]), ("pending", "shareware"))
        quest = g["quest-of-freedom"]  # explicit licence, but a Windows program: fails the checks
        self.assertEqual(quest["status"], "pending")
        self.assertIn("Windows", quest["editions"][0]["validated"]["error"])
        self.assertNotIn("drascula", g.get("drascula", {}).get("scummvm", ""))  # a music add-on is not a game
        self.assertEqual(g["drascula"]["editions"], [])  # the timeline record stays, without editions
        self.assertEqual(g["drascula"]["status"], "record")

    def test_confirmed_rights_make_it_playable(self):
        key = "cave-quest-full-shareware-cave"
        g = self.sync(overrides={"cave-quest": {"editions": {key: {"rights": "shareware", "rightsSource": "https://example.org/permission"}}}})
        cave = g["cave-quest"]
        self.assertEqual(cave["status"], "playable")
        self.assertIn("DOSBox runs CAVE/CAVE.EXE", cave["editions"][0]["validated"]["checks"])  # Internet Archive's emulator_start
        self.assertIn("md5 matches", cave["editions"][0]["validated"]["checks"])
        bundle = zipfile.ZipFile(self.cache / f"{key}.jsdos")
        self.assertIn("CAVE.EXE", bundle.read(".jsdos/dosbox.conf").decode())

    def test_fetch_refuses_bad_downloads(self):
        gf = self.gf
        base = {"id": "x", "title": "X", "rights": "freeware", "emulator": "dosbox"}
        with self.assertRaises(gf.GameError):
            gf.prepare(dict(base, rights="commercial", download={"url": self.base + "/download/shareware_cave/CAVE.ZIP"}), self.cache)
        with self.assertRaises(gf.GameError):
            gf.prepare(dict(base, download={"url": "https://evil.example/x.zip"}), self.cache)
        with self.assertRaisesRegex(gf.GameError, "md5"):
            gf.prepare(dict(base, download={"url": self.base + "/download/shareware_cave/CAVE.ZIP", "md5": "0" * 32}), self.cache)
        with self.assertRaisesRegex(gf.GameError, "engine"):
            gf.prepare(dict(base, emulator="scummvm", run={"svmEngine": "sword25"}, download={"url": self.base + "/x"}), self.cache)

    def test_removed_editions_do_not_come_back(self):
        sc = self.sc
        found, _ = sc.scummvm_source(self.cfg["scummvm"], {})
        key = "beneath-a-steel-sky-full-bass-cd-1-2"
        games = {g["id"]: g for g in sc.merge(found, {}, {"beneath-a-steel-sky": {"removedEditions": {key: {"key": key}}}})}
        self.assertNotIn(key, [e["key"] for e in games["beneath-a-steel-sky"]["editions"]])
        self.assertTrue(games["beneath-a-steel-sky"]["editions"])  # the demo stays

    def test_network_failures_are_not_verdicts(self):
        sc = self.sc
        games = [{"title": "Far", "editions": [
            {"key": "far", "kind": "full", "rights": "freeware", "emulator": "dosbox", "edition": "x", "download": {"url": "http://127.0.0.1:9/x.zip"}},
            {"key": "svm", "kind": "full", "rights": "freeware", "emulator": "scummvm", "run": {"svmEngine": "sword25"}, "edition": "y",
             "download": {"url": self.base + "/x"}}]}]
        self.assertEqual(sc.validate(games, self.cache, 1), 1)
        eds = {e["key"]: e for e in games[0]["editions"]}
        self.assertNotIn("validated", eds["far"])                     # unreachable: tried again next time
        self.assertEqual(eds["svm"]["validated"]["engineMissing"], "sword25")  # known without downloading, not counted

    def test_proxy_serves_only_playable_games(self):
        g = self.sync()
        catalog = self.tmp / "catalog.json"
        catalog.write_text(json.dumps({"games": list(g.values())}))
        os.environ.update(PCM_CATALOG=str(catalog), GAMES_CACHE=str(self.tmp / "proxy"))
        import importlib
        import games
        games = importlib.reload(games)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), games.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/games/"
        try:
            key = g["beneath-a-steel-sky"]["editions"][0]["key"]
            with urllib.request.urlopen(url + key) as r:
                data = r.read()
                self.assertEqual(r.headers["Content-Type"], "application/zip")
            self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()), ["readme.txt", "sky.dnr", "sky.dsk"])  # folder removed
            n = len(Fake.hits)
            with urllib.request.urlopen(url + key) as r:  # second time: from the cache
                r.read()
            self.assertEqual(len(Fake.hits), n)
            for bad in ("cave-quest-full-shareware-cave", "monkey-island-full-msdos-monkey-island-1990", "..%2Fetc%2Fpasswd", "nope"):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(url + bad)
                self.assertEqual(e.exception.code, 404, bad)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
