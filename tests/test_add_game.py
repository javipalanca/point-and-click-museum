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
        add_game.SVM_DIR = self.tmp / "assets/scummvm"
        add_game.SVM_BUILT = self.tmp / "vendor/scummvm/scummvm.js"   # not built unless a test creates it
        self.data = add_game.load_local()

    def args(self, **kw):
        base = dict(exe=None, title=None, id=None, year=None, studio=None, license="", desc=None, source=None,
                    icon="floppy", cycles=None, yes=True, force=False, engine="auto")
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


    # ---- ScummVM ----
    def pe_exe(self, extra=b""):
        head = bytearray(b"MZ" + b"\0" * 0x3E)
        head[0x3C:0x40] = (0x40).to_bytes(4, "little")
        return bytes(head) + b"PE\0\0" + b"\0" * 64 + extra

    def test_scummvm_data_in_subfolder(self):
        z = self.tmp / "bass-cd-1.2.zip"
        make_zip(z, {"bass/sky.dnr": b"d", "bass/sky.dsk": b"k", "bass/readme.txt": b"r"})
        self.assertTrue(add_game.add(z, self.args(title="Beneath a Steel Sky"), self.data))
        g = self.data["games"][0]
        self.assertEqual((g["engine"], g["svmEngine"], g["bundle"]), ("scummvm", "sky", "scummvm/beneath-a-steel-sky.zip"))
        names = zipfile.ZipFile(add_game.SVM_DIR / "beneath-a-steel-sky.zip").namelist()
        self.assertEqual(sorted(names), ["readme.txt", "sky.dnr", "sky.dsk"])  # folder stripped

    def test_scumm_data_files(self):
        z = self.tmp / "monkey.zip"
        make_zip(z, {"MONKEY.000": b"a", "MONKEY.001": b"b"})
        add_game.add(z, self.args(), self.data)
        self.assertEqual(self.data["games"][0]["svmEngine"], "scumm")

    def test_windows_ags_game_goes_to_scummvm(self):
        z = self.tmp / "indie.zip"
        make_zip(z, {"Indie/Indie.exe": self.pe_exe(b"xx Adventure Creator Game File v2 xx"), "Indie/acsetup.cfg": b"c"})
        add_game.add(z, self.args(), self.data)
        g = self.data["games"][0]
        self.assertEqual((g["engine"], g["svmEngine"]), ("scummvm", "ags"))

    def test_windows_game_is_rejected(self):
        z = self.tmp / "win.zip"
        make_zip(z, {"WIN.EXE": self.pe_exe()})
        with self.assertRaises(SystemExit):
            add_game.add(z, self.args(), self.data)

    def test_official_freeware_zip_fills_catalogue_entry(self):
        z = self.tmp / "bass-cd-1.2.zip"
        make_zip(z, {"sky.dnr": b"d", "sky.dsk": b"k"})
        add_game.add(z, self.args(), self.data)
        g = self.data["games"][0]
        self.assertEqual((g["id"], g["title"]), ("beneath-a-steel-sky", "Beneath a Steel Sky"))

    def test_dos_exe_preferred_until_scummvm_is_built(self):
        z = self.tmp / "lure.zip"
        files = {"LURE.EXE": b"x" * 50000, "DISK1.VGA": b"v"}
        make_zip(z, files)
        add_game.add(z, self.args(title="Lure"), self.data)
        self.assertEqual(self.data["games"][0]["engine"], "dosbox")
        add_game.SVM_BUILT.parent.mkdir(parents=True)
        add_game.SVM_BUILT.write_text("// built")
        add_game.add(z, self.args(title="Lure", force=True), self.data)
        self.assertEqual(self.data["games"][0]["engine"], "scummvm")
        add_game.add(z, self.args(title="Lure", force=True, engine="dosbox"), self.data)
        self.assertEqual(self.data["games"][0]["engine"], "dosbox")


if __name__ == "__main__":
    unittest.main()
