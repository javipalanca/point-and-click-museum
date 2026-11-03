#!/usr/bin/env python3
"""Build the Point and Click Museum static site.

Everything the visitor sees comes from data/*.json:

    data/site.json                languages, base URL, score table
    data/i18n/<lang>.json         interface strings, one file per language
    data/timeline.json            eras and games
    data/studios.json             studios and their dialogue trees
    data/engines.json             engine cartridges
    data/techniques.json          interface evolution, demos, design ideas
    data/hero.json                hotspots of the entrance scene
    data/minigames/*.json         the four minigames (rules, texts, scenes)
    data/arcade.json              DOSBox room: emulator + game bundles
    data/sprites.json             12×12 pixel sprites and palette
    data/pixelfont.json           5-pixel bitmap font

Any text field can be a plain string or an object keyed by language
({"es": "...", "en": "...", "de": "...", "fr": "..."}). The build resolves it
per language (falling back to the default language), prerenders one HTML page
per language for search engines, and inlines the resolved data for the scripts.

Usage:
    python build.py                       # -> dist/
    python build.py --base-url https://example.org
    python build.py --link-style file     # links like fr/index.html (static previews)
    python build.py --check               # validate data only

Standard library only (Python 3.9+).
"""
from __future__ import annotations

import argparse
import html
import os
import json
import re
import shutil
import struct
import sys
import time
import urllib.parse
import zlib
from pathlib import Path

from tools.jsdos import museum_demo_bundle

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SRC = ROOT / "src"


# --------------------------------------------------------------------------- data
def load(rel: str):
    return json.loads((DATA / rel).read_text("utf-8"))


def load_all() -> dict:
    site = load("site.json")
    langs = [l["code"] for l in site["languages"]]
    return {
        "site": site,
        "langs": langs,
        "i18n": {l: load(f"i18n/{l}.json") for l in langs},
        "timeline": load("timeline.json"),
        "studios": load("studios.json")["studios"],
        "engines": load("engines.json")["engines"],
        "techniques": load("techniques.json"),
        "hero": load("hero.json"),
        "games": {
            "textAdventure": load("minigames/text-adventure.json"),
            "room": load("minigames/restoration-room.json"),
            "hunt": load("minigames/pixel-hunt.json"),
            "chronology": load("minigames/chronology.json"),
        },
        "arcade": load_arcade(),
        "media": load_media(),
        "sprites": load("sprites.json"),
        "characters": load("characters.json"),
        "font": load("pixelfont.json"),
    }


MEDIA_DIR = ROOT / "assets" / "media"


def load_media() -> dict:
    """data/media.json -> {group: {id: {role: item}}}, only for images already downloaded by tools/fetch_media.py.

    `refs` reuse another entry's image (e.g. the SCUMM engine shows a screenshot of Monkey Island)."""
    doc = load("media.json")
    idx: dict = {"_pending": [], "_items": doc["items"]}
    for it in doc["items"]:
        if it.get("file") and (MEDIA_DIR / it["file"]).exists():
            idx.setdefault(it["group"], {}).setdefault(it["id"], {})[it["role"]] = it
        else:
            idx["_pending"].append(f"{it['group']}/{it['id']} ({it['role']})")
    for group, refs in doc.get("refs", {}).items():
        for id_, ref in refs.items():
            g, i, role = ref.split("/")
            it = idx.get(g, {}).get(i, {}).get(role)
            if it:
                idx.setdefault(group, {}).setdefault(id_, {}).setdefault(role, dict(it, ref=f"{g}/{i}"))
    return idx


def source_name(url: str) -> str:
    if "libretro-thumbnails" in url:
        return "libretro-thumbnails"
    if "wikimedia.org" in url:
        return "Wikimedia Commons"
    if "wikipedia.org" in url:
        return "Wikipedia"
    m = re.match(r"https://github.com/([^/]+)/([^/]+)", url)
    return f"{m.group(1)}/{m.group(2)} (GitHub)" if m else urllib.parse.urlsplit(url).netloc


def media_view(it: dict, root: str, ui: dict) -> dict:
    """What a page needs to show an image honestly: file, size, alt text and a credit line with its source."""
    page = it.get("page", "")
    label = ""
    if "libretro-thumbnails" in page:  # the file name says which edition the image shows
        label = urllib.parse.unquote(page.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("_ ", ": ")
    if it.get("recreation"):
        label = ui["logoRecreation"]
    if it.get("license"):
        rights = " · ".join(x for x in (it.get("author"), it["license"]) if x)
        if it.get("nonFree"):
            rights += " · " + ui["rightsFairUse"]
    else:
        rights = ui["rights_" + it["rights"]]
    return {"src": f"{root}media/{it['file']}", "w": it["w"], "h": it["h"], "role": it["role"], "label": label,
            "rights": rights, "via": source_name(page), "url": page, "licenseUrl": it.get("licenseUrl", "")}


LOCAL_ARCADE = DATA / "arcade.local.json"   # games added with tools/add_game.py (not versioned)
INCLUDE_LOCAL = True                         # switched off by --no-local


def load_arcade() -> dict:
    """data/arcade.json plus, if present, the local catalogue written by tools/add_game.py."""
    arcade = load("arcade.json")
    if INCLUDE_LOCAL and LOCAL_ARCADE.exists():
        ids = {g["id"] for g in arcade["games"]}
        official = {g["id"]: g for g in arcade["games"]}
        for g in json.loads(LOCAL_ARCADE.read_text("utf-8")).get("games", []):
            if g["id"] in ids and not official.get(g["id"], {}).get("bundle") and (ROOT / "assets" / g["bundle"]).exists():
                # your copy of a game the catalogue lists without a bundle (e.g. official freeware): fill it in
                official[g["id"]].update({k: g[k] for k in ("bundle", "engine", "svmEngine", "exe") if k in g}, local=True)
            elif g["id"] in ids:
                print(f"warning: arcade.local.json: id {g['id']} already exists, skipped", file=sys.stderr)
            elif not (ROOT / "assets" / g["bundle"]).exists():
                print(f"warning: arcade.local.json: {g['id']} has no bundle at assets/{g['bundle']}, skipped", file=sys.stderr)
            else:
                arcade["games"].append(dict(g, local=True))
                ids.add(g["id"])
    return arcade


ARTICLES = re.compile(r"^(the|a|an|el|la|los|las|le|les|l'|der|die|das)\s+", re.I)


def sort_key(title: str) -> str:
    """'The Secret of Monkey Island' -> 'secret of monkey island' (for sorting and the A–Z index)"""
    import unicodedata
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().strip()
    return ARTICLES.sub("", t).lower()


def is_localized(v, langs) -> bool:
    return isinstance(v, dict) and v and set(v) <= set(langs)


def localize(v, lang: str, langs: list[str], default: str):
    """Resolve every {lang: value} object inside v to the value for `lang`."""
    if is_localized(v, langs):
        for code in (lang, default, "en", *langs):
            if code in v:
                return localize(v[code], lang, langs, default)
    if isinstance(v, dict):
        return {k: localize(x, lang, langs, default) for k, x in v.items()}
    if isinstance(v, list):
        return [localize(x, lang, langs, default) for x in v]
    return v


# --------------------------------------------------------------------------- validation
def validate(d: dict) -> list[str]:
    errors, warnings = [], []
    langs, site = d["langs"], d["site"]

    def walk(v, path):
        if is_localized(v, langs):
            missing = [l for l in langs if l not in v]
            if missing:
                warnings.append(f"{path}: missing translation {missing}")
            for k, x in v.items():
                walk(x, f"{path}.{k}")
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")

    for key in ("timeline", "studios", "engines", "techniques", "hero", "games", "arcade"):
        walk(d[key], key)

    base_keys = set(d["i18n"][site["defaultLanguage"]])
    for l, strings in d["i18n"].items():
        for k in base_keys - set(strings):
            warnings.append(f"i18n/{l}.json: missing key {k!r}")

    awards = site["score"]["awards"]
    total = sum(a["points"] * a.get("cap", 1) for a in awards.values())
    if total != site["score"]["total"]:
        errors.append(f"site.json: awards add up to {total}, expected {site['score']['total']}")

    sprites = d["sprites"]["sprites"]
    for name, rows in sprites.items():
        if len(rows) != d["sprites"]["size"] or any(len(r) != d["sprites"]["size"] for r in rows):
            errors.append(f"sprites.json: {name} is not {d['sprites']['size']}×{d['sprites']['size']}")

    eras = {e["id"] for e in d["timeline"]["eras"]}
    seen = set()
    for g in d["timeline"]["games"]:
        for f in ("id", "year", "title", "studio", "engine", "era", "text"):
            if f not in g:
                errors.append(f"timeline: {g.get('id', '?')} has no {f!r}")
        if g["id"] in seen:
            errors.append(f"timeline: duplicate id {g['id']}")
        seen.add(g["id"])
        if g["era"] not in eras:
            errors.append(f"timeline: {g['id']} uses unknown era {g['era']}")

    for sec in ("studios", "engines"):
        ids = [x["id"] for x in d[sec]]
        if len(ids) != len(set(ids)):
            errors.append(f"{sec}: duplicate ids")

    for st in d["studios"]:
        for gid in st.get("games", []):
            if gid not in seen:
                errors.append(f"studios: {st['id']} lists unknown timeline game {gid}")

    known = {"techniques": {x["id"] for x in d["techniques"]["interfaces"]}, "games": seen, "studios": {x["id"] for x in d["studios"]}, "engines": {x["id"] for x in d["engines"]}}
    for it in d["media"]["_items"]:
        if it.get("id") not in known.get(it.get("group"), ()):
            errors.append(f"media.json: unknown {it.get('group')}/{it.get('id')}")
        if it.get("rights") not in ("boxart", "screenshot", "logo"):
            errors.append(f"media.json: {it.get('group')}/{it.get('id')} needs rights boxart|screenshot|logo")
        if it.get("file") and not it.get("page"):
            errors.append(f"media.json: {it['group']}/{it['id']} has no source page")

    # award keys referenced by minigames and rules
    for gname, g in d["games"].items():
        if "award" in g and g["award"] not in awards:
            errors.append(f"minigame {gname}: unknown award {g['award']}")
        for r in g.get("rules", []):
            for eff in r.get("do", []):
                if eff.startswith("award:") and eff[6:] not in awards:
                    errors.append(f"minigame {gname}: rule uses unknown award {eff}")
    for it in d["games"]["room"]["items"].values():
        if it["icon"] not in sprites:
            errors.append(f"restoration-room: unknown icon {it['icon']}")
    rooms = d["games"]["textAdventure"]["rooms"]
    for rid, room in rooms.items():
        for ex in room.get("exits", {}).values():
            to = ex if isinstance(ex, str) else ex["to"]
            if to not in rooms:
                errors.append(f"text-adventure: room {rid} exits to unknown room {to}")

    for g in d["arcade"]["games"]:
        b = g.get("bundle")
        if b and not g.get("local") and not b.startswith("http") and b != "games/museum-demo.jsdos" and not (ROOT / "assets" / b).exists():
            errors.append(f"arcade: {g['id']} bundle not found at assets/{b}")

    ids = [p["id"] for p in site["pages"]]
    for p in site["pages"]:
        if not (SRC / "pages" / f"{p['id']}.html").exists():
            errors.append(f"site.json: page {p['id']} has no src/pages/{p['id']}.html")
        for k in ("title", "meta"):
            if f"page_{p['id']}_{k}" not in d["i18n"][site["defaultLanguage"]]:
                errors.append(f"i18n: missing page_{p['id']}_{k}")
    for n in site["nav"]:
        if n not in ids:
            errors.append(f"site.json: nav entry {n} is not a page")

    for w in warnings:
        print("warning:", w, file=sys.stderr)
    return errors


# --------------------------------------------------------------------------- images (PNG, no dependencies)
def png(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in pixels)
    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def hex_rgba(h: str, a: int = 255) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


class Canvas:
    def __init__(self, w, h, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.px = [[bg] * w for _ in range(h)]

    def rect(self, x, y, w, h, c):
        for j in range(max(0, y), min(self.h, y + h)):
            row = self.px[j]
            for i in range(max(0, x), min(self.w, x + w)):
                row[i] = c

    def sprite(self, rows, palette, x0, y0, s):
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != "." and ch in palette:
                    self.rect(x0 + i * s, y0 + j * s, s, s, hex_rgba(palette[ch]))

    def text(self, font, s, x0, y0, scale, c):
        x = x0
        for ch in s:
            g = font.get(ch, font[" "])
            for j, row in enumerate(g):
                for i, v in enumerate(row):
                    if v == "1":
                        self.rect(x + i * scale, y0 + j * scale, scale, scale, c)
            x += (len(g[0]) + 1) * scale

    def png(self):
        return png(self.w, self.h, self.px)


def text_width(font, s, scale):
    return sum((len(font.get(ch, font[" "])[0]) + 1) * scale for ch in s) - scale


ICON = [  # 16×16 museum façade for favicons
    "................",
    ".......yy.......",
    ".....yyyyyy.....",
    "...yyyyyyyyyy...",
    ".wwwwwwwwwwwwww.",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    "..ww.ww..ww.ww..",
    ".wwwwwwwwwwwwww.",
    "wwwwwwwwwwwwwwww",
    "................",
    "................",
]


def write_images(d: dict, out: Path):
    sp = d["sprites"]
    pal = sp["palette"]
    (out / "img/sprites").mkdir(parents=True, exist_ok=True)
    for name, rows in sp["sprites"].items():
        c = Canvas(12 * 6, 12 * 6)
        c.sprite(rows, pal, 0, 0, 6)
        (out / f"img/sprites/{name}.png").write_bytes(c.png())
    ink = hex_rgba(d["site"]["themeColor"])
    icon_pal = {"y": "#ffb547", "w": "#f3e6c8"}
    for size, name in ((32, "favicon-32.png"), (180, "icon-180.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        s = size // 16
        c = Canvas(size, size, ink)
        off = (size - 16 * s) // 2
        c.sprite(ICON, icon_pal, off, off + s, s)
        (out / "img" / name).write_bytes(c.png())
    # Open Graph image 1200×630
    font = d["font"]["glyphs"]
    c = Canvas(1200, 630, ink)
    bands = [hex_rgba(x) for x in ("#120d24", "#1b1240", "#2a1d5c", "#3d2a70")]
    for y in range(0, 630, 6):
        b = min(3, y * 4 // 630)
        for x in range(0, 1200, 6):
            bb = min(3, b + 1) if (y * 4 % 630) > 400 and ((x + y) // 6) % 2 == 0 else b
            c.rect(x, y, 6, 6, bands[bb])
    for t, y in (("POINT AND CLICK", 150), ("MUSEUM", 280)):
        w = text_width(font, t, 14)
        c.text(font, t, (1200 - w) // 2 + 10, y + 10, 14, hex_rgba("#ef5d8a"))
        c.text(font, t, (1200 - w) // 2, y, 14, hex_rgba("#ffb547"))
    sub = "1976 - 2026"
    c.text(font, sub, (1200 - text_width(font, sub, 6)) // 2, 400, 6, hex_rgba("#4fd6c8"))
    icons = ["terminal", "crown", "cursor", "palm", "cd", "skull", "robot", "magnifier", "star"]
    x0 = (1200 - len(icons) * 96 + 24) // 2
    for i, n in enumerate(icons):
        c.sprite(sp["sprites"][n], pal, x0 + i * 96, 480, 6)
    (out / "img/og-image.png").write_bytes(c.png())


# --------------------------------------------------------------------------- HTML blocks
E = html.escape
SCRIPTS = {"rules": ["rules"], "sections": ["sections"], "interfaces": ["interfaces", "techlab"], "games": ["rules", "scene", "games"], "arcade": ["arcade"]}


class Site:
    """URL helpers for one build."""

    def __init__(self, d, args):
        self.d, self.args = d, args
        self.pages = d["site"]["pages"]
        self.by_id = {p["id"]: p for p in self.pages}
        self.base = args.base_url.rstrip("/")

    @staticmethod
    def depth(page, is_root=False):
        return 0 if is_root else 1 + page["path"].count("/")

    def url(self, lang, page_id, from_depth):
        p = self.by_id[page_id]
        target = f"{lang}/{p['path']}"
        if self.args.link_style == "file":
            target += "index.html"
        return "../" * from_depth + target

    def abs(self, lang, page_id):
        return f"{self.base}/{lang}/{self.by_id[page_id]['path']}"


def page_title(ui, pid):
    return ui[f"page_{pid}_title"]


def render_blocks(S: Site, page, lang, L, ui, depth) -> dict:
    d, site, langs = S.d, S.d["site"], S.d["langs"]
    pid, root = page["id"], "../" * depth
    tl = L["timeline"]
    eras = {e["id"]: e for e in tl["eras"]}
    u = lambda target: S.url(lang, target, depth)
    b = {}
    lang_url = lambda code: S.url(code, pid, depth)
    current = next(l for l in site["languages"] if l["code"] == lang)
    b["langMenu"] = (
        f'<details class="lang-menu"><summary aria-label="{E(ui["language"])}: {E(current["name"])}">'
        f'<img src="{root}img/sprites/globe.png" width="20" height="20" alt=""><span>{E(current["label"])}</span></summary><ul>'
        + "".join(f'<li><a href="{E(lang_url(l["code"]))}" hreflang="{l["code"]}" lang="{l["code"]}"'
                  + (' aria-current="true"' if l["code"] == lang else "") + f'>{E(l["name"])}</a></li>' for l in site["languages"])
        + "</ul></details>")
    b["mapLangs"] = "".join(
        f'<a class="pbtn small" href="{E(lang_url(l["code"]))}" hreflang="{l["code"]}" lang="{l["code"]}"'
        + (' aria-current="true"' if l["code"] == lang else "") + f'>{E(l["name"])}</a>' for l in site["languages"])
    b["footerLangs"] = "".join(
        f'<li><a href="{E(lang_url(l["code"]))}" hreflang="{l["code"]}" lang="{l["code"]}"'
        + (' aria-current="true"' if l["code"] == lang else "") + f'>{E(l["name"])}</a></li>' for l in site["languages"])
    b["alternates"] = "\n".join(
        [f'<link rel="alternate" hreflang="{l}" href="{S.abs(l, pid)}">' for l in langs]
        + [f'<link rel="alternate" hreflang="x-default" href="{S.abs(site["defaultLanguage"], pid)}">'])
    locales = {l["code"]: l["locale"] for l in site["languages"]}
    b["ogAlternates"] = "\n".join(f'<meta property="og:locale:alternate" content="{locales[l]}">' for l in langs if l != lang)
    b["scoreInitial"] = E(ui["scoreShort"].format(score=0, total=site["score"]["total"]))

    active = page.get("parent", pid)
    games = [p for p in S.pages if p.get("parent") == "games"]
    room_label = lambda n: ui["roomFmt"].format(n=S.by_id[n]["room"]) if S.by_id[n].get("room") else ""

    def door(n):
        here = n == active
        link = (f'<a class="door-link" href="{E(u(n))}"' + (' aria-current="page"' if here else "") + ">"
                f'<img src="{root}img/sprites/{S.by_id[n]["icon"]}.png" width="24" height="24" alt="">'
                f'<span class="door-text"><span class="door-room">{E(room_label(n))}</span>'
                f'<span class="door-name">{E(ui["navLabel_" + n])}</span></span></a>')
        if n != "games":
            return f'<li class="door{" here" if here else ""}">{link}</li>'
        sub = "".join(
            f'<li><a href="{E(u(g["id"]))}"' + (' aria-current="page"' if g["id"] == pid else "") + ">"
            f'<img src="{root}img/sprites/{g["icon"]}.png" width="24" height="24" alt="">'
            f'<span><b>{E(page_title(ui, g["id"]))}</b><small>{E(ui["page_" + g["id"] + "_meta"])}</small></span></a></li>'
            for g in games)
        return (f'<li class="door has-sub{" here" if here else ""}">{link}'
                f'<button class="sub-toggle" type="button" aria-expanded="false" aria-controls="sub-{n}" '
                f'aria-label="{E(ui["submenuFor"].format(name=ui["navLabel_" + n]))}"><span aria-hidden="true">▾</span></button>'
                f'<div class="sub" id="sub-{n}"><ul>{sub}</ul></div></li>')
    b["primaryNav"] = "".join(door(n) for n in site["nav"])

    # floor plan of the museum (map panel)
    def tile(n, extra=""):
        here = n == active or (n == "home" and pid == "home")
        title = ui["breadcrumbHome"] if n == "home" else page_title(ui, n)
        caption = ui["mapHomeCaption"] if n == "home" else ui["navS_" + n]
        return (f'<div class="plan-room plan-{n}{" here" if here else ""}" data-page="{n}">'
                f'<a href="{E(u(n))}"' + (' aria-current="page"' if here else "") + ">"
                f'<img src="{root}img/sprites/{S.by_id[n]["icon"]}.png" width="32" height="32" alt="">'
                f'<span class="plan-room-no">{E(room_label(n)) if n != "home" else ""}</span>'
                f'<span class="plan-room-name">{E(title)}</span><span class="plan-caption">{E(caption)}</span>'
                f'<span class="plan-flags"><span class="here-pin">{E(ui["youAreHere"])}</span>'
                f'<span class="visited-mark">{E(ui["visited"])}</span></span></a>{extra}</div>')
    games_list = '<ul class="plan-sub">' + "".join(
        f'<li><a href="{E(u(g["id"]))}"' + (' aria-current="page"' if g["id"] == pid else "") + ">"
        f'<img src="{root}img/sprites/{g["icon"]}.png" width="20" height="20" alt="">{E(page_title(ui, g["id"]))}</a></li>' for g in games) + "</ul>"
    b["mapPlan"] = "".join(tile(n, games_list if n == "games" else "") for n in site["nav"]) + tile("home")
    b["footerRooms"] = "".join(f'<li><a href="{E(u(n))}">{E(page_title(ui, n) if n != "home" else ui["breadcrumbHome"])}</a></li>'
                               for n in ["home"] + site["nav"])
    b["footerGames"] = "".join(f'<li><a href="{E(u(g["id"]))}">{E(page_title(ui, g["id"]))}</a></li>' for g in games)
    b["scoreTitle"] = E(ui["scoreFmt"].format(score=0, total=site["score"]["total"]))

    # "in this room": jump links to the sections of long pages
    sections = []
    if pid == "timeline":
        sections = [(f"era-{e['id']}", e["name"]) for e in tl["eras"]]
    elif pid == "techniques":
        T0 = L["techniques"]
        sections = [("tech-interface", ui["interfaceTitle"])] + [(f"tech-{k}", T0["demos"][k]["title"]) for k in ("cycle", "dither", "parallax", "music", "walkbox", "priority", "palette")] + [("tech-ideas", ui["ideasTitle"])]
    b["subnav"] = (f'<nav class="subnav" aria-label="{E(ui["onThisPage"])}"><div class="subnav-inner"><span class="subnav-label">{E(ui["onThisPage"])}</span><ul>'
                   + "".join(f'<li><a href="#{a}">{E(t)}</a></li>' for a, t in sections) + "</ul></div></nav>") if sections else ""

    # header of every room page: breadcrumb + room number + h1
    crumbs = [("home", ui["breadcrumbHome"])]
    if page.get("parent"):
        crumbs.append((page["parent"], page_title(ui, page["parent"])))
    room = page.get("room") or S.by_id.get(page.get("parent"), {}).get("room")
    b["pageHeader"] = (
        f'<nav class="crumbs" aria-label="{E(ui["youAreHere"])}"><ol>'
        + "".join(f'<li><a href="{E(u(c))}">{E(n)}</a></li>' for c, n in crumbs)
        + f'<li aria-current="page">{E(page_title(ui, pid))}</li></ol></nav>'
        + f'<div class="page-head"><img src="{root}img/sprites/{page["icon"]}.png" width="48" height="48" alt="">'
        + (f'<span class="room">{E(ui["roomFmt"].format(n=room))}</span>' if room else "")
        + f'<h1 id="page-title">{E(page_title(ui, pid))}</h1></div>')

    # previous / next room
    if pid != "home":
        seq = [p["id"] for p in S.pages if p.get("parent") == page["parent"]] if page.get("parent") else ["home"] + site["nav"]
        i = seq.index(pid)
        prev_, next_ = (seq[i - 1] if i > 0 else None), (seq[i + 1] if i + 1 < len(seq) else None)
        name = lambda x: ui["breadcrumbHome"] if x == "home" else page_title(ui, x)
        parts = []
        if prev_:
            parts.append(f'<a class="rn prev" href="{E(u(prev_))}" rel="prev"><small>◀ {E(ui["prevRoom"])}</small>{E(name(prev_))}</a>')
        else:
            parts.append(f'<a class="rn prev" href="{E(u(page["parent"]))}"><small>◀ {E(ui["breadcrumbHome"] if not page.get("parent") else page_title(ui, page["parent"]))}</small>{E(page_title(ui, page["parent"]))}</a>' if page.get("parent") else "<span></span>")
        if next_:
            parts.append(f'<a class="rn next" href="{E(u(next_))}" rel="next"><small>{E(ui["nextRoom"])} ▶</small>{E(name(next_))}</a>')
        elif page.get("parent"):
            parts.append(f'<a class="rn next" href="{E(u(page["parent"]))}"><small>{E(ui["nextRoom"])} ▶</small>{E(page_title(ui, page["parent"]))}</a>')
        b["roomNav"] = f'<nav class="wrap room-nav" aria-label="{E(ui["roomsNav"])}">' + "".join(parts) + "</nav>"
    else:
        b["roomNav"] = ""

    def card(target, label, desc, icon, cta, number=None):
        return (f'<a class="px room-card" href="{E(u(target))}"><img src="{root}img/sprites/{icon}.png" width="48" height="48" alt="">'
                + (f'<span class="room">{E(ui["roomFmt"].format(n=number))}</span>' if number else "")
                + f'<h3>{E(label)}</h3><p>{E(desc)}</p><span class="go">{E(cta)} ▶</span></a>')
    b["roomCards"] = "".join(card(n, page_title(ui, n), ui[f"page_{n}_meta"], S.by_id[n]["icon"], ui["enterRoom"], S.by_id[n].get("room")) for n in site["nav"])
    b["gameCards"] = "".join(card(p["id"], page_title(ui, p["id"]), ui[f"page_{p['id']}_meta"], p["icon"], ui["playGame"])
                             for p in S.pages if p.get("parent") == "games")
    b["firstRoomUrl"] = E(u(site["nav"][0]))
    b["arcadeUrl"] = E(u("arcade"))

    # timeline
    b["eras"] = "".join(
        f'<button class="pbtn small" type="button" data-era="{e["id"]}" aria-pressed="false" style="color:{e["color"]}">'
        f'{E(e["name"])} <span class="era-range">{E(e["range"])}</span></button>' for e in tl["eras"])
    # the timeline: one axis, era "station signs" and a stop per game (cover thumbnail only if a real one exists)
    media = S.d["media"]
    groups, side, decade = [], 0, None
    for e in tl["eras"]:
        items = []
        for i, g in enumerate(tl["games"]):
            if g["era"] != e["id"]:
                continue
            dec = g["year"] // 10 * 10
            if dec != decade:
                decade = dec
                items.append(f'<li class="tl-decade" aria-hidden="true"><span>{E(ui["decadeFmt"].format(n=dec))}</span></li>')
            cover = media.get("games", {}).get(g["id"], {}).get("cover")
            img = (f'<img class="tl-cover" src="{root}media/{cover["file"]}" width="{cover["w"]}" height="{cover["h"]}" '
                   f'alt="{E(ui["coverOf"].format(title=g["title"]))}" loading="lazy" decoding="async">') if cover else ""
            people = g["studio"].split(" · ")
            items.append(
                f'<li class="tl-item {"r" if side % 2 else "l"}{" has-cover" if cover else ""}" id="{g["id"]}" data-i="{i}">'
                f'<span class="tl-node" aria-hidden="true"></span>'
                f'<time class="tl-year" datetime="{g["year"]}">{g["year"]}</time>'
                f'<button class="tl-entry" type="button" data-i="{i}" aria-haspopup="dialog">{img}'
                f'<span class="tl-text"><span class="tl-title">{E(g["title"])}</span>'
                f'<span class="tl-meta">{E(people[0])} · {E(g["engine"])}</span></span></button>'
                f'<div class="vh"><p>{E(ui["studio"])}: {E(g["studio"])}. {E(ui["engine"])}: {E(g["engine"])}.</p>'
                f'<p>{E(g["text"]["d"])}</p><p>{E(g["text"]["f"])}</p>'
                + (f'<a href="{E(g["link"])}">{E(ui["moreAbout"])}</a>' if g.get("link") else "") + "</div></li>")
            side += 1
        n = sum(1 for g in tl["games"] if g["era"] == e["id"])
        groups.append(
            f'<section class="tl-era" data-era="{e["id"]}" aria-labelledby="era-{e["id"]}" style="--ec:{e["color"]}">'
            f'<header class="tl-sign"><span class="tl-range">{E(e["range"])}</span>'
            f'<h2 id="era-{e["id"]}">{E(e["name"])}</h2>'
            + (f'<p>{E(e["summary"])}</p>' if e.get("summary") else "")
            + f'<span class="tl-n">{E(ui["gamesCount"].format(n=n))}</span></header>'
            f'<ol class="tl-list">{"".join(items)}</ol></section>')
    b["eraGroups"] = '<div class="tl" id="eraGroups">' + "".join(groups) + "</div>"

    def logo_or_monogram(group, x):
        it = media.get(group, {}).get(x["id"], {}).get("logo")
        if it:
            return (f'<img class="logo{" plate-dark" if it.get("plate") == "dark" else ""}" src="{root}media/{it["file"]}" width="{it["w"]}" height="{it["h"]}" '
                    f'alt="{E(ui["logoOf"].format(name=x["name"]))}" loading="lazy">')
        words = [w for w in re.sub(r"[^\w ]", " ", x["name"]).split()
                 if w.lower() not in ("the", "of", "and", "de", "games", "studio", "studios", "software", "entertainment", "design")]
        mono = (words[0][0] + words[1][0]) if len(words) > 1 else (words[0] if words else x["name"])[:2]
        return f'<span class="monogram" aria-hidden="true">{E(mono.upper())}</span>'

    titles = {g["id"]: g for g in tl["games"]}
    tl_url = u("timeline")

    def studio_covers(st):
        out = []
        for gid in st.get("games", []):
            g, cover = titles[gid], media.get("games", {}).get(gid, {}).get("cover")
            inner = (f'<img src="{root}media/{cover["file"]}" width="{cover["w"]}" height="{cover["h"]}" alt="" loading="lazy">'
                     if cover else f'<span class="nc">{E(g["title"])}</span>')
            out.append(f'<li><a href="{E(tl_url)}#{gid}" title="{E(g["title"])} ({g["year"]})">{inner}'
                       f'<span class="vh">{E(g["title"])} ({g["year"]})</span></a></li>')
        return (f'<div class="st-games"><span class="st-games-h">{E(ui["studioGames"])}</span><ul>' + "".join(out) + "</ul></div>") if out else ""

    b["studios"] = "".join(
        f'<article class="px studio" data-i="{i}"><div class="top">{logo_or_monogram("studios", s)}'
        f'<div><h3>{E(s["name"])}</h3><div class="yrs">{E(s["years"])}</div></div></div>'
        + studio_covers(s)
        + f'<div class="row studio-actions"><button class="pbtn small talk" type="button">{E(ui["talk"])}</button>'
        + (f'<a class="ext" href="{E(s["link"])}" target="_blank" rel="noopener">{E(ui["moreAbout"])} ↗</a>' if s.get("link") else "")
        + '</div><span class="talked"></span>'
        f'<dl class="vh">' + "".join(f"<dt>{E(q)}</dt><dd>{E(a)}</dd>" for q, a in s["dialog"]) + "</dl></article>"
        for i, s in enumerate(L["studios"]))

    b["carts"] = "".join(
        f'<button class="cart" type="button" data-i="{i}" aria-pressed="false" style="--cc:{en["color"]}">'
        f'<span class="lbl">' + (logo_or_monogram("engines", en) if media.get("engines", {}).get(en["id"], {}).get("logo") else "")
        + f'{E(en["name"])}<span class="yr2">{en["year"]}</span></span></button>'
        for i, en in enumerate(L["engines"]))
    b["enginesList"] = '<dl class="eng-list">' + "".join(
        f'<dt>{E(en["name"])} <small>{en["year"]} · {E(en["by"])}</small></dt><dd><p>{E(en["text"])}</p><p>'
        + " ".join(f'<a class="ext" href="{E(l["url"])}" target="_blank" rel="noopener">{E(l["label"])} ↗</a>' for l in en.get("links", []))
        + "</p></dd>" for en in L["engines"]) + "</dl>"

    # image credits: every real image on the page, with the exact file it comes from
    def credit_li(name, it):
        m = media_view(it, root, ui)
        rights = (f'<a href="{E(m["licenseUrl"])}" target="_blank" rel="noopener">{E(m["rights"])}</a>' if m["licenseUrl"] else E(m["rights"]))
        return (f'<li><b>{E(name)}</b> · {E(ui["role_" + it["role"]])}: ' + (f'<cite>{E(m["label"])}</cite> · ' if m["label"] else "")
                + f'{rights} · {E(ui["via"])} <a href="{E(m["url"])}" target="_blank" rel="noopener">{E(m["via"])} ↗</a></li>')
    groups_for = {"timeline": [("games", tl["games"], "title")], "studios": [("studios", L["studios"], "name"), ("games", tl["games"], "title")],
                  "engines": [("engines", L["engines"], "name")]}.get(pid, [])
    lis = []
    for group, things, key in groups_for:
        for x in things:
            if group == "games" and pid == "studios" and not any(x["id"] in st.get("games", []) for st in L["studios"]):
                continue
            for role in ("logo", "cover", "screenshot"):
                it = media.get(group, {}).get(x["id"], {}).get(role)
                if it and not (pid == "studios" and role == "screenshot"):
                    lis.append(credit_li(x[key], it))
    b["mediaCredits"] = (f'<details class="px list-details credits"><summary>{E(ui["mediaCreditsTitle"])}</summary>'
                         f'<p>{E(ui["mediaCreditsLead"])}</p><ul>{"".join(lis)}</ul></details>') if lis else ""

    T = L["techniques"]
    b["uiTabs"] = "".join(
        f'<button class="pbtn small" type="button" role="tab" data-i="{i}" aria-selected="{"true" if i == 0 else "false"}">{E(x["label"])}</button>'
        for i, x in enumerate(T["interfaces"]))
    for k in ("walkbox", "priority"):
        b[k + "Toggle"] = E(T["demos"][k]["toggle"])
    for k in ("cycle", "dither", "parallax", "music", "walkbox", "priority", "palette"):
        b[k + "Title"] = E(T["demos"][k]["title"])
        b[k + "Body"] = E(T["demos"][k]["body"])
    b["ideas"] = "".join(f'<li><b>{E(x["title"])}.</b> {E(x["body"])}</li>' for x in T["ideas"])

    G = L["games"]
    for key, g in (("ta", G["textAdventure"]), ("room", G["room"]), ("hunt", G["hunt"]), ("order", G["chronology"])):
        b[key + "Title"] = E(g["title"])
        b[key + "How"] = E(g["how"])
    b["taPlaceholder"] = E(G["textAdventure"]["placeholder"])

    A = L["arcade"]
    b["arcadeIntro"] = E(A["intro"])
    games = sorted(A["games"], key=lambda g: (0 if g.get("pinned") else 1, sort_key(g["title"])))
    items = []
    for g in games:
        key = sort_key(g["title"])
        letter = key[:1].upper() if key[:1].isalpha() else "#"
        action = (f'<button class="pbtn small dos-play" type="button" data-id="{E(g["id"])}">{E(ui["arcadePlay"])}</button>' if g.get("bundle")
                  else f'<span class="chip warn">{E(ui["arcadeNeedsBundle"])}</span>')
        if g.get("source"):
            action += f' <a class="ext" href="{E(g["source"])}" rel="noopener" target="_blank">{E(ui["arcadeSource"])} ↗</a>'
        meta = " · ".join(x for x in (str(g["year"]) if g.get("year") else "", E(g.get("studio") or "")) if x)
        engine = g.get("engine", "dosbox")
        chips = f'<span class="chip engine">{"ScummVM" if engine == "scummvm" else "DOSBox"}</span> ' + (f'<span class="chip">{E(g["license"])}</span>' if g.get("license") else "") + (f' <span class="chip local">{E(ui["catLocal"])}</span>' if g.get("local") else "")
        items.append(
            f'<article class="px dos-game" data-id="{E(g["id"])}" data-engine="{engine}" data-key="{E(key)}" data-letter="{letter}" '
            f'data-studio="{E(g.get("studio") or "")}" data-year="{g.get("year") or 9999}">'
            f'<img src="{root}img/sprites/{g["icon"]}.png" width="40" height="40" alt="" loading="lazy">'
            f'<h3>{E(g["title"])}</h3><div class="meta">{meta} {chips}</div>'
            f'<p>{E(g["desc"])}</p><div class="row">{action}</div></article>')
    b["arcadeGames"] = "".join(items)
    b["arcadeCount"] = E(ui["catCount"].format(n=len(games), total=len(games)))
    tools = ""
    if len(games) >= A.get("catalogue", {}).get("filtersFrom", 8):
        studios = sorted({g.get("studio") for g in games if g.get("studio") and g.get("studio") != "—"}, key=str.lower)
        letters = {(k[:1].upper() if k[:1].isalpha() else "#") for k in (sort_key(g["title"]) for g in games)}
        tools = (
            '<div class="cat-tools">'
            f'<label class="vh" for="catSearch">{E(ui["catSearch"])}</label>'
            f'<input type="search" id="catSearch" placeholder="{E(ui["catSearch"])}" autocomplete="off">'
            '<div class="row">'
            f'<label class="vh" for="catStudio">{E(ui["catAllStudios"])}</label><select id="catStudio"><option value="">{E(ui["catAllStudios"])}</option>'
            + "".join(f'<option value="{E(st)}">{E(st)}</option>' for st in studios) + "</select>"
            + (f'<label class="vh" for="catEngine">{E(ui["catAllEngines"])}</label><select id="catEngine"><option value="">{E(ui["catAllEngines"])}</option>'
               '<option value="dosbox">DOSBox</option><option value="scummvm">ScummVM</option></select>'
               if len({g.get("engine", "dosbox") for g in games}) > 1 else "")
            + f'<label class="vh" for="catSort">{E(ui["catSortTitle"])}</label><select id="catSort">'
            f'<option value="title">{E(ui["catSortTitle"])}</option><option value="year">{E(ui["catSortYear"])}</option></select></div>'
            f'<nav class="letters" aria-label="{E(ui["catLetters"])}"><button type="button" data-l="" aria-pressed="true">{E(ui["catAllLetters"])}</button>'
            + "".join(f'<button type="button" data-l="{c}" aria-pressed="false"{"" if c in letters else " disabled"}>{c}</button>'
                      for c in ["#"] + [chr(x) for x in range(65, 91)])
            + "</nav></div>")
    b["arcadeTools"] = tools
    b["catClass"] = "cat-list compact" if tools else "cat-list"

    # structured data
    page_url = S.abs(lang, pid)
    crumb_items = [{"@type": "ListItem", "position": i + 1, "name": (ui["breadcrumbHome"] if c == "home" else page_title(ui, c)),
                    "item": S.abs(lang, c)} for i, c in enumerate([c for c, _ in crumbs] + ([pid] if pid != "home" else []))]
    graph = [
        {"@type": "WebSite", "@id": f"{S.base}/#website", "name": site["name"], "url": f"{S.base}/", "inLanguage": langs},
        {"@type": "CollectionPage" if pid == "timeline" else "WebPage", "@id": page_url, "url": page_url,
         "name": page_title(ui, pid), "description": ui[f"page_{pid}_meta"], "inLanguage": lang,
         "isPartOf": {"@id": f"{S.base}/#website"}, "image": f"{S.base}/img/og-image.png"},
    ]
    if pid != "home":
        graph.append({"@type": "BreadcrumbList", "itemListElement": crumb_items})
    if pid == "timeline":
        graph[1]["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(tl["games"]), "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": f"{page_url}#{g['id']}",
             "item": dict({"@type": "VideoGame", "name": g["title"], "datePublished": str(g["year"]), "genre": "Adventure",
                           "description": g["text"]["d"], "author": {"@type": "Organization", "name": g["studio"].split(" · ")[0]}},
                          **({"sameAs": g["link"]} if g.get("link") else {}),
                          **({"image": f"{S.base}/media/{cv['file']}"} if (cv := S.d["media"].get("games", {}).get(g["id"], {}).get("cover")) else {}))}
            for i, g in enumerate(tl["games"])]}
    if pid == "engines":
        graph[1]["mainEntity"] = {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": {"@type": "SoftwareApplication", "name": en["name"],
             "applicationCategory": "Game engine", "datePublished": str(en["year"]),
             **({"sameAs": [l["url"] for l in en["links"]]} if en.get("links") else {})}}
            for i, en in enumerate(L["engines"])]}
    b["jsonld"] = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    return b


def pick(obj, path):
    for k in path.split("."):
        obj = obj[k]
    return obj


def render_page(S: Site, page, lang, is_root, layout, build_id, vendored, svm=None) -> str:
    d, site, langs, default = S.d, S.d["site"], S.d["langs"], S.d["site"]["defaultLanguage"]
    L = {k: localize(d[k], lang, langs, default) for k in ("timeline", "studios", "engines", "techniques", "hero", "games", "arcade")}
    L["timeline"]["games"].sort(key=lambda g: g["year"])
    ui = dict(d["i18n"][default], **d["i18n"][lang])
    pid = page["id"]
    depth = Site.depth(page, is_root)
    root = "../" * depth
    for group, items in (("games", L["timeline"]["games"]), ("studios", L["studios"]), ("engines", L["engines"])):
        for x in items:  # real images (covers, screenshots, logos) with their credits
            x["media"] = {r: media_view(it, root, ui) for r, it in d["media"].get(group, {}).get(x["id"], {}).items()}
    pal = L["techniques"]["demos"]["palette"]
    if isinstance(pal.get("media"), str):
        g, i, r = pal["media"].split("/")
        it = d["media"].get(g, {}).get(i, {}).get(r)
        pal["media"] = media_view(it, root, ui) if it else None
    for x in L["techniques"]["interfaces"]:  # each interface shows a real screenshot of the game it reproduces
        g, i, r = x["media"].split("/")
        it = d["media"].get(g, {}).get(i, {}).get(r)
        x["media"] = media_view(it, root, ui) if it else None
    blocks = render_blocks(S, page, lang, L, ui, depth)
    data = {
        "lang": lang, "root": root, "isRoot": is_root, "page": pid, "ui": ui,
        "nav": site["nav"], "gamePages": [p["id"] for p in S.pages if p.get("parent") == "games"],
        "site": {"score": site["score"]}, "transitions": site.get("transitions", {}), "sprites": d["sprites"], "font": d["font"], "characters": d["characters"],
        "arcadeVendored": vendored,
        "svm": dict(svm or {"available": False}, base=f"{'../' * Site.depth(page, is_root)}scummvm/"),
        "pageUrls": {p["id"]: S.url(lang, p["id"], depth) for p in S.pages},
        "langHints": {l: {"text": d["i18n"][l]["langHintText"], "label": d["i18n"][l]["langHintLink"],
                          "url": S.url(l, pid, depth)} for l in langs},
    }
    for path in page.get("data", []):
        node, keys = data, path.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = pick(L, path)
    blocks["data"] = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    names = []
    for s in page.get("scripts", []):
        names += [n for n in SCRIPTS[s] if n not in names]
    order = ["rules", "scene", "sections", "interfaces", "techlab", "games", "arcade"]
    scripts = []
    if "arcade" in names and S.args.inline_bundles:
        scripts.append(f'<script src="{root}games/bundles.js?v={build_id}" defer></script>')
    scripts += [f'<script src="{root}js/{n}.js?v={build_id}" defer></script>' for n in sorted(names, key=order.index)]
    blocks["scripts"] = "\n".join(scripts)

    def sub(m, vars_):
        kind, key = m.group(1), m.group(2)
        if kind == "t":
            if key not in ui:
                raise KeyError(f"i18n key {key!r} missing")
            return E(ui[key])
        if kind == "v":
            return E(str(vars_[key]))
        return blocks[key]

    vars_ = {
        "lang": lang, "root": root, "siteName": site["name"], "themeColor": site["themeColor"], "fonts": site["fonts"],
        "canonical": S.abs(lang, pid), "ogImage": f"{S.base}/img/og-image.png", "locale": {l["code"]: l["locale"] for l in site["languages"]}[lang],
        "homeUrl": S.url(lang, "home", depth), "build": build_id, "pageId": pid,
        "title": ui["metaTitle"] if pid == "home" else f'{page_title(ui, pid)} · {site["name"]}',
        "description": ui[f"page_{pid}_meta"],
    }
    pat = re.compile(r"\{\{(t|v|raw):([\w-]+)\}\}")
    content = pat.sub(lambda m: sub(m, vars_), (SRC / "pages" / f"{pid}.html").read_text("utf-8"))
    blocks["content"] = content
    return pat.sub(lambda m: sub(m, vars_), layout)


# --------------------------------------------------------------------------- ScummVM
SVM_VENDOR = Path(os.environ.get("PCM_SCUMMVM_VENDOR", ROOT / "vendor" / "scummvm"))  # override used by the tests


def write_pack(path: Path, logical: str, data: bytes):
    """<path>.pack.js: a script that hands the file to the player (for hosts that refuse binary files)."""
    import base64
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(str(path) + ".pack.js").write_text(
        f"PCM_SVM_FILE({json.dumps(logical)},{json.dumps(base64.b64encode(data).decode())});\n", "utf-8")


def write_scummvm(d: dict, out: Path, inline: bool) -> dict:
    """Copy the ScummVM web build and unpack the ScummVM games into out/scummvm/.

    Returns what the pages need to know: whether ScummVM is available and its data files."""
    import zipfile
    dest = out / "scummvm"
    dest.mkdir(parents=True, exist_ok=True)
    for f in (SRC / "scummvm").iterdir():
        shutil.copy(f, dest / f.name)
    available = (SVM_VENDOR / "scummvm.js").exists() and (SVM_VENDOR / "scummvm.wasm").exists()
    data_files = []
    if available:
        shutil.copy(SVM_VENDOR / "scummvm.js", dest / "scummvm.js")
        shutil.copy(SVM_VENDOR / "scummvm.wasm", dest / "scummvm.wasm")
        for f in sorted((SVM_VENDOR / "data").rglob("*")):
            if not f.is_file() or f.name == "index.json":
                continue
            rel = f.relative_to(SVM_VENDOR / "data").as_posix()
            data_files.append(rel)
            target = dest / "data" / rel
            if inline:
                write_pack(target, "data/" + rel, f.read_bytes())
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, target)
    for g in d["arcade"]["games"]:
        if g.get("engine") != "scummvm" or not g.get("bundle"):
            continue
        src = ROOT / "assets" / g["bundle"]
        files = []
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                files.append(info.filename)
                target = dest / "games" / g["id"] / info.filename
                if inline:
                    write_pack(target, f"games/{g['id']}/{info.filename}", z.read(info))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(info))
        g["files"] = sorted(files)
    version = (SVM_VENDOR / "VERSION").read_text().strip() if (SVM_VENDOR / "VERSION").exists() else ""
    return {"available": available, "data": data_files, "inline": inline, "version": version}


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--base-url", help="public URL of the site (default: site.json baseUrl)")
    ap.add_argument("--link-style", choices=("dir", "file"), default="dir",
                    help="'dir' links to es/timeline/, 'file' links to es/timeline/index.html")
    ap.add_argument("--inline-bundles", action="store_true",
                    help="also pack local .jsdos bundles into games/bundles.js (for hosts that refuse .zip files)")
    ap.add_argument("--no-local", action="store_true",
                    help="leave out the games in data/arcade.local.json (use it for public builds)")
    ap.add_argument("--check", action="store_true", help="only validate the data")
    args = ap.parse_args()

    global INCLUDE_LOCAL
    INCLUDE_LOCAL = not args.no_local
    d = load_all()
    args.base_url = args.base_url or d["site"]["baseUrl"]
    errors = validate(d)
    if errors:
        for e in errors:
            print("error:", e, file=sys.stderr)
        return 1
    if args.check:
        print("data OK")
        return 0

    out = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(SRC / "css", out / "css")
    shutil.copytree(SRC / "js", out / "js")
    vendored = (ROOT / "vendor/js-dos/js-dos.js").exists()
    if vendored:
        shutil.copytree(ROOT / "vendor/js-dos", out / "vendor/js-dos")
    if (ROOT / "assets").exists():
        keep = {g["bundle"] for g in d["arcade"]["games"] if g.get("bundle")}
        def skip(folder, names):  # never copy bundles that are not in the catalogue (e.g. local games with --no-local)
            rel = Path(folder).relative_to(ROOT / "assets").as_posix()
            if rel == ".":
                return [n for n in names if n == "scummvm"]  # ScummVM zips are unpacked by write_scummvm()
            return [n for n in names if n.endswith(".jsdos") and f"{rel}/{n}".lstrip("./") not in keep]
        shutil.copytree(ROOT / "assets", out, dirs_exist_ok=True, ignore=skip)
    (out / "games").mkdir(exist_ok=True)
    (out / "games/museum-demo.jsdos").write_bytes(museum_demo_bundle())
    write_images(d, out)
    svm = write_scummvm(d, out, args.inline_bundles)
    if args.inline_bundles:
        import base64
        packed = {g["bundle"]: base64.b64encode((out / g["bundle"]).read_bytes()).decode()
                  for g in d["arcade"]["games"]
                  if g.get("bundle") and g.get("engine", "dosbox") == "dosbox" and not g["bundle"].startswith("http")}
        (out / "games/bundles.js").write_text("window.PCM_BUNDLES = " + json.dumps(packed) + ";\n", "utf-8")

    S = Site(d, args)
    layout = (SRC / "layout.html").read_text("utf-8")
    build_id = time.strftime("%Y%m%d%H%M")
    default = d["site"]["defaultLanguage"]
    count = 0
    for lang in d["langs"]:
        for page in S.pages:
            target = out / lang / page["path"] / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_page(S, page, lang, False, layout, build_id, vendored, svm), "utf-8")
            count += 1
    (out / "index.html").write_text(render_page(S, S.by_id["home"], default, True, layout, build_id, vendored, svm), "utf-8")

    today = time.strftime("%Y-%m-%d")
    urls = []
    for page in S.pages:
        alts = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{S.abs(l, page["id"])}"/>' for l in d["langs"])
        alts += f'<xhtml:link rel="alternate" hreflang="x-default" href="{S.abs(default, page["id"])}"/>'
        urls += [f"<url><loc>{S.abs(l, page['id'])}</loc><lastmod>{today}</lastmod>{alts}</url>" for l in d["langs"]]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{"".join(urls)}</urlset>\n', "utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {S.base}/sitemap.xml\n", "utf-8")
    ui = d["i18n"][default]
    (out / "manifest.webmanifest").write_text(json.dumps({
        "name": d["site"]["name"], "short_name": "P&C Museum", "description": ui["metaDescription"],
        "start_url": f"./{default}/", "display": "standalone", "background_color": d["site"]["themeColor"],
        "theme_color": d["site"]["themeColor"], "lang": default,
        "icons": [{"src": "img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "img/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    }, ensure_ascii=False, indent=2), "utf-8")
    (out / ".nojekyll").write_text("")
    n = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"built {count} pages ({len(d['langs'])} languages × {len(S.pages)}), {n} files -> {out}"
          + ("" if vendored else "  (js-dos from CDN: run tools/fetch_jsdos.py to self-host)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
