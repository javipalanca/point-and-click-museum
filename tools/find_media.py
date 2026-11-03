#!/usr/bin/env python3
"""Busca portadas, capturas y logos reales para un juego o estudio en fuentes con historial fijo.

Indexa (sin descargar las imágenes) los repositorios de GitHub que usamos como fuente:
  · libretro-thumbnails/<plataforma>  portadas (Named_Boxarts), capturas (Named_Snaps) y títulos (Named_Titles)
  · scummvm/scummvm-web               capturas oficiales de ScummVM (public_html/data/screenshots)
  · HVR88/Monochrome-Gaming-Logos     logotipos de editoras (recreaciones vectoriales)
y propone líneas `src` listas para `data/media.json`, fijadas al commit actual.

Uso:
    python3 tools/find_media.py "Monkey Island 2"                 # busca en todo
    python3 tools/find_media.py "Gemini Rue" --kind cover
    python3 tools/find_media.py "LucasArts" --kind logo
    python3 tools/find_media.py --refresh                        # vuelve a indexar

El índice se guarda en .cache/media-index/ (ignorado por git). Necesita git y acceso a github.com.
Después: añade el elemento a data/media.json, ejecuta tools/fetch_media.py y MIRA la imagen (edición correcta,
no un port ni un remake) antes de hacer commit. Para Wikipedia/Wikimedia usa `wikipedia:` o `commons:` directamente.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "media-index"
LIBRETRO = ["DOS", "ScummVM", "Commodore_-_Amiga", "Atari_-_ST", "Commodore_-_64", "Sinclair_-_ZX_Spectrum",
            "Amstrad_-_CPC", "Microsoft_-_MSX", "NEC_-_PC-98", "Sega_-_Mega-CD_-_Sega_CD", "Sony_-_PlayStation",
            "Nintendo_-_Wii", "Nintendo_-_Nintendo_DS", "Sony_-_PlayStation_3", "Nintendo_-_Wii_U"]
OTHER = {"scummvm-web": "scummvm/scummvm-web", "logos": "HVR88/Monochrome-Gaming-Logos"}


def repo_list(slug: str, refresh: bool) -> tuple[str, list[str]]:
    name = slug.replace("/", "__")
    d, idx = CACHE / name, CACHE / (name + ".txt")
    if refresh or not idx.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        if not d.exists():
            subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1",
                            f"https://github.com/{slug}", str(d)], check=True)
        else:
            subprocess.run(["git", "-C", str(d), "fetch", "-q", "--depth", "1", "origin", "HEAD"], check=True)
            subprocess.run(["git", "-C", str(d), "update-ref", "HEAD", "FETCH_HEAD"], check=True)
        files = subprocess.run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", "HEAD"],
                               capture_output=True, text=True, check=True).stdout
        commit = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        idx.write_text(commit + "\n" + files, "utf-8")
    lines = idx.read_text("utf-8").splitlines()
    return lines[0], lines[1:]


def norm(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(the|a|an|of|and)\b", " ", s.replace("&", " and ").replace("_", " "))
    return [w for w in re.split(r"[^a-z0-9]+", s) if w]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--kind", choices=["cover", "screenshot", "title", "logo", "all"], default="all")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--max", type=int, default=12)
    a = ap.parse_args()
    q = norm(a.query)
    sources = []
    if a.kind in ("cover", "screenshot", "title", "all"):
        sources += [(f"libretro-thumbnails/{r}", r) for r in LIBRETRO]
    if a.kind in ("screenshot", "all"):
        sources.append((OTHER["scummvm-web"], "scummvm-web"))
    if a.kind in ("logo", "all"):
        sources.append((OTHER["logos"], "logos"))
    want = {"cover": "Named_Boxarts/", "screenshot": "Named_Snaps/", "title": "Named_Titles/"}
    for slug, label in sources:
        try:
            commit, files = repo_list(slug, a.refresh)
        except subprocess.CalledProcessError as e:
            print(f"! {slug}: {e}", file=sys.stderr)
            continue
        if not q:
            continue
        hits = []
        for f in files:
            if not f.lower().endswith((".png", ".jpg", ".svg")):
                continue
            if slug.startswith("libretro") and a.kind in want and not f.startswith(want[a.kind]):
                continue
            if label == "scummvm-web" and not f.endswith("_full.png"):
                continue
            words = norm(Path(f).stem if label != "scummvm-web" else f.split("/screenshots/")[-1])
            if all(any(w.startswith(t) for w in words) for t in q):
                hits.append(f)
        hits.sort(key=lambda f: (len(f), f))
        for f in hits[:a.max]:
            print(f"github:{slug}@{commit}/{f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
