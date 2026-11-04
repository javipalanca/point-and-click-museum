#!/usr/bin/env python3
"""Works out which adventure a zip contains (best effort) and finds its original box art.

    python3 tools/identify_game.py ~/juegos/MONKEY2.zip [--engine scumm] [--cover]

Clues, strongest first:
  1. data files whose name is the game's ScummVM id (MONKEY2.000, TENTACLE.000, FT.LA0, COMI.LA0, SKY.DNR…),
     AGI v3 directory files (KQ4DIR, GRDIR…) and executables named after the game (KQ5.EXE, INDY.EXE);
  2. the name of the zip and of the folders inside it, compared with the titles of the museum's timeline and of
     the ScummVM catalogue (data/murray_kb/scummvm-games.jsonl, ~1200 games with year and company), ignoring case,
     accents, "The", punctuation and Roman numerals ("Kings_Quest_5_DOS.zip" -> King's Quest V).
A timeline game brings its four-language description and its cover from data/media.json. Any other game gets the
box art of the PC release from libretro-thumbnails (GitHub, pinned to a commit; the file name, shown in the credit,
says which edition it is). Without network access the game is still identified, just without a cover.
Standard library only.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "PointAndClickMuseum-games/1.0 (+https://github.com/javipalanca/point-and-click-museum)"
COVER_REPOS = ("DOS", "ScummVM")  # PC box art first; the ScummVM set covers the rest
INDEX_DAYS = 7

# names that say nothing about which game it is
GENERIC = set("""
game games setup install installer uninst uninstall config sound setsound sierra sciv scidhuv sci scidos agi agidata
resource resources data start play run go main menu launch launcher loader intro dos dosbox cd cdrom disk disc floppy
vol logdir picdir viewdir snddir words object objects readme manual patch update english eng spanish german french
full version demo vga ega cga pc win windows exe com bat files drive extras music speech voices voice sfx
""".split())
# AGI v3 games prefix their directory files with a short code
AGI_PREFIX = {"kq4": "kq4", "gr": "goldrush", "mh": "mh1", "mh2": "mh2"}
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
# editions we do not want as "the original cover" unless the title asks for them
NOT_ORIGINAL = re.compile(r"\b(demo|beta|proto|sample|remaster\w*|special edition|anniversary|windows|mac|amiga|"
                          r"fm-towns|pc-98|sega|playstation|ios|android|steam|gog|collection|compilation|bundle)\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("'", "").replace("_", " ")
    words = [ROMAN.get(w, w) for w in re.split(r"[^a-z0-9]+", s) if w]
    if words[:1] == ["the"]:
        words = words[1:]
    return " ".join(words)


def guess_title(stem: str) -> str:
    """'Monkey_Island_2_LeChucks_Revenge_DOS_EN_v1.1' -> 'Monkey Island 2 LeChucks Revenge'"""
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", stem)
    t = re.sub(r"[\s_\-.]+", " ", t)
    t = re.sub(r"\b(v?\d+(\.\d+)+|dos|pc|floppy|cd|cdrom|eng|en|es|esp|spa|de|ger|fr|fre|full|game|vga|ega|cga|"
               r"talkie|gog|rip|install(ed)?)\b", " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------- what we know
_KB = None


def knowledge() -> dict:
    """Titles from the timeline and the ScummVM catalogue, indexed by normalised title and by ScummVM id."""
    global _KB
    if _KB:
        return _KB
    games, by_id = [], {}
    for line in (DATA / "murray_kb" / "scummvm-games.jsonl").read_text("utf-8").splitlines():
        g = json.loads(line)
        _, engine, gid = g["id"].split(":", 2)
        rec = {"title": g["title"], "year": g.get("year"), "studio": g.get("company") or "", "engine": engine, "gameid": gid}
        games.append(rec)
        by_id.setdefault(gid, []).append(rec)
    timeline = json.loads((DATA / "timeline.json").read_text("utf-8"))["games"]
    for t in timeline:
        games.append({"title": t["title"], "year": t["year"], "studio": t["studio"].split(" · ")[0], "engine": "",
                      "gameid": "", "timeline": t["id"]})
    titles = {}
    for g in games:
        for alias in {norm(g["title"]), norm(re.split(r"[:–]| - ", g["title"])[0])}:
            if len(alias) >= 3:
                titles.setdefault(alias, []).append(g)
    _KB = {"games": games, "by_id": by_id, "titles": titles,
           "timeline": {norm(t["title"]): t for t in timeline}, "timeline_by_id": {t["id"]: t for t in timeline}}
    return _KB


def zip_names(path: Path) -> list[str]:
    """File names inside the zip (one level of zip-in-zip unwrapped), without reading the data."""
    with zipfile.ZipFile(path) as z:
        names = [i.filename.replace("\\", "/") for i in z.infolist() if not i.is_dir() and not i.filename.startswith("__MACOSX/")]
        if len(names) == 1 and names[0].lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(z.read(names[0]))) as inner:
                return [i.filename.replace("\\", "/") for i in inner.infolist() if not i.is_dir()]
    return names


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    wa, wb = set(a.split()), set(b.split())
    cover = len(wa & wb) / max(len(wa | wb), 1)
    na, nb = {w for w in wa if w.isdigit()}, {w for w in wb if w.isdigit()}
    if na and nb and not na & nb:  # Larry 1 is not Larry 7, King's Quest 5 is not King's Quest 6
        return max(ratio, cover) * 0.6
    return max(ratio, cover)


def identify(names: list[str], stem: str, engine: str | None = None, hint: str | None = None) -> dict | None:
    """-> {"title", "year", "studio", "timeline"?, "gameid"?, "score", "why"} or None."""
    kb = knowledge()
    found: list[tuple[float, dict, str]] = []

    def consistent(rec):  # a SCUMM data file cannot be an AGI game
        return not engine or not rec.get("engine") or rec["engine"] == engine or (engine == "scumm" and rec["engine"] == "scumm")

    zip_title = norm(guess_title(stem))

    # 1. file names that are ScummVM game ids
    for n in names:
        p = PurePosixPath(n)
        s, ext = p.stem.lower(), p.suffix.lower()
        cands = []
        if ext in (".000", ".la0", ".he0", ".sm0", ".dnr", ".exe", ".com", ".bat") and s not in GENERIC:
            cands.append(s)
        if ext == "" and s.endswith("dir") and s[:-3] in AGI_PREFIX:
            cands.append(AGI_PREFIX[s[:-3]])
        if s == "monkey1":
            cands.append("monkey")
        for c in cands:
            for rec in kb["by_id"].get(c, []):
                # data files are reliable; an executable name is only a hint (PRINCE.EXE is also Prince of Persia)
                sc = 0.97 if ext not in (".exe", ".com", ".bat") else 0.85
                if ext in (".exe", ".com", ".bat") and len(zip_title) >= 4 and hint is None \
                        and similarity(zip_title, norm(rec["title"])) < 0.5 and c != zip_title.replace(" ", ""):
                    sc *= 0.7  # the zip is called something else
                found.append((sc if consistent(rec) else 0.6, rec, f"file {p.name}"))

    # 2. names: the zip, the folders inside it, a title given by hand
    texts = [(hint, 1.0, "given title")] if hint else []
    texts.append((guess_title(stem), 0.97, f"zip name {stem}"))
    for folder in sorted({PurePosixPath(n).parts[0] for n in names if len(PurePosixPath(n).parts) > 1}):
        texts.append((guess_title(folder), 0.93, f"folder {folder}"))
    for text, weight, why in texts:
        q = norm(text or "")
        if len(q) < 3 or q in GENERIC:
            continue
        for alias, recs in kb["titles"].items():
            sc = similarity(q, alias)
            if sc >= 0.8:
                for rec in recs:
                    found.append((sc * weight * (1 if consistent(rec) else 0.8), rec, why))
        compact = q.replace(" ", "")  # "kq5", "monkey2"
        for rec in kb["by_id"].get(compact, []):
            found.append((0.9 * weight, rec, why + " (ScummVM id)"))
    if not found:
        return None
    score, rec, why = max(found, key=lambda f: (f[0], bool(f[1].get("timeline")), -len(f[1]["title"])))
    if score < 0.78:
        return None
    out = {"title": rec["title"], "year": rec.get("year"), "studio": rec.get("studio") or "", "score": round(score, 2), "why": why}
    if rec.get("gameid"):
        out["gameid"], out["engine"] = rec["gameid"], rec["engine"]
    tl = rec.get("timeline") or timeline_for(rec)
    if tl:  # the museum has a record of it: its title, year and studio win
        t = kb["timeline_by_id"][tl]
        out.update(title=t["title"], year=t["year"], studio=t["studio"].split(" · ")[0], timeline=tl, desc=t["text"])
    return out


def timeline_for(rec: dict) -> str | None:
    """The museum's record of a catalogue game: same title, or one title inside the other with the same year
    ("Maniac Mansion: Day of the Tentacle" in ScummVM is "Day of the Tentacle" in the timeline)."""
    kb, t = knowledge(), norm(rec["title"])
    if t in kb["timeline"]:
        return kb["timeline"][t]["id"]
    for name, g in kb["timeline"].items():
        if g["year"] == rec.get("year") and len(name) >= 6 and (f" {name} " in f" {t} " or f" {t} " in f" {name} "):
            return g["id"]
    return None


# ---------------------------------------------------------------- covers
def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def boxart_index(repo: str, cache: Path) -> tuple[str, list[str]]:
    """(commit, ["Named_Boxarts/Name.png", …]) of libretro-thumbnails/<repo>, cached for a week."""
    idx = cache / f"libretro-{repo}.txt"
    seed = ROOT / ".cache" / "media-index" / f"libretro-thumbnails__{repo}.txt"  # left by tools/find_media.py
    if not idx.exists() and seed.exists():
        lines = seed.read_text("utf-8").splitlines()
        cache.mkdir(parents=True, exist_ok=True)
        idx.write_text("\n".join([lines[0]] + [l for l in lines[1:] if l.startswith("Named_Boxarts/")]), "utf-8")
    if not idx.exists() or time.time() - idx.stat().st_mtime > INDEX_DAYS * 86400:
        try:
            commit = json.loads(http_get(f"https://api.github.com/repos/libretro-thumbnails/{repo}/commits/HEAD"))["sha"]
            root = json.loads(http_get(f"https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/{commit}"))
            sub = next(t["sha"] for t in root["tree"] if t["path"] == "Named_Boxarts")
            tree = json.loads(http_get(f"https://api.github.com/repos/libretro-thumbnails/{repo}/git/trees/{sub}", 60))
            files = ["Named_Boxarts/" + t["path"] for t in tree["tree"]]
        except Exception as api_error:  # API limit or no network: try git, else keep the old index
            try:
                files, commit = git_index(repo, cache)
            except Exception:
                if idx.exists():
                    idx.touch()
                    lines = idx.read_text("utf-8").splitlines()
                    return lines[0], lines[1:]
                raise api_error from None
        cache.mkdir(parents=True, exist_ok=True)
        idx.write_text("\n".join([commit] + files), "utf-8")
    lines = idx.read_text("utf-8").splitlines()
    return lines[0], lines[1:]


def git_index(repo: str, cache: Path) -> tuple[list[str], str]:
    d = cache / f"libretro-{repo}.git"
    if not d.exists():
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", "--depth", "1",
                        f"https://github.com/libretro-thumbnails/{repo}", str(d)], check=True, timeout=300)
    out = subprocess.run(["git", "-C", str(d), "ls-tree", "--name-only", "HEAD", "Named_Boxarts/"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    commit = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return out, commit


def libretro_title(path: str) -> tuple[str, str]:
    """'Named_Boxarts/Secret of Monkey Island, The (1990).png' -> ('secret of monkey island', '(1990)')"""
    name = PurePosixPath(path).stem
    tags = " ".join(re.findall(r"\([^)]*\)|\[[^\]]*\]", name))
    base = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", name).strip().replace("_ ", ": ")
    base = re.sub(r"^(.*), (The|A|An)(?=$|:| -)", r"\2 \1", base)  # "Secret of Monkey Island, The" -> "The Secret…"
    return norm(base), tags


def find_cover(title: str, year: int | None, cache: Path) -> str | None:
    """github:libretro-thumbnails/<repo>@<commit>/Named_Boxarts/<file> for the original PC box, or None."""
    want, want_short = norm(title), norm(re.split(r"[:–]| - ", title)[0])
    best, errors = None, []
    for rank, repo in enumerate(COVER_REPOS):
        try:
            commit, files = boxart_index(repo, cache)
        except Exception as e:
            errors.append(e)
            continue
        for f in files:
            if not f.lower().endswith(".png"):
                continue
            name, tags = libretro_title(f)
            sc = 1.0 if name == want else 0.92 if name == want_short or norm(name.split(":")[0]) == want else similarity(name, want)
            if sc < 0.9:
                continue
            bad = bool(NOT_ORIGINAL.search(tags)) and not NOT_ORIGINAL.search(title)
            key = (sc, not bad, bool(year and str(year) in tags), -rank, not tags, -len(f))
            if not best or key > best[0]:
                best = (key, f"github:libretro-thumbnails/{repo}@{commit}/{f}")
    if not best and len(errors) == len(COVER_REPOS):
        raise errors[-1]  # no index could be read: say so, so that the cover is looked for again later
    return best[1] if best else None


def fetch_cover(spec: str, dest: Path) -> dict:
    """Downloads and shrinks the cover (tools/fetch_media.py does the PNG work) -> {page, w, h}."""
    sys.path.insert(0, str(ROOT / "tools"))
    import fetch_media  # noqa: E402
    data, meta = fetch_media.from_github(spec)
    if fetch_media.ext_of(data, spec) != "png":
        raise ValueError("not a PNG")
    data, w, h = fetch_media.shrink_png(data, "cover")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"page": meta["page"], "w": w, "h": h, "src": spec}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("zip", type=Path)
    ap.add_argument("--engine", help="ScummVM engine detected (scumm, sci, agi…), if any")
    ap.add_argument("--title", help="a title you already know")
    ap.add_argument("--cover", action="store_true", help="also look for the box art")
    a = ap.parse_args()
    r = identify(zip_names(a.zip), a.zip.stem, a.engine, a.title)
    print(json.dumps({k: v for k, v in (r or {}).items() if k != "desc"}, ensure_ascii=False, indent=1) if r else "not identified")
    if r and a.cover:
        print(find_cover(r["title"], r.get("year"), ROOT / ".cache" / "games-inbox") or "no cover found")
    return 0 if r else 1


if __name__ == "__main__":
    raise SystemExit(main())
