"""Games that do not come as a plain zip (tools/game_fetch.py): a 7z inside a zip, CD images (.iso, .cue + .bin),
ScummVM first, and their inspection on the fake Internet Archive (tools/ia_inspect.py)."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
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


def cue_bin(data_files, name="GAME", audio_seconds=1):
    data = iso9660.raw(iso9660.build(data_files))
    cue = (f'FILE "{name} (Track 1).bin" BINARY\r\n  TRACK 01 MODE1/2352\r\n    INDEX 01 00:00:00\r\n'
           f'FILE "{name} (Track 2).bin" BINARY\r\n  TRACK 02 AUDIO\r\n    INDEX 01 00:00:00\r\n').encode()
    return {f"{name}.cue": cue, f"{name} (Track 1).bin": data, f"{name} (Track 2).bin": bytes(2352 * 75 * audio_seconds)}


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

    def test_raw_sectors_and_cue_sheet(self):
        img = iso9660.build({"GAME/GAME.EXE": DOS})
        for mode in ("MODE1/2352", "MODE2/2352"):
            raw = iso9660.raw(img, mode)
            self.assertEqual(iso9660.raw_mode(raw[:17 * 2352 + 40]), mode)
            read = iso9660.track_reader(lambda o, n: raw[o:o + n], mode)
            e = iso9660.listing(read)[0]
            self.assertEqual(iso9660.read_file(read, e), DOS)
        tracks = iso9660.parse_cue('FILE "A b.bin" BINARY\n TRACK 01 MODE1/2352\n  INDEX 01 00:00:00\n TRACK 02 AUDIO\n  INDEX 00 01:00:00\n  INDEX 01 01:02:00\n')
        self.assertEqual([(t["file"], t["mode"], t["start"]) for t in tracks], [("A b.bin", "MODE1/2352", 0), ("A b.bin", "AUDIO", 62 * 75)])

    def test_iso_is_mounted_not_unpacked(self):
        iso = self.tmp / "cd.bin"
        iso.write_bytes(iso9660.build({"QUEST/QUEST.EXE": DOS}))
        files, cd, how = game_fetch.unpack(iso, self.tmp)
        self.assertEqual(files, {})
        self.assertEqual(cd.path, iso)
        self.assertIn("CD image", how)

    def test_cue_and_bins_inside_a_zip(self):
        z = self.tmp / "dl.bin"
        z.write_bytes(zbytes({"CD/" + n: d for n, d in cue_bin({"QUEST/QUEST.EXE": DOS}).items()} | {"CD/manual.pdf": b"%PDF"}))
        files, cd, how = game_fetch.unpack(z, self.tmp)
        self.assertEqual(set(files), {"CD/manual.pdf"})
        self.assertEqual([t["mode"] for t in cd.tracks], ["MODE1/2352", "AUDIO"])
        self.assertEqual([e["name"] for e in cd.listing()], ["QUEST/QUEST.EXE"])
        wav = cd.audio()["track02.wav"]
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (2, 2, 44100, 44100))
        extra, mount = cd.bundle()
        self.assertEqual(mount, "cd.cue")
        self.assertEqual(set(extra), {"cd.cue", "cd01.bin", "cd02.bin"})
        self.assertIn(b'FILE "cd02.bin" BINARY', extra["cd.cue"])

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
        cd = game_fetch.CD(iso)
        progs, _ = game_fetch.cd_programs(cd)
        self.assertEqual(game_fetch.find_exe(progs, None, "Quest"), "QUEST/QUEST.EXE")
        out = self.tmp / "b.jsdos"
        game_fetch.cd_bundle({}, cd, "QUEST/QUEST.EXE", True, None, out)
        with zipfile.ZipFile(out) as zf:
            conf = zf.read(".jsdos/dosbox.conf").decode()
            self.assertEqual(zf.read("cd.iso"), iso.read_bytes())
        self.assertIn("imgmount d cd.iso -t iso\nd:\ncd \\QUEST\nQUEST.EXE", conf)


class FakeArchiveTest(unittest.TestCase):
    """prepare() and the inspection against tests/fixtures/fake_sources.py."""

    @classmethod
    def setUpClass(cls):
        cls.srv = subprocess.Popen([sys.executable, str(ROOT / "tests/fixtures/fake_sources.py")], stdout=subprocess.PIPE, text=True)
        cls.base = f"http://127.0.0.1:{cls.srv.stdout.readline().strip()}"
        os.environ["PCM_IA_BASE"] = cls.base
        os.environ["PCM_GAMES_TEST_HOSTS"] = "127.0.0.1"
        for m in ("sync_catalog", "ia_inspect"):
            sys.modules.pop(m, None)
        import ia_inspect
        cls.ia = ia_inspect

    @classmethod
    def tearDownClass(cls):
        cls.srv.kill()
        cls.srv.wait()

    def setUp(self):
        self.cache = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.cache, ignore_errors=True)

    def test_cd_image_listed_without_downloading_it(self):
        z = self.ia.inspect("cd_quest_1995")["zips"][0]
        self.assertEqual((z["kind"], z["verdict"], z["suggested"], z["cd"]), ("iso", "dosbox", "QUEST/QUEST.EXE", True))
        self.assertTrue(any(p["installer"] for p in z["programs"]))

    @unittest.skipUnless(HAS_7Z, "the 7-Zip program is not installed")
    def test_zip_with_the_game_as_7z(self):
        z = self.ia.inspect("skulls_7z")["zips"][0]
        self.assertEqual(z["verdict"], "nested")
        self.assertEqual(z["inner"], ["Skulls/Skulls.7z"])

    def test_scummvm_first_even_with_a_dos_program(self):
        game = {"id": "sky-cd", "title": "Beneath a Steel Sky", "emulator": "dosbox", "run": {"exe": "SKY.EXE"},
                "download": {"url": f"{self.base}/download/cd_sky/SKYCD.ZIP"}}
        r = game_fetch.prepare(game, self.cache, admin=True, switch=True)
        self.assertEqual((r["kind"], r["engine"]), ("svm", "sky"))
        self.assertIn("track02.wav", r["files"], "the CD's music, for ScummVM")
        self.assertIn("SKY.DNR", r["files"])
        ed = dict(game)
        self.assertTrue(game_fetch.detected(ed, r))
        self.assertEqual((ed["emulator"], ed["run"]), ("scummvm", {"svmEngine": "sky"}))
        # the public proxy (switch=False) keeps to what the edition says
        pub = game_fetch.prepare(dict(game, id="sky-cd-public"), self.cache, admin=True)
        self.assertEqual(pub["kind"], "jsdos")

    def test_cue_and_bins_as_separate_files(self):
        r = self.ia.inspect("cd_quest_cue")
        z = r["zips"][0]
        self.assertEqual((z["kind"], z["verdict"], z["suggested"], z["cd"]), ("cue", "dosbox", "QUEST/QUEST.EXE", True))
        self.assertEqual([p["name"] for p in z["parts"]], ["QUESTCUE.cue", "QUESTCUE (Track 1).bin", "QUESTCUE (Track 2).bin"])
        self.assertEqual(z["audioTracks"], 1)
        game = {"id": "quest-cue", "title": "Quest", "emulator": "dosbox", "run": {"exe": "QUEST/QUEST.EXE"},
                "download": {"provider": "archive", "url": z["url"], "parts": z["parts"]}}
        b = game_fetch.prepare(game, self.cache, admin=True, switch=True)
        self.assertEqual((b["kind"], b["exe"], b["onCd"]), ("jsdos", "QUEST/QUEST.EXE", True))
        with zipfile.ZipFile(b["file"]) as zf:
            self.assertEqual(sorted(n for n in zf.namelist() if not n.startswith(".jsdos")), ["cd.cue", "cd01.bin", "cd02.bin"])
            self.assertIn("imgmount d cd.cue -t iso\nd:\ncd \\QUEST\nQUEST.EXE", zf.read(".jsdos/dosbox.conf").decode())


if __name__ == "__main__":
    unittest.main()
