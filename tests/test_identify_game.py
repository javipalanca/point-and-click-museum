"""Tests for tools/identify_game.py: which game a zip contains, from file and folder names only."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import identify_game as ig  # noqa: E402


def who(names, stem, engine=None, hint=None):
    r = ig.identify(names, stem, engine, hint)
    return r and (r["title"], r.get("timeline"))


class IdentifyTest(unittest.TestCase):
    def test_data_files_name_the_game(self):
        self.assertEqual(who(["MONKEY2/MONKEY2.000", "MONKEY2/MONKEY2.EXE"], "MI2_GOG", "scumm"),
                         ("Monkey Island 2: LeChuck's Revenge", "monkey-island-2"))
        self.assertEqual(who(["TENTACLE.000"], "game1", "scumm"), ("Day of the Tentacle", "day-of-the-tentacle"))
        self.assertEqual(who(["FT.LA0", "MONSTER.SOU"], "x", "scumm"), ("Full Throttle", "full-throttle"))
        self.assertEqual(who(["KQ4/KQ4DIR", "KQ4/KQ4VOL.0"], "stuff", "agi")[1], "kings-quest-4")

    def test_zip_and_folder_names(self):
        self.assertEqual(who(["KQ5/RESOURCE.MAP", "KQ5/SIERRA.EXE"], "Kings_Quest_5_DOS", "sci")[1], "kings-quest-5")
        self.assertEqual(who(["SIERRA.COM", "LOGDIR"], "Leisure Suit Larry 1 (EGA)", "agi")[1], "leisure-suit-larry")
        self.assertEqual(who(["RESOURCE.MAP"], "Space Quest III", "sci")[0], "Space Quest III: The Pirates of Pestulon")
        self.assertEqual(who(["GAME/GK.EXE"], "download", None, "Gabriel Knight")[1], "gabriel-knight")

    def test_no_wild_guesses(self):
        self.assertIsNone(who(["PRINCE.EXE"], "Prince of Persia"))   # PRINCE.EXE is not The Prince and the Coward
        self.assertIsNone(who(["TOOL.EXE"], "random_utility"))
        self.assertIsNone(who(["SETUP.EXE", "INSTALL.EXE"], "game"))

    def test_libretro_names(self):
        self.assertEqual(ig.libretro_title("Named_Boxarts/Secret of Monkey Island, The (1990).png"),
                         ("secret of monkey island", "(1990)"))
        self.assertEqual(ig.libretro_title("Named_Boxarts/Space Quest III_ The Pirates of Pestulon.png")[0],
                         "space quest 3 the pirates of pestulon")


if __name__ == "__main__":
    unittest.main()
