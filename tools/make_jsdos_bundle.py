#!/usr/bin/env python3
"""Package a DOS game folder (or .zip) as a js-dos bundle for the DOSBox room.

    python tools/make_jsdos_bundle.py path/to/GAME --exe GAME.EXE --out assets/games/game.jsdos
    python tools/make_jsdos_bundle.py game.zip --exe SKY.EXE --cycles 20000 --out assets/games/sky.jsdos

Then add an entry to data/arcade.json with "bundle": "games/<name>.jsdos" and rebuild.
Only package software you are allowed to redistribute.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.jsdos import files_from_dir, make_bundle  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="game folder or .zip with the DOS files")
    ap.add_argument("--exe", required=True, help="program to run, relative to the game root (e.g. GAME\\START.BAT)")
    ap.add_argument("--out", type=Path, required=True, help="output .jsdos file")
    ap.add_argument("--cycles", help="DOSBox cpu cycles (default: auto)")
    args = ap.parse_args()

    if args.source.is_dir():
        files = files_from_dir(args.source)
    elif zipfile.is_zipfile(args.source):
        with zipfile.ZipFile(args.source) as z:
            files = {n: z.read(n) for n in z.namelist() if not n.endswith("/")}
    else:
        ap.error(f"{args.source} is neither a folder nor a .zip")
    names = {n.replace("\\", "/").upper() for n in files}
    if args.exe.replace("\\", "/").upper() not in names:
        print(f"warning: {args.exe} not found in the source files", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(make_bundle(files, args.exe, args.cycles))
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KiB, {len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
