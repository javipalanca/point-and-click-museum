#!/usr/bin/env python3
"""Builds Murray's external knowledge base (data/murray_kb/*.jsonl) from public sources on the internet.

Sources:
  scummvm     the ScummVM website's game catalogue (github.com/scummvm/scummvm-web, data/en/*.yaml, pinned to a
              commit): ~1,200 games with company, year, engine and series. Works wherever GitHub is reachable.
  wikipedia   plain-text extracts of Wikipedia articles (es, en, de, fr) about every game, studio and engine of the
              museum plus the genre's history topics listed below, split into passages, with URL and licence
              (CC BY-SA 4.0). Needs access to *.wikipedia.org.

The curated articles in data/murray_kb/history.json are written by hand from web sources (each lists its URLs);
server/knowledge.py indexes all of it next to the museum's own data.

Usage:
    python3 tools/build_murray_kb.py scummvm
    python3 tools/build_murray_kb.py wikipedia [--langs es,en,de,fr] [--max-chars 900]
    python3 tools/build_murray_kb.py all

Standard library only. Re-run whenever the museum's data changes; commit the resulting files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "murray_kb"
UA = "PointAndClickMuseum-kb/1.0 (+https://github.com/javipalanca/point-and-click-museum)"
SCUMMVM_WEB = "scummvm/scummvm-web"
WIKI_API = "https://{lang}.wikipedia.org/w/api.php"   # overridable for tests with PCM_WIKI_API

# Genre history articles fetched besides the museum's own records (English titles; other languages via langlinks)
TOPICS = ["Adventure game", "Graphic adventure game", "Point-and-click adventure game", "Interactive fiction",
          "Text-based game", "Visual novel", "Escape the room", "Hidden object game", "Walking simulator",
          "Interactive movie", "Full-motion video", "Pixel hunt", "Verb coin", "Inventory (video games)",
          "Infocom", "Sierra Entertainment", "LucasArts", "Lucasfilm Games", "Revolution Software", "Cyan Worlds",
          "Telltale Games", "Double Fine", "Daedalic Entertainment", "Wadjet Eye Games", "Amanita Design",
          "Pendulo Studios", "Coktel Vision", "Cryo Interactive", "Westwood Studios", "Legend Entertainment",
          "Adventure Soft", "Magnetic Scrolls", "Level 9 Computing", "Aventuras AD", "Microïds", "Dynamix",
          "Ron Gilbert", "Tim Schafer", "Dave Grossman", "Roberta Williams", "Ken Williams (gamer)", "Jane Jensen",
          "Al Lowe", "Charles Cecil", "Brian Moriarty", "Steve Meretzky", "Scott Adams (game designer)",
          "Will Crowther", "Don Woods (programmer)", "Hal Barwood", "Noah Falstein", "Benoît Sokal",
          "Ragnar Tørnquist", "Steve Purcell", "Jordan Mechner", "Rand Miller", "Robyn Miller",
          "SCUMM", "Adventure Game Interpreter", "Sierra's Creative Interpreter", "Z-machine", "ScummVM",
          "Adventure Game Studio", "Visionaire Studio", "GrimE", "iMUSE", "Inform", "Professional Adventure Writer",
          "Graphic Adventure Creator", "Kickstarter", "Interactive Fiction Competition"]


def http_get(url: str, tries: int = 3) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i < tries - 1:
                time.sleep(2 * (i + 1))
                continue
            raise
        except urllib.error.URLError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def write_jsonl(path: Path, docs: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{path.relative_to(ROOT)}: {len(docs)} passages")


# ---------------------------------------------------------------------- ScummVM catalogue
def parse_list_yaml(text: str) -> list[dict]:
    """The generated YAML of scummvm-web: a list of flat mappings ("-" then "    key: value")."""
    items, cur = [], None
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if line.strip() == "-":
            cur = {}
            items.append(cur)
            continue
        m = re.match(r"\s+([\w-]+):\s?(.*)$", line)
        if m and cur is not None:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1].replace("''", "'")
            cur[m.group(1)] = v
    return items


def build_scummvm(commit: str | None) -> list[dict]:
    commit = commit or _ls_remote_head()
    raw = lambda f: http_get(f"https://raw.githubusercontent.com/{SCUMMVM_WEB}/{commit}/data/en/{f}").decode("utf-8")
    games, companies, engines, series = (parse_list_yaml(raw(f + ".yaml")) for f in ("games", "companies", "engines", "series"))
    co = {c["id"]: c["name"] for c in companies}
    en = {e["id"]: e["name"] + (f" ({e['alt_name']})" if e.get("alt_name") else "") for e in engines}
    se = {s["id"]: s["name"] for s in series}
    page = f"https://github.com/{SCUMMVM_WEB}/blob/{commit}/data/en/games.yaml"
    docs, seen = [], set()
    for g in games:
        key = g["name"].lower()
        if "demo" in key or key in seen:  # demos and duplicate entries (platform variants) add nothing
            continue
        seen.add(key)
        parts = [f"{g['name']}" + (f" ({g['year']})" if g.get("year") else "") + "."]
        if g.get("company_id") in co:
            parts.append(f"Company: {co[g['company_id']]}.")
        if g.get("engine_id") in en:
            parts.append(f"Runs in ScummVM with the {en[g['engine_id']]} engine.")
        if g.get("series_id") in se:
            parts.append(f"Series: {se[g['series_id']]}.")
        if g.get("wikipedia_page"):
            parts.append(f"Wikipedia: {g['wikipedia_page'].replace('_', ' ')}.")
        docs.append({"id": "scummvm:" + g["id"], "kind": "catalogue", "lang": "en", "title": g["name"],
                     "year": int(g["year"]) if g.get("year", "").isdigit() else None,
                     "text": " ".join(parts), "company": co.get(g.get("company_id"), ""), "engine": en.get(g.get("engine_id"), ""),
                     "source": page, "license": "facts from the ScummVM website (GPL-3.0 repository)"})
    return docs


def _ls_remote_head() -> str:
    import subprocess
    out = subprocess.run(["git", "ls-remote", f"https://github.com/{SCUMMVM_WEB}", "HEAD"], capture_output=True, text=True, check=True)
    return out.stdout.split()[0]


# ---------------------------------------------------------------------- Wikipedia
def wiki_api(lang: str, params: dict) -> dict:
    base = os.environ.get("PCM_WIKI_API", WIKI_API).format(lang=lang)
    params = {**params, "format": "json", "formatversion": "2"}
    return json.loads(http_get(base + "?" + urllib.parse.urlencode(params)))


def museum_titles() -> list[str]:
    """English Wikipedia titles of the museum's games, studios and engines (from their links)."""
    titles = []
    for f, key in (("timeline.json", "games"), ("studios.json", "studios"), ("engines.json", "engines")):
        data = json.loads((ROOT / "data" / f).read_text("utf-8"))[key]
        for x in data:
            links = [x.get("link", "")] + [l.get("url", "") for l in x.get("links", [])]
            for l in links:
                if "en.wikipedia.org/wiki/" in l:
                    titles.append(urllib.parse.unquote(l.split("/wiki/", 1)[1]).replace("_", " "))
    return titles


def passages(text: str, max_chars: int) -> list[tuple[str, str]]:
    """Split a plain-text extract into (section, passage) chunks of whole paragraphs."""
    out, section, buf = [], "", ""
    skip = re.compile(r"^(see also|references|external links|notes|further reading|véase también|referencias|enlaces externos|"
                      r"siehe auch|einzelnachweise|weblinks|literatur|voir aussi|références|notes et références|liens externes)$", re.I)
    skipping = False
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        m = re.match(r"^=+\s*(.*?)\s*=+$", para)
        if m:
            if buf:
                out.append((section, buf)); buf = ""
            section, skipping = m.group(1), bool(skip.match(m.group(1)))
            continue
        if skipping:
            continue
        if len(buf) + len(para) > max_chars and buf:
            out.append((section, buf)); buf = ""
        buf = (buf + "\n" + para).strip()
    if buf:
        out.append((section, buf))
    return out


def build_wikipedia(langs: list[str], max_chars: int) -> dict[str, list[dict]]:
    en_titles = sorted(set(museum_titles() + TOPICS))
    by_lang: dict[str, list[dict]] = {l: [] for l in langs}
    for i in range(0, len(en_titles), 20):
        batch = en_titles[i:i + 20]
        # resolve redirects and find the same article in the other languages
        d = wiki_api("en", {"action": "query", "titles": "|".join(batch), "redirects": 1, "prop": "langlinks", "lllimit": "max"})
        for page in d["query"]["pages"]:
            if page.get("missing"):
                print(f"  missing on en.wikipedia: {page.get('title')}", file=sys.stderr)
                continue
            titles = {"en": page["title"]}
            for ll in page.get("langlinks", []):
                if ll["lang"] in langs:
                    titles[ll["lang"]] = ll["title"]
            for lang, title in titles.items():
                if lang in langs:
                    by_lang[lang].extend(fetch_article(lang, title, max_chars))
        print(f"  {min(i + 20, len(en_titles))}/{len(en_titles)} topics", file=sys.stderr)
    return by_lang


def fetch_article(lang: str, title: str, max_chars: int) -> list[dict]:
    d = wiki_api(lang, {"action": "query", "titles": title, "redirects": 1, "prop": "extracts|info", "explaintext": 1,
                        "exsectionformat": "wiki", "inprop": "url"})
    page = d["query"]["pages"][0]
    text = page.get("extract") or ""
    url = page.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    docs = []
    for n, (section, body) in enumerate(passages(text, max_chars)):
        docs.append({"id": f"wp-{lang}:{page['title']}#{n}", "kind": "wikipedia", "lang": lang,
                     "title": page["title"] + (f" · {section}" if section else ""), "text": body, "source": url,
                     "license": "CC BY-SA 4.0 · Wikipedia contributors"})
    return docs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", choices=["scummvm", "wikipedia", "all"])
    ap.add_argument("--langs", default="es,en,de,fr")
    ap.add_argument("--max-chars", type=int, default=900)
    ap.add_argument("--scummvm-commit", help="pin a scummvm-web commit (default: current HEAD)")
    a = ap.parse_args()
    if a.source in ("scummvm", "all"):
        write_jsonl(OUT / "scummvm-games.jsonl", build_scummvm(a.scummvm_commit))
    if a.source in ("wikipedia", "all"):
        for lang, docs in build_wikipedia([l.strip() for l in a.langs.split(",") if l.strip()], a.max_chars).items():
            write_jsonl(OUT / f"wikipedia-{lang}.jsonl", docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
