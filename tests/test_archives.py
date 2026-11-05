"""Games that do not come as a plain zip (tools/game_fetch.py): a 7z inside a zip, a 7z on its own and CD images
(.iso, mounted in DOSBox as drive D:), and their inspection on the fake Internet Archive (tools/ia_inspect.py)."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import game_fetch  # noqa: E402
import iso9660  # noqa: E402

DOS = (ROOT / "tools/dos/PAINT.COM").read_bytes()
HAS_7Z = bool(game_fetch.seven_zip())


def zbytes(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


def seven(files, work: Path) -> bytes:
    for n, d in files.items():
        (work / n).parent.mkdir(parents=True, exist_ok=True)
        (work / n).write_bytes(d)
    subprocess.run([game_fetch.seven_zip(), "a", "-bd", "-y", "g.7z", *files], cwd=work, capture_output=True, check=True)
    return (work / "g.7z").read_bytes()


class UnpackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_iso_reader_round_trip(self):
        img = iso9660.build({"GAME/GAME.EXE": DOS, "README.TXT": b"hi"})
        read = lambda o, n: img[o:o + n]
        names = {e["name"]: e for e in iso9660.listing(read)}
        self.assertEqual(set(names), {"GAME/GAME.EXE", "README.TXT"})
        self.assertEqual(iso9660.read_file(read, names["GAME/GAME.EXE"]), DOS)

    def test_iso_is_mounted_not_unpacked(self):
        iso = self.tmp / "cd.bin"
        iso.write_bytes(iso9660.build({"QUEST/QUEST.EXE": DOS}))
        files, cd, how = game_fetch.unpack(iso, self.tmp)
        self.assertEqual((files, cd), ({}, iso))
        self.assertIn("CD image", how)

    @unittest.skipUnless(HAS_7Z, "the 7-Zip program is not installed")
    def test_7z_inside_a_zip_with_manual_and_cover(self):
        packed = seven({"SKULLS/SKULLS.EXE": DOS}, self.tmp / "w")
        z = self.tmp / "dl.bin"
        z.write_bytes(zbytes({"S/Manual.pdf": b"%PDF", "S/Skulls.7z": packed, "S/cover.png": b"png", "S/metadata.json": b"{}"}))
        files, cd, how = game_fetch.unpack(z, self.tmp)
        self.assertIsNone(cd)
        self.assertEqual(set(files), {"SKULLS/SKULLS.EXE"})
        self.assertIn("Skulls.7z", how)

    def test_not_an_archive(self):
        f = self.tmp / "x.bin"
        f.write_bytes(b"hello")
        with self.assertRaises(game_fetch.GameError):
            game_fetch.unpack(f, self.tmp)

    def test_cd_bundle_mounts_d(self):
        iso = self.tmp / "cd.iso"
        iso.write_bytes(iso9660.build({"QUEST/QUEST.EXE": DOS}))
        progs, _ = game_fetch.cd_programs(iso)
        self.assertEqual(game_fetch.find_exe(progs, None, "Quest"), "QUEST/QUEST.EXE")
        out = self.tmp / "b.jsdos"
        game_fetch.cd_bundle(iso, "QUEST/QUEST.EXE", None, out)
        with zipfile.ZipFile(out) as zf:
            conf = zf.read(".jsdos/dosbox.conf").decode()
            self.assertEqual(zf.read("cd.iso"), iso.read_bytes())
        self.assertIn("imgmount d cd.iso -t iso\nd:\ncd \\QUEST\nQUEST.EXE", conf)


class InspectArchivesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "tests/fixtures/fake_sources.py")], stdout=subprocess.PIPE, text=True)
        port = cls.srv.stdout.readline().strip()
        os.environ["PCM_IA_BASE"] = f"http://127.0.0.1:{port}"
        os.environ["PCM_GAMES_TEST_HOSTS"] = "127.0.0.1"
        for m in ("sync_catalog", "ia_inspect"):
            sys.modules.pop(m, None)
        import ia_inspect
        cls.ia = ia_inspect

    @classmethod
    def tearDownClass(cls):
        cls.srv.kill()
        cls.srv.wait()

    def test_cd_image_listed_without_downloading_it(self):
        z = self.ia.inspect("cd_quest_1995")["zips"][0]
        self.assertEqual((z["kind"], z["verdict"], z["suggested"], z["cd"]), ("iso", "dosbox", "QUEST/QUEST.EXE", True))
        self.assertTrue(any(p["installer"] for p in z["programs"]))

    @unittest.skipUnless(HAS_7Z, "the 7-Zip program is not installed")
    def test_zip_with_the_game_as_7z(self):
        z = self.ia.inspect("skulls_7z")["zips"][0]
        self.assertEqual(z["verdict"], "nested")
        self.assertEqual(z["inner"], ["Skulls/Skulls.7z"])


if __name__ == "__main__":
    unittest.main()
