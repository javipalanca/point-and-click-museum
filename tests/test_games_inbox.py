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
        add_game.save_local({"games": [{"id": "loom-mine", "title": "Mine", "bundle": "games/loom-mine.jsdos"}]})
        make_zip(self.inbox / "Loom Mine.zip", {"LOOM.EXE": b"l"})
        make_zip(self.inbox / "a/Loom Mine.zip", {"LOOM.EXE": b"l2"})
        self.sync()
        self.assertEqual(set(self.local()), {"loom-mine", "loom-mine-2", "loom-mine-3"})
        self.assertFalse(self.local()["loom-mine"].get("inbox"))
        self.assertEqual(self.local()["loom-mine"]["bundle"], "games/loom-mine.jsdos")   # yours is never overwritten
        self.assertFalse((games_inbox.ASSETS / "games/loom-mine.jsdos").exists())

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
