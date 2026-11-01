#!/usr/bin/env python3
"""Build a copy of the site ready to publish as a claude.ai Artifact.

    python3 tools/export_artifact.py --out /tmp/artifact

Differences from a normal build:
  * links point to .../index.html (the artifact host does not resolve directories)
  * .jsdos bundles are packed into games/bundles.js (the host does not serve .zip files)
  * the root index.html is stripped of <!DOCTYPE>/<html>/<head>/<body>: the host wraps it in its own skeleton
  * files the host does not serve (.jsdos, .nojekyll, VERSION) are removed
It prints the list of supporting files to pass as `files` when publishing.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    subprocess.run([sys.executable, str(ROOT / "build.py"), "--out", str(args.out), "--link-style", "file", "--inline-bundles"], check=True)
    for junk in list(args.out.rglob("*.jsdos")) + [args.out / ".nojekyll", args.out / "vendor/js-dos/VERSION"]:
        if junk.exists():
            junk.unlink()
    index = args.out / "index.html"
    s = index.read_text("utf-8")
    head = re.search(r"<head>(.*?)</head>", s, re.S).group(1)
    head = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*|<title>.*?</title>\s*', "", head)
    body = re.search(r'<body class="([^"]*)">(.*)</body>', s, re.S)
    index.write_text('<title>Point and Click Museum</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
                     + head + f'\n<script>document.body.className="{body.group(1)}"</script>\n' + body.group(2), "utf-8")
    files = sorted(p.relative_to(args.out).as_posix() for p in args.out.rglob("*") if p.is_file() and p != index)
    print(json.dumps([{"path": f} for f in files]))
    print(f"{len(files)} supporting files", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
