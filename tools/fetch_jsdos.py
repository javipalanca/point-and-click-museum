#!/usr/bin/env python3
"""Download js-dos from npm into vendor/js-dos so the DOSBox room works without a CDN
(needed on hosts with a strict Content-Security-Policy).

    python tools/fetch_jsdos.py                 # version from data/arcade.json
    python tools/fetch_jsdos.py --tarball js-dos-8.3.20.tgz   # use a tarball you already have
    python tools/fetch_jsdos.py --with-dosbox-x # also copy the larger DOSBox-X backend (~7 MB)
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ["js-dos.js", "js-dos.css", "emulators/emulators.js", "emulators/wdosbox.js", "emulators/wdosbox.wasm",
        "emulators/wlibzip.js", "emulators/wlibzip.wasm"]
DOSBOX_X = ["emulators/wdosbox-x.js", "emulators/wdosbox-x.wasm"]


def main() -> int:
    cfg = json.loads((ROOT / "data/arcade.json").read_text("utf-8"))["emulator"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default=cfg["version"])
    ap.add_argument("--tarball", type=Path, help="local npm tarball instead of downloading")
    ap.add_argument("--with-dosbox-x", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "vendor/js-dos")
    args = ap.parse_args()

    if args.tarball:
        data = args.tarball.read_bytes()
    else:
        url = f"https://registry.npmjs.org/{cfg['package']}/-/{cfg['package']}-{args.version}.tgz"
        print("downloading", url)
        with urllib.request.urlopen(url) as r:
            data = r.read()
    wanted = BASE + (DOSBOX_X if args.with_dosbox_x else [])
    if args.out.exists():
        shutil.rmtree(args.out)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for rel in wanted:
            member = tar.extractfile(f"package/dist/{rel}")
            dest = args.out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(member.read())
            print(f"  {rel}  {dest.stat().st_size // 1024} KiB")
    (args.out / "VERSION").write_text(args.version + "\n")
    print("js-dos", args.version, "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
