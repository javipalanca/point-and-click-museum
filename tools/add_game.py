#!/usr/bin/env python3
"""Add games to the DOSBox room straight from the .zip you downloaded (DOS games or ScummVM games).

    python3 tools/add_game.py ~/Downloads/game.zip                 # detects the executable, asks if unsure
    python3 tools/add_game.py ~/Downloads/*.zip --yes              # several at once, best guess, no questions
    python3 tools/add_game.py game.zip --exe GAME/START.BAT --title "My Game" --year 1993 --studio "Studio"
    python3 tools/add_game.py bundle.jsdos --title "Ready-made bundle"
    python3 tools/add_game.py --list
    python3 tools/add_game.py --remove my-game

It detects the kind of game:
  * ScummVM data (Beneath a Steel Sky, LucasArts/Sierra data files, AGS games…) -> runs in ScummVM (web build)
  * a DOS program (.EXE/.COM/.BAT)                                               -> runs in DOSBox
Force one with --engine dosbox|scummvm.

For each game it writes:
    assets/games/<id>.jsdos     the js-dos bundle (zip + .jsdos/dosbox.conf), or
    assets/scummvm/<id>.zip     the game data for ScummVM
    data/arcade.local.json      the catalogue entry (title, year, studio, licence, description)
Both paths are in .gitignore: your games stay on your computer and never reach the repository.
Run `python3 build.py` afterwards to see them in the DOSBox room.

Only add games you are allowed to use. Games that need an installer, a CD image or a specific
memory setup may need --exe / --cycles, or editing the generated dosbox.conf.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.jsdos import make_bundle  # noqa: E402

GAMES_DIR = ROOT / "assets" / "games"
SVM_DIR = ROOT / "assets" / "scummvm"
SVM_BUILT = ROOT / "vendor" / "scummvm" / "scummvm.js"
LOCAL = ROOT / "data" / "arcade.local.json"
RUNNABLE = (".exe", ".com", ".bat")
# helper programs that are almost never the game itself
NOT_THE_GAME = re.compile(r"^(install|setup|uninst|unins\d*|config|setsound|sound|setblast|setmidi|dos4gw|dos32a|cwsdpmi|"
                          r"pmodew|pkunzip|pkzip|lha|arj|unzip|readme|read|manual|catalog|order|patch|update|vesa|univbe|"
                          r"mouse|ctmouse|emm386|himem|command|go32|keyb|mode|choice|cdplay|vgaset|setup\w*)\.\w+$", re.I)
DEFAULT_DESC = {
    "es": "Juego añadido desde tu colección local.",
    "en": "Game added from your local collection.",
    "de": "Spiel aus deiner lokalen Sammlung.",
    "fr": "Jeu ajouté depuis votre collection locale.",
}


# data files that identify games ScummVM can run (engine id -> test on lower-case base names)
SCUMMVM_SIGNATURES = [
    ("sky", lambda n: {"sky.dnr", "sky.dsk"} <= n),
    ("queen", lambda n: bool({"queen.1", "queen.1c"} & n)),
    ("lure", lambda n: "disk1.vga" in n),
    ("drascula", lambda n: "packet.001" in n),
    ("dreamweb", lambda n: any(re.match(r"dreamw\w*\.r00$", x) for x in n)),
    ("teenagent", lambda n: {"on.res", "off.res"} <= n),
    ("cge", lambda n: {"vol.cat", "vol.dat"} <= n),
    ("sci", lambda n: "resource.map" in n),
    ("agi", lambda n: ("logdir" in n and "picdir" in n) or any(x.endswith("dir") and "vol.0" in n for x in n) or any(x.endswith(".wag") for x in n)),
    ("scumm", lambda n: any(re.match(r"(\d\d\.lfl|.+\.(la0|he0|sou))$", x) for x in n)
              or any(x.endswith(".000") and x != "resource.000" for x in n)),
    ("ags", lambda n: "ac2game.dat" in n or any(x.endswith(".ags") for x in n)),
]
AGS_MAGIC = b"Adventure Creator Game File"


def is_windows_exe(data: bytes) -> bool:
    """MZ executables with a PE header are Windows programs: DOSBox cannot run them."""
    if data[:2] != b"MZ" or len(data) < 0x40:
        return False
    off = int.from_bytes(data[0x3C:0x40], "little")
    return data[off:off + 4] == b"PE\0\0"


def detect_engine(files: dict[str, bytes]) -> tuple[str | None, str]:
    """('sky', 'GAME') for ScummVM games (engine, folder holding the data), (None, '') otherwise."""
    by_dir: dict[str, set] = {}
    for name in files:
        p = PurePosixPath(name)
        by_dir.setdefault(str(p.parent) if str(p.parent) != "." else "", set()).add(p.name.lower())
    for engine, test in SCUMMVM_SIGNATURES:
        for folder, names in sorted(by_dir.items(), key=lambda kv: kv[0].count("/")):
            if test(names):
                return engine, folder
    for name, data in files.items():  # Windows AGS games carry the game inside the .exe
        if name.lower().endswith(".exe") and is_windows_exe(data) and AGS_MAGIC in data:
            parent = str(PurePosixPath(name).parent)
            return "ags", "" if parent == "." else parent
    return None, ""


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "game"


def guess_title(stem: str) -> str:
    """'monkey_island-1.2' -> 'Monkey Island'"""
    t = re.sub(r"[\s_\-.]+", " ", stem)
    t = re.sub(r"\b(v?\d+(\.\d+)*|dos|pc|floppy|cd|eng|en|es|esp|de|fr|full|game)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t.title() if t else stem


def read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        files = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
                continue
            files[name] = z.read(info)
    # one zip inside another (common on download sites): unwrap it
    if len(files) == 1:
        (only, data), = files.items()
        if only.lower().endswith(".zip"):
            inner = path.with_name("._inner.zip")
            inner.write_bytes(data)
            try:
                return read_zip(inner)
            finally:
                inner.unlink()
    return files


def candidates(files: dict[str, bytes], stem: str) -> list[tuple[int, str]]:
    key = slugify(stem).replace("-", "")[:8]
    out = []
    for name in files:
        p = PurePosixPath(name)
        if p.suffix.lower() not in RUNNABLE or NOT_THE_GAME.match(p.name) or is_windows_exe(files[name]):
            continue
        score = 10 - 3 * (len(p.parts) - 1)                      # closer to the root is better
        base = slugify(p.stem).replace("-", "")
        if key and (base.startswith(key[:4]) or key.startswith(base[:4])):
            score += 6                                            # name looks like the zip
        if p.suffix.lower() == ".exe":
            score += 2
        if p.suffix.lower() == ".bat" and re.match(r"^(play|start|run|go|game)\.", p.name, re.I):
            score += 5                                            # launcher scripts
        if len(files[name]) > 40_000:
            score += 1
        out.append((score, name))
    return sorted(out, key=lambda x: (-x[0], x[1]))


def choose_exe(files, stem, given, assume_yes) -> str:
    if given:
        g = given.replace("\\", "/").lower()
        for name in files:
            if name.lower() == g or name.lower().endswith("/" + g):
                return name
        sys.exit(f"  error: {given} is not in the archive")
    cands = candidates(files, stem)
    if not cands:
        if any(is_windows_exe(d) for n, d in files.items() if n.lower().endswith(".exe")):
            sys.exit("  error: this is a Windows game; DOSBox only runs DOS programs and ScummVM does not recognise it")
        sys.exit("  error: no DOS .EXE/.COM/.BAT found; use --exe (it may need an installer first)")
    clear = len(cands) == 1 or cands[0][0] - cands[1][0] >= 4
    if clear or assume_yes or not sys.stdin.isatty():
        if not clear:
            print(f"  note: several candidates, using {cands[0][1]} (others: {', '.join(c for _, c in cands[1:5])})")
        return cands[0][1]
    print("  Which program starts the game?")
    for i, (_, c) in enumerate(cands[:12], 1):
        print(f"   {i:>2}. {c}")
    while True:
        a = input(f"  number [1]: ").strip() or "1"
        if a.isdigit() and 1 <= int(a) <= min(12, len(cands)):
            return cands[int(a) - 1][1]


def official_for(engine: str | None) -> dict | None:
    """The data/arcade.json entry waiting for this ScummVM game (e.g. the official freeware), if any."""
    if not engine:
        return None
    games = json.loads((ROOT / "data/arcade.json").read_text("utf-8"))["games"]
    return next((g for g in games if g.get("svmEngine") == engine and not g.get("bundle")), None)


def load_local() -> dict:
    if LOCAL.exists():
        return json.loads(LOCAL.read_text("utf-8"))
    return {"_comment": "Local games (not versioned). Managed by tools/add_game.py.", "games": []}


def save_local(data: dict):
    data["games"].sort(key=lambda g: g["title"].lower())
    LOCAL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def add(path: Path, args, data: dict) -> bool:
    print(f"· {path.name}")
    if not path.exists():
        print("  error: file not found")
        return False
    title = args.title or guess_title(path.stem)
    gid = args.id or slugify(title)
    existing = next((g for g in data["games"] if g["id"] == gid), None)
    if existing and not args.force:
        print(f"  skipped: '{gid}' already exists (use --force to replace)")
        return False
    exe, svm_engine = None, None
    if path.suffix.lower() == ".jsdos":
        GAMES_DIR.mkdir(parents=True, exist_ok=True)
        out = GAMES_DIR / f"{gid}.jsdos"
        out.write_bytes(path.read_bytes())
    elif zipfile.is_zipfile(path):
        files = read_zip(path)
        engine, folder = detect_engine(files)
        has_dos = bool(candidates(files, path.stem))
        use = args.engine
        if use == "auto":
            if engine and (SVM_BUILT.exists() or not has_dos):
                use = "scummvm"
            elif engine and has_dos:
                use = "dosbox"
                print(f"  note: ScummVM ({engine}) would also run it, but vendor/scummvm is not built; using DOSBox")
            else:
                use = "dosbox"
        if use == "scummvm":
            if not engine:
                print("  error: ScummVM does not recognise these files (use --engine dosbox for DOS games)")
                return False
            svm_engine = engine
            known = official_for(engine) if not (args.title or args.id) else None
            if known:  # e.g. the official Beneath a Steel Sky zip fills the catalogue entry
                title, gid = known["title"], known["id"]
                print(f"  recognised: {title} (listed in data/arcade.json)")
            prefix = folder + "/" if folder else ""
            game_files = {n[len(prefix):]: d for n, d in files.items() if n.startswith(prefix)}
            SVM_DIR.mkdir(parents=True, exist_ok=True)
            out = SVM_DIR / f"{gid}.zip"
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                for n, d in sorted(game_files.items()):
                    z.writestr(n, d)
            if not SVM_BUILT.exists():
                print("  note: build ScummVM once with tools/build_scummvm.sh to play it")
        else:
            exe = choose_exe(files, path.stem, args.exe, args.yes)
            GAMES_DIR.mkdir(parents=True, exist_ok=True)
            out = GAMES_DIR / f"{gid}.jsdos"
            out.write_bytes(make_bundle(files, exe, args.cycles))
    else:
        print("  error: not a .zip or .jsdos file")
        return False
    entry = {
        "id": gid, "title": title, "year": args.year, "studio": args.studio or "—", "icon": args.icon,
        "bundle": f"{out.parent.name}/{out.name}",
        "engine": "scummvm" if svm_engine else "dosbox", "license": args.license, "local": True,
        "desc": {k: (args.desc or v) for k, v in DEFAULT_DESC.items()},
    }
    if not args.desc:
        entry["autoDesc"] = True
    if exe:
        entry["exe"] = exe
    if svm_engine:
        entry["svmEngine"] = svm_engine
    if args.source:
        entry["source"] = args.source
    data["games"] = [g for g in data["games"] if g["id"] != gid] + [entry]
    size = out.stat().st_size // 1024
    where = f"{out.parent.name}/{out.name}"
    print(f"  ok: {title} -> assets/{where} ({size} KiB)" + (f", DOSBox runs {exe}" if exe else "") + (f", ScummVM engine {svm_engine}" if svm_engine else ""))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help=".zip or .jsdos files")
    ap.add_argument("--exe", help="program that starts the game, inside the zip (e.g. GAME/START.BAT)")
    ap.add_argument("--title", help="title shown in the catalogue (default: from the file name)")
    ap.add_argument("--id", help="identifier / file name (default: from the title)")
    ap.add_argument("--year", type=int, help="release year")
    ap.add_argument("--studio", help="developer or publisher")
    ap.add_argument("--license", default="", help="licence label shown as a chip, e.g. Freeware (default: none)")
    ap.add_argument("--desc", help="description (same text for every language)")
    ap.add_argument("--source", help="URL where the game comes from")
    ap.add_argument("--icon", default="floppy", help="sprite name from data/sprites.json (default: floppy)")
    ap.add_argument("--cycles", help="DOSBox cpu cycles, e.g. 20000 for games that run too fast")
    ap.add_argument("--engine", choices=("auto", "dosbox", "scummvm"), default="auto",
                    help="auto: ScummVM if it recognises the data files (and is built), else DOSBox")
    ap.add_argument("-y", "--yes", action="store_true", help="never ask: take the best executable guess")
    ap.add_argument("--force", action="store_true", help="replace a game with the same id")
    ap.add_argument("--list", action="store_true", help="list local games")
    ap.add_argument("--remove", metavar="ID", help="remove a local game and its bundle")
    args = ap.parse_args()

    sprites = json.loads((ROOT / "data/sprites.json").read_text("utf-8"))["sprites"]
    if args.icon not in sprites:
        ap.error(f"unknown icon {args.icon}; choose one of: {', '.join(sorted(sprites))}")
    data = load_local()

    if args.list:
        for g in data["games"]:
            ok = (ROOT / "assets" / g["bundle"]).exists()
            print(f"{g['id']:<32} {g['title']:<40} {g.get('year') or '':<5} {g['studio']}" + ("" if ok else "  (bundle missing)"))
        print(f"{len(data['games'])} local game(s)")
        return 0
    if args.remove:
        g = next((g for g in data["games"] if g["id"] == args.remove), None)
        if not g:
            print(f"no local game '{args.remove}'")
            return 1
        (ROOT / "assets" / g["bundle"]).unlink(missing_ok=True)
        data["games"].remove(g)
        save_local(data)
        print(f"removed {args.remove}")
        return 0
    if not args.files:
        ap.print_help()
        return 1
    if len(args.files) > 1 and (args.title or args.id or args.exe):
        ap.error("--title, --id and --exe only make sense with a single file")

    added = sum(add(p.expanduser(), args, data) for p in args.files)
    save_local(data)
    print(f"\n{added} game(s) added, {len(data['games'])} in the local catalogue. Now run: python3 build.py")
    return 0 if added or not args.files else 1


if __name__ == "__main__":
    raise SystemExit(main())
