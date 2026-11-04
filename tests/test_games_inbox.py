"""Tests for tools/games_inbox.py (python3 -m unittest discover -s tests)."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import add_game  # noqa: E402
import games_inbox  # noqa: E402
import identify_game  # noqa: E402


def make_zip(path: Path, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


class GamesInboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.inbox, self.cache = self.tmp / "inbox", self.tmp / "cache"
        self.inbox.mkdir(), self.cache.mkdir()
        self.saved = (add_game.LOCAL, add_game.SVM_BUILT, games_inbox.ASSETS, games_inbox.build)
        self.net = (identify_game.find_cover, identify_game.fetch_cover)
        self.covers = []

        def find_cover(title, year, cache):  # no network in the tests
            return f"github:libretro-thumbnails/DOS@abc123/Named_Boxarts/{title}.png" if title == "Space Quest III: The Pirates of Pestulon" else None

        def fetch_cover(spec, dest):
            self.covers.append(spec)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x89PNG fake")
            return {"page": "https://github.com/libretro-thumbnails/DOS/blob/abc123/x.png", "w": 170, "h": 240, "src": spec}
        identify_game.find_cover, identify_game.fetch_cover = find_cover, fetch_cover
        add_game.LOCAL = self.tmp / "arcade.local.json"
        add_game.SVM_BUILT = self.tmp / "no-scummvm.js"
        games_inbox.ASSETS = self.tmp / "assets"
        self.builds = 0

        def fake_build(site, extra):
            self.builds += 1
            return True
        games_inbox.build = fake_build

    def tearDown(self):
        add_game.LOCAL, add_game.SVM_BUILT, games_inbox.ASSETS, games_inbox.build = self.saved
        identify_game.find_cover, identify_game.fetch_cover = self.net
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sync(self):
        return games_inbox.sync(self.inbox, self.cache, None, [], games_inbox.scan(self.inbox))

    def local(self):
        return {g["id"]: g for g in json.loads(add_game.LOCAL.read_text("utf-8"))["games"]}

    def test_imports_updates_and_removes(self):
        make_zip(self.inbox / "space_quest_DOS.zip", {"SQ/SQ.EXE": b"x" * 5000, "SQ/INSTALL.EXE": b"i"})
        make_zip(self.inbox / "sub/Cave.zip", {"CAVE.COM": b"c"})
        (self.inbox / "sub/Cave.json").write_text(json.dumps({"title": "Colossal Test", "year": 1977, "cycles": 3000}))
        (self.inbox / "notes.txt").write_text("not a game")
        self.assertTrue(self.sync())
        games = self.local()
        self.assertEqual(set(games), {"space-quest", "colossal-test"})
        self.assertEqual((games["colossal-test"]["year"], games["space-quest"]["exe"]), (1977, "SQ/SQ.EXE"))
        self.assertTrue(all(g["inbox"] for g in games.values()))
        self.assertTrue((games_inbox.ASSETS / "games/space-quest.jsdos").exists())
        self.assertIn("cycles=3000", zipfile.ZipFile(games_inbox.ASSETS / "games/colossal-test.jsdos").read(".jsdos/dosbox.conf").decode())
        cached = {d.name for d in self.cache.iterdir()}

        self.sync()  # nothing changed: nothing converted again
        self.assertEqual({d.name for d in self.cache.iterdir()}, cached)

        (self.inbox / "space_quest_DOS.zip").unlink()
        self.sync()
        self.assertEqual(set(self.local()), {"colossal-test"})
        self.assertFalse((games_inbox.ASSETS / "games/space-quest.jsdos").exists())
        self.assertEqual(len(list(self.cache.iterdir())), 1)
        self.assertEqual(self.builds, 3)

    def test_keeps_games_added_by_hand_and_avoids_clashes(self):
        add_game.save_local({"games": [{"id": "zzyx-mine", "title": "Mine", "bundle": "games/zzyx-mine.jsdos"}]})
        make_zip(self.inbox / "Zzyx Mine.zip", {"ZZYX.EXE": b"l"})
        make_zip(self.inbox / "a/Zzyx Mine.zip", {"ZZYX.EXE": b"l2"})
        self.sync()
        self.assertEqual(set(self.local()), {"zzyx-mine", "zzyx-mine-2", "zzyx-mine-3"})
        self.assertFalse(self.local()["zzyx-mine"].get("inbox"))
        self.assertEqual(self.local()["zzyx-mine"]["bundle"], "games/zzyx-mine.jsdos")   # yours is never overwritten
        self.assertFalse((games_inbox.ASSETS / "games/zzyx-mine.jsdos").exists())

    def test_identifies_the_game_and_its_cover(self):
        make_zip(self.inbox / "MI2_GOG.zip", {"MONKEY2/MONKEY2.000": b"d", "MONKEY2/MONKEY2.EXE": b"e"})   # a data file
        make_zip(self.inbox / "Space_Quest_III_DOS.zip", {"SQ3/RESOURCE.MAP": b"m", "SQ3/SIERRA.EXE": b"s"})   # the zip name
        make_zip(self.inbox / "x.zip", {"ZZYX.EXE": b"z"})                                                    # unknown
        self.sync()
        games = self.local()
        mi2 = games["monkey-island-2"]  # the museum's record: its title, year, description and checked cover
        self.assertEqual((mi2["title"], mi2["year"], mi2["timeline"]), ("Monkey Island 2: LeChuck's Revenge", 1991, "monkey-island-2"))
        self.assertEqual(mi2["cover"], {"media": "games/monkey-island-2/cover"})
        self.assertIn("Big Whoop", mi2["desc"]["en"])
        sq3 = games["space-quest-iii"]  # not in the timeline: ScummVM catalogue data and a libretro box
        self.assertEqual((sq3["year"], sq3["studio"]), (1989, "Sierra"))
        self.assertEqual(sq3["cover"]["file"], "games/covers/space-quest-iii.png")
        self.assertTrue((games_inbox.ASSETS / "games/covers/space-quest-iii.png").exists())
        self.assertNotIn("cover", games["x"])
        self.assertEqual(len(self.covers), 1)
        self.sync()  # cached: nothing downloaded again
        self.assertEqual(len(self.covers), 1)

    def test_settings_file_wins(self):
        make_zip(self.inbox / "MI2.zip", {"MONKEY2.000": b"d", "MONKEY2.EXE": b"e"})
        (self.inbox / "MI2.json").write_text(json.dumps({"title": "Mi copia", "year": 1992, "cover": False}))
        self.sync()
        g = self.local()["mi-copia"]
        self.assertEqual((g["title"], g["year"]), ("Mi copia", 1992))
        self.assertNotIn("cover", g)

    def test_bad_files_are_reported_once_and_skipped(self):
        make_zip(self.inbox / "windows.zip", {"README.TXT": b"no program here"})
        (self.inbox / "broken.zip").write_bytes(b"PK\x03\x04 not really")
        self.assertTrue(self.sync())
        self.assertEqual(self.local(), {})
        self.assertEqual(len(list(self.cache.glob("*/error.txt"))), 2)

    def test_build_swaps_the_site_atomically(self):
        games_inbox.build = self.saved[3]
        site = self.tmp / "site"
        calls = []
        real_run = games_inbox.subprocess.run

        def fake_run(cmd, **kw):  # do not run the real generator: just create the output folder
            calls.append(cmd)
            out = Path(cmd[cmd.index("--out") + 1])
            (out / "es").mkdir(parents=True)
            (out / "index.html").write_text("ok")
            return games_inbox.subprocess.CompletedProcess(cmd, 0, "built 44 pages", "")
        games_inbox.subprocess.run = fake_run
        try:
            for _ in range(4):
                self.assertTrue(games_inbox.build(site, ["--base-url", "https://x"]))
                time.sleep(1.05)  # build folders are named by the second
        finally:
            games_inbox.subprocess.run = real_run
        self.assertTrue((site / "current").is_symlink())
        self.assertEqual((site / "current/index.html").read_text(), "ok")
        self.assertLessEqual(len(list(site.glob("build-*"))), 2)
        self.assertIn("--base-url", calls[0])


if __name__ == "__main__":
    unittest.main()
