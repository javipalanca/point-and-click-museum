"""tools/ia_inspect.py against the fake Internet Archive of tests/fixtures/fake_sources.py: what each item holds,
read from the zips' index with partial requests, without downloading them."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class InspectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "tests/fixtures/fake_sources.py")], stdout=subprocess.PIPE, text=True)
        port = cls.srv.stdout.readline().strip()
        os.environ["PCM_IA_BASE"] = f"http://127.0.0.1:{port}"
        os.environ["PCM_GAMES_TEST_HOSTS"] = "127.0.0.1"
        sys.path.insert(0, str(ROOT / "tools"))
        for m in ("sync_catalog", "ia_inspect"):
            sys.modules.pop(m, None)
        import ia_inspect
        cls.ia = ia_inspect

    @classmethod
    def tearDownClass(cls):
        cls.srv.kill()
        cls.srv.wait()

    def test_dos_game_with_its_installer(self):
        r = self.ia.inspect("msdos_quest_1991")
        self.assertEqual(r["page"], "https://archive.org/details/msdos_quest_1991")
        self.assertEqual(r["best"], "QUEST.ZIP")
        game = next(z for z in r["zips"] if z["name"] == "QUEST.ZIP")
        self.assertEqual(game["verdict"], "dosbox")
        self.assertEqual(game["suggested"], "QUEST/QUEST.EXE")
        self.assertEqual(game["programs"][0]["type"], "dos")
        extras = next(z for z in r["zips"] if z["name"] == "QUEST_EXTRAS.ZIP")
        self.assertEqual(extras["verdict"], "none", "an installer alone does not start the game")
        self.assertTrue(extras["programs"][0]["installer"])

    def test_windows_only(self):
        z = self.ia.inspect("win_quest_1998")["zips"][0]
        self.assertEqual(z["verdict"], "windows")       # read from a deflated program's first bytes
        self.assertEqual(z["programs"][0]["type"], "windows")
        self.assertIsNone(z["suggested"])

    def test_scummvm_data(self):
        r = self.ia.inspect("sky_full")
        self.assertEqual(r["zips"][0]["verdict"], "scummvm")
        self.assertEqual(r["zips"][0]["scummvm"]["engine"], "sky")

    def test_bad_identifier(self):
        with self.assertRaises(self.ia.InspectError):
            self.ia.inspect("../etc")


if __name__ == "__main__":
    unittest.main()
