"""Tests for tools/add_game.py (python3 -m unittest discover -s tests)."""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import add_game  # noqa: E402


def make_zip(path: Path, files: dict):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


class AddGameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        add_game.GAMES_DIR = self.tmp / "assets/games"
        add_game.LOCAL = self.tmp / "arcade.local.json"
        self.data = add_game.load_local()

    def args(self, **kw):
        base = dict(exe=None, title=None, id=None, year=None, studio=None, license="", desc=None, source=None,
                    icon="floppy", cycles=None, yes=True, force=False)
        base.update(kw)
        return Namespace(**base)

    def bundle(self, gid):
        return zipfile.ZipFile(add_game.GAMES_DIR / f"{gid}.jsdos")

    def test_detects_game_exe_and_skips_installers(self):
        z = self.tmp / "space_quest_v1.2_DOS.zip"
        make_zip(z, {"SQ/SQ.EXE": b"x" * 50000, "SQ/INSTALL.EXE": b"x", "SQ/SETUP.EXE": b"x", "SQ/README.TXT": b"r"})
        self.assertTrue(add_game.add(z, self.args(), self.data))
        g = self.data["games"][0]
        self.assertEqual((g["id"], g["title"], g["exe"]), ("space-quest", "Space Quest", "SQ/SQ.EXE"))
        conf = self.bundle("space-quest").read(".jsdos/dosbox.conf").decode()
        self.assertIn("cd \\SQ\nSQ.EXE", conf)
        self.assertIn("autolock=true", conf)

    def test_unwraps_zip_inside_zip(self):
        inner = io.BytesIO()
        make_zip(inner, {"CAVE.COM": b"c", "DATA.DAT": b"d"})
        z = self.tmp / "cave.zip"
        make_zip(z, {"cave-inner.zip": inner.getvalue()})
        self.assertTrue(add_game.add(z, self.args(), self.data))
        self.assertIn("CAVE.COM", self.bundle("cave").namelist())

    def test_explicit_exe_and_metadata(self):
        z = self.tmp / "x.zip"
        make_zip(z, {"A.EXE": b"a", "B/PLAY.BAT": b"b"})
        add_game.add(z, self.args(exe="B\\PLAY.BAT", title="Mi Juego", year=1993, studio="Estudio"), self.data)
        g = self.data["games"][0]
        self.assertEqual((g["exe"], g["year"], g["studio"], g["id"]), ("B/PLAY.BAT", 1993, "Estudio", "mi-juego"))

    def test_duplicate_needs_force(self):
        z = self.tmp / "dup.zip"
        make_zip(z, {"DUP.EXE": b"d"})
        self.assertTrue(add_game.add(z, self.args(), self.data))
        self.assertFalse(add_game.add(z, self.args(), self.data))
        self.assertTrue(add_game.add(z, self.args(force=True), self.data))
        self.assertEqual(len(self.data["games"]), 1)

    def test_saves_sorted_catalogue(self):
        for name in ("zeta", "alpha"):
            z = self.tmp / f"{name}.zip"
            make_zip(z, {f"{name.upper()}.EXE": b"x"})
            add_game.add(z, self.args(), self.data)
        add_game.save_local(self.data)
        saved = json.loads(add_game.LOCAL.read_text())
        self.assertEqual([g["id"] for g in saved["games"]], ["alpha", "zeta"])


if __name__ == "__main__":
    unittest.main()
