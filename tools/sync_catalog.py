#!/usr/bin/env python3
"""Builds data/catalog.json: the museum's catalogue of classic adventures, with where each one can be played or bought.

    python3 tools/sync_catalog.py                    # all sources, validates up to 20 new editions
    python3 tools/sync_catalog.py --only scummvm --validate 0
    python3 tools/sync_catalog.py --out /catalog/catalog.json --cache /cache/games   # what the Docker builder runs daily

Sources (settings in data/catalog.sources.json):
  · ScummVM: the freeware games and the demos its website distributes with the authors' permission
    (scummvm/scummvm-web, data/en/game_downloads.yaml and game_demos.yaml, pinned to a commit);
  · Internet Archive: advancedsearch.php to discover adventures, metadata/{id} for files, checksums and the program
    to start (emulator_start); download/{id}/{file} to download;
  · GOG.com: its catalogue search, only to link to the shop page of games that are still sold;
  · the museum's own timeline (data/timeline.json): every game in it has a record here.
Per-game corrections and confirmed rights go in data/catalog.overrides.json (they always win).

Each game gets one of three states:
  playable  an edition is authorised to run on the web (rights in game_fetch.RIGHTS_PLAYABLE) and passed the
            automatic checks (download, checksum, zip, engine, program to start) in tools/game_fetch.py;
  pending   found automatically, but its rights or its compatibility are not confirmed yet;
  record    documented only: no edition we may distribute (commercial games, "abandonware" included).
Internet Archive items are never playable on the uploader's word alone: only with an explicit licence in their
metadata (Creative Commons / public domain) or rights confirmed in catalog.overrides.json with an evidence link.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "tools"))
import add_game  # noqa: E402
import game_fetch  # noqa: E402
import identify_game as ig  # noqa: E402

UA = "PointAndClickMuseum-catalog/1.0 (+https://github.com/javipalanca/point-and-click-museum)"
SVM_WEB = "scummvm/scummvm-web"
SVM_DL = os.environ.get("PCM_SCUMMVM_DL", "https://downloads.scummvm.org")
IA = os.environ.get("PCM_IA_BASE", "https://archive.org")
NOT_GAME = re.compile(r"addon|add-on|music|soundtrack|mp3|flac|ogg|manual|disk images|subtitles|translation|installer|"
                      r"cutscene|patch|box|stickers", re.I)
RANK = {"playable": 0, "pending": 1, "record": 2}
# ScummVM also runs action games, RPGs, 3D and light-gun games: only its adventure engines belong to the museum
ADVENTURE_ENGINES = set("""
access adl agi agos ags avalanche bbvs buried chamber chewy cine composer cruise cryo cryomni3d dgds director dm dragons
draci drascula dreamweb gob groovie hdb hopkins hugo hypno illusions immortal kyra lab lastexpress lure m4 macventure made
mads mohawk mortevielle mtropolis myst3 nancy neverhood ngi pegasus petka pink plumbers prince private queen saga sci scumm
sherlock sky sludge stark startrek supernova sword1 sword2 sword25 teenagent tinsel titanic toltecs toon tony touche
trecision tsage tucker twine voyeur wage wintermute zvision cge cge2 parallaction
""".split())


def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def http_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def slug(text: str) -> str:
    text = text.translate(str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae", "Æ": "AE"}))
    return add_game.slugify(re.split(r"[:–]| - ", text)[0].replace("'", ""))


# ---------------------------------------------------------------- ScummVM
def simple_yaml(text: str) -> list[dict]:
    """The generated lists of scummvm-web: '-' then '    key: 'value'' lines."""
    out = []
    for block in re.split(r"^-\s*$", text, flags=re.M)[1:]:
        d = {}
        for k, v in re.findall(r"^\s+([\w']+):\s*(.*)$", block, re.M):
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] == "'":
                v = v[1:-1].replace("''", "'")
            d[k.strip("'")] = v
        out.append(d)
    return out


def scummvm_commit(previous: str | None) -> str:
    for attempt in (lambda: http_json(f"https://api.github.com/repos/{SVM_WEB}/commits/master")["sha"],
                    lambda: subprocess.run(["git", "ls-remote", f"https://github.com/{SVM_WEB}", "HEAD"], capture_output=True,
                                           text=True, check=True, timeout=60).stdout.split()[0]):
        try:
            return attempt()
        except Exception:
            continue
    if previous:
        return previous
    raise RuntimeError("cannot read the scummvm-web commit")


def scummvm_source(cfg: dict, prev: dict) -> tuple[list[dict], dict]:
    commit = cfg.get("commit") or scummvm_commit((prev.get("sources") or {}).get("scummvm", {}).get("commit"))
    raw = f"https://raw.githubusercontent.com/{SVM_WEB}/{commit}/data/en/"
    titles = {}
    for line in (DATA / "murray_kb" / "scummvm-games.jsonl").read_text("utf-8").splitlines():
        g = json.loads(line)
        titles[g["id"].split(":", 1)[1]] = g
    found = []
    # freeware: one main edition per game (the first full one, English if there is a choice), the rest as alternatives
    by_game: dict[str, list[dict]] = {}
    for d in simple_yaml(http_text(raw + "game_downloads.yaml")):
        if d.get("category") == "games" and d.get("url", "").lower().endswith(".zip") and not NOT_GAME.search(d.get("name", "")):
            by_game.setdefault(d["game_id"], []).append(d)
    for gid, eds in by_game.items():
        if gid.split(":")[0] not in ADVENTURE_ENGINES:
            continue
        main = next((e for e in eds if re.search(r"english|\ben\b|cd version", e["name"], re.I)), eds[0])
        info = titles.get(gid, {})
        engine = gid.split(":")[0]
        found.append({
            "title": info.get("title") or gid, "year": info.get("year"), "developer": info.get("company", ""),
            "scummvm": gid, "kind": "full", "rights": "freeware", "rightsSource": f"https://www.scummvm.org/games/#games-{engine}",
            "emulator": "scummvm", "run": {"svmEngine": engine}, "edition": main["name"],
            "download": {"provider": "scummvm", "url": f"{SVM_DL}/frs/extras/{urllib.parse.quote(main['url'])}"},
            "alternatives": [e["name"] for e in eds if e is not main][:6]})
    # demos: interactive DOS demos (shareware/demo discs, distributed by ScummVM with permission)
    demos: dict[str, dict] = {}
    for d in simple_yaml(http_text(raw + "game_demos.yaml")):
        if d.get("platform") not in ("dos", "pc") or re.search(r"non-interactive|unsupported", d.get("category", ""), re.I):
            continue
        if d.get("language") not in ("en", "es", "") or d["id"] in demos or not d.get("url", "").endswith(".zip"):
            continue
        demos[d["id"]] = d
    for gid, d in demos.items():
        info = titles.get(gid)
        if not info or gid.split(":")[0] not in ADVENTURE_ENGINES:  # adventures of ScummVM's catalogue only
            continue
        found.append({
            "title": info["title"], "year": info.get("year"), "developer": info.get("company", ""), "scummvm": gid,
            "kind": "demo", "rights": "demo", "rightsSource": "https://www.scummvm.org/demos/",
            "emulator": "scummvm", "run": {"svmEngine": gid.split(":")[0]}, "edition": "Demo" + (f" ({d['category']})" if d.get("category") else ""),
            "download": {"provider": "scummvm", "url": SVM_DL + urllib.parse.quote(d["url"])}})
    log(f"ScummVM: {sum(e['kind'] == 'full' for e in found)} freeware games, {sum(e['kind'] == 'demo' for e in found)} demos (scummvm-web {commit[:10]})")
    return found, {"commit": commit}


# ---------------------------------------------------------------- Internet Archive
def ia_rights(meta: dict) -> tuple[str, str]:
    """(rights, hint). Only an explicit licence counts; the rest is a hint for a person to confirm."""
    lic = (meta.get("licenseurl") or "").lower()
    if "publicdomain" in lic or "/zero/" in lic:
        return "public-domain", lic
    if "creativecommons.org/licenses" in lic:
        return "open-license", lic
    words = " ".join(str(x) for x in ([meta.get("title", "")] + as_list(meta.get("subject")) + as_list(meta.get("collection")))).lower()
    for hint in ("shareware", "freeware", "demo", "public domain"):
        if re.search(rf"\b{hint}\b", words):
            return "unknown", hint
    return "commercial", ""


def as_list(v) -> list:
    return v if isinstance(v, list) else [v] if v else []


def archive_source(cfg: dict, known: list[dict], prev_ia: dict) -> tuple[list[dict], dict]:
    if not cfg.get("enabled", True):
        return [], {}
    coll = " OR ".join(cfg["collections"])
    subj = " OR ".join(f'"{s}"' for s in cfg["subjects"])
    queries = [f"collection:({coll}) AND subject:({subj})"]
    # and each game of the timeline by title, which finds the ones tagged loosely
    queries += [f'collection:({coll}) AND title:("{g["title"].split(":")[0]}")' for g in known if g.get("timeline")][:cfg.get("titleQueries", 150)]
    docs: dict[str, dict] = {}
    for q in queries:
        url = f"{IA}/advancedsearch.php?" + urllib.parse.urlencode(
            [("q", q), ("rows", cfg.get("rows", 200)), ("output", "json")] + [("fl[]", f) for f in
             ("identifier", "title", "year", "date", "creator", "publisher", "subject", "collection", "licenseurl")])
        try:
            for d in http_json(url)["response"]["docs"]:
                docs.setdefault(d["identifier"], d)
        except Exception as e:
            log(f"  Internet Archive search failed ({type(e).__name__}): {q[:60]}")
            if not docs:
                break  # no network: do not try 150 more times
        time.sleep(cfg.get("pause", 0.5))
    found, seen_meta = [], dict(prev_ia.get("meta", {}))
    for ident, d in docs.items():
        title = str(as_list(d.get("title"))[0] if d.get("title") else ident)
        match = ig.identify([], title, None, title) or {}
        if not match and not cfg.get("keepUnmatched", True):
            continue
        rights, hint = ia_rights(d)
        entry = {"title": match.get("title") or re.sub(r"\s*\([^)]*\)|\s*\[[^\]]*\]", "", title).strip() or ident, "year": match.get("year") or year_of(d),
                 "developer": match.get("studio") or str(as_list(d.get("creator"))[0] if d.get("creator") else ""),
                 "kind": "demo" if hint == "demo" else "full", "rights": rights, "rightsHint": hint,
                 "archive": ident, "emulator": "dosbox", "edition": f"Internet Archive · {ident}"}
        if rights in game_fetch.RIGHTS_PLAYABLE or hint:  # files, checksum and program to start: only when it could be played
            meta = seen_meta.get(ident)
            if not meta:
                try:
                    meta = http_json(f"{IA}/metadata/{urllib.parse.quote(ident)}")
                    meta = {"files": [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(".zip")],
                            "emulator": meta.get("metadata", {}).get("emulator"), "start": meta.get("metadata", {}).get("emulator_start")}
                    seen_meta[ident] = meta
                    time.sleep(cfg.get("pause", 0.5))
                except Exception as e:
                    log(f"  metadata of {ident} not available ({type(e).__name__})")
            if meta and meta["files"]:
                f = max(meta["files"], key=lambda x: int(x.get("size") or 0))
                entry["download"] = {"provider": "archive", "file": f["name"], "size": int(f.get("size") or 0) or None,
                                     "md5": f.get("md5"), "sha1": f.get("sha1"),
                                     "url": f"{IA}/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(f['name'])}"}
                if meta.get("start"):
                    entry["run"] = {"exe": meta["start"]}
        found.append(entry)
    log(f"Internet Archive: {len(found)} items ({sum(1 for e in found if e['rights'] == 'commercial')} commercial: record only)")
    return found, {"meta": seen_meta, "at": int(time.time())}


def year_of(d: dict):
    for k in ("year", "date"):
        m = re.match(r"(19[7-9]\d|20[0-2]\d)", str(d.get(k) or ""))
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------- GOG
def gog_link(title: str, cfg: dict, cached: dict) -> str | None:
    key = ig.norm(title)
    hit = cached.get(key)
    if hit and time.time() - hit.get("at", 0) < cfg.get("days", 7) * 86400:
        return hit.get("url")
    url = cfg["search"].format(query=urllib.parse.quote(title.split(":")[0]))
    try:
        data = http_json(url)
    except Exception as e:
        raise ConnectionError(f"GOG search failed ({type(e).__name__})") from None
    best = None
    for p in data.get("products", []):
        name = p.get("title", "")
        sc = ig.similarity(ig.norm(name), key)
        link = p.get("storeLink") or (f"https://www.gog.com/en/game/{p['slug']}" if p.get("slug") else None)
        if link and sc >= 0.9 and (not best or sc > best[0]):
            best = (sc, link)
    cached[key] = {"url": best[1] if best else None, "at": int(time.time())}
    return cached[key]["url"]


# ---------------------------------------------------------------- merge
def edition_status(ed: dict) -> str:
    if ed["rights"] not in game_fetch.RIGHTS_PLAYABLE:
        return "record" if ed["rights"] == "commercial" else "pending"
    v = ed.get("validated") or {}
    return "playable" if v.get("ok") else "pending"


def merge(found: list[dict], prev: dict, overrides: dict) -> list[dict]:
    kb = ig.knowledge()
    old = {g["id"]: g for g in prev.get("games", [])}
    games: dict[str, dict] = {}
    for t in json.loads((DATA / "timeline.json").read_text("utf-8"))["games"]:  # every timeline game has a record
        games[t["id"]] = {"id": t["id"], "title": t["title"], "year": t["year"], "developer": t["studio"].split(" · ")[0],
                          "timeline": t["id"], "editions": []}
    for e in found:
        tl = ig.timeline_for({"title": e["title"], "year": e.get("year")})
        gid = tl or slug(e["title"])
        g = games.setdefault(gid, {"id": gid, "title": e["title"], "year": e.get("year"), "developer": e.get("developer", ""), "editions": []})
        if tl:
            g["timeline"] = tl
        for k in ("scummvm", "archive"):
            if e.get(k):
                g.setdefault(k, e[k])
        ed = {k: e[k] for k in ("kind", "rights", "rightsHint", "rightsSource", "emulator", "run", "edition", "download",
                                "alternatives", "archive") if e.get(k)}
        src = e.get("archive") or Path(urllib.parse.unquote((e.get("download") or {}).get("url", ""))).stem or e.get("scummvm") or ""
        ed["key"] = add_game.slugify(f"{gid}-{e['kind']}-{src}")[:80].strip("-")
        prev_ed = next((x for x in old.get(gid, {}).get("editions", []) if x.get("key") == ed["key"]), {})
        if prev_ed.get("validated") and prev_ed.get("download", {}).get("url") == ed.get("download", {}).get("url"):
            ed["validated"] = prev_ed["validated"]
        if ed not in g["editions"]:
            g["editions"].append(ed)
    for gid, g in games.items():
        if gid in old:  # keep what does not come from the sources (GOG link, cover)
            for k in ("gog", "cover"):
                if old[gid].get(k) and not g.get(k):
                    g[k] = old[gid][k]
        ov = overrides.get(gid) or {}
        for k, v in ov.items():
            if k == "editions":  # per-edition corrections, by key or by index
                for sel, fix in v.items():
                    eds = [x for x in g["editions"] if x.get("key") == sel] or ([g["editions"][int(sel)]] if sel.isdigit() and int(sel) < len(g["editions"]) else [])
                    for x in eds:
                        x.update(fix)
            elif not k.startswith("_"):
                g[k] = v
        for ed in g["editions"]:
            ed["status"] = edition_status(ed)
        g["editions"].sort(key=lambda x: (RANK[x["status"]], x["kind"] != "full"))
        g["status"] = g["editions"][0]["status"] if g["editions"] else "record"
        if ov.get("status") == "record":
            g["status"] = "record"
        if not g.get("cover") and g.get("timeline"):
            g["cover"] = {"media": f"games/{g['timeline']}/cover"}
    return sorted(games.values(), key=lambda g: (ig.norm(g["title"]), g["id"]))


def validate(games: list[dict], cache: Path, limit: int) -> int:
    """Downloads and checks up to `limit` editions that may be played and have not been checked yet.
    A network failure is not a verdict: the edition is tried again next time (and after three in a row we stop)."""
    done = net_errors = 0
    now = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for g in games:
        for ed in g["editions"]:
            v = ed.get("validated") or {}
            engine = (ed.get("run") or {}).get("svmEngine")
            if v.get("engineMissing") and game_fetch.engine_built(v["engineMissing"]):
                ed.pop("validated")  # the engine has been added to the build since: check it again
                v = {}
            if v or ed["rights"] not in game_fetch.RIGHTS_PLAYABLE or not ed.get("download"):
                continue
            if ed.get("emulator") == "scummvm" and not game_fetch.engine_built(engine or ""):
                ed["validated"] = {"ok": False, "at": now(), "engineMissing": engine,
                                   "error": f"ScummVM engine '{engine}' is not in our build (tools/build_scummvm.sh ENGINES)"}
                ed["status"] = edition_status(ed)
                continue  # no download needed to know it: does not count towards the limit
            if done >= limit or net_errors >= 3:
                continue
            done += 1
            job = {"id": ed["key"], "title": g["title"], **ed}
            try:
                r = game_fetch.prepare(job, cache)
                ed["validated"] = {"ok": True, "at": r["at"], "checks": r["checks"]}
                net_errors = 0
                log(f"  ✓ {g['title']} ({ed['edition']})")
            except game_fetch.GameError as e:  # the file itself is not right: a verdict
                ed["validated"] = {"ok": False, "at": now(), "error": str(e)[:200]}
                log(f"  ✗ {g['title']} ({ed['edition']}): {e}")
            except Exception as e:  # network, disk…: try again next time
                net_errors += 1
                log(f"  … {g['title']} ({ed['edition']}): not reachable now ({type(e).__name__}); next time")
                if net_errors == 3:
                    log("  three downloads in a row failed: the sources look unreachable, stopping the checks for today")
            ed["status"] = edition_status(ed)
        g["editions"].sort(key=lambda x: (RANK[x["status"]], x["kind"] != "full"))
        g["status"] = g["editions"][0]["status"] if g["editions"] else "record"
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("PCM_CATALOG", DATA / "catalog.json")))
    ap.add_argument("--cache", type=Path, default=ROOT / ".cache" / "games-proxy", help="where validated games are kept")
    ap.add_argument("--only", action="append", choices=("scummvm", "archive", "gog"), help="sources to refresh (others are kept)")
    ap.add_argument("--validate", type=int, default=int(os.environ.get("GAMES_VALIDATE_PER_RUN", "20")),
                    help="editions to download and check in this run (default 20; 0 = none)")
    ap.add_argument("--retry-failed", action="store_true", help="check again the editions that failed")
    a = ap.parse_args()
    cfg = json.loads((DATA / "catalog.sources.json").read_text("utf-8"))
    overrides = json.loads((DATA / "catalog.overrides.json").read_text("utf-8")) if (DATA / "catalog.overrides.json").exists() else {}
    prev = json.loads(a.out.read_text("utf-8")) if a.out.exists() else {}
    only = set(a.only or ("scummvm", "archive", "gog"))
    state = dict(prev.get("sources") or {})
    found = []
    prev_found = {k: [] for k in ("scummvm", "archive")}  # sources not refreshed this time: rebuilt from the previous file
    for g in prev.get("games", []):
        for ed in g.get("editions", []):
            src = (ed.get("download") or {}).get("provider") or ("archive" if ed.get("archive") else None)
            if src in prev_found:
                prev_found[src].append({"title": g["title"], "year": g.get("year"), "developer": g.get("developer", ""),
                                        "scummvm": g.get("scummvm"), **{k: v for k, v in ed.items() if k not in ("status", "validated", "key")}})
    if "scummvm" in only:
        try:
            items, state["scummvm"] = scummvm_source(cfg.get("scummvm", {}), prev)
            found += items
        except Exception as e:
            log(f"ScummVM not refreshed ({type(e).__name__}: {e}); keeping the previous list")
            found += prev_found["scummvm"]
    else:
        found += prev_found["scummvm"]
    if "archive" in only:
        items, st = archive_source(cfg["archive"], [{"title": t["title"], "timeline": t["id"]} for t in
                                                    json.loads((DATA / "timeline.json").read_text("utf-8"))["games"]], state.get("archive", {}))
        found += items or prev_found["archive"]
        if items:
            state["archive"] = st
    else:
        found += prev_found["archive"]
    games = merge(found, prev, overrides)
    if "gog" in only and cfg.get("gog", {}).get("enabled", True):
        cached, errors = state.get("gog", {}).get("cache", {}), 0
        for g in games:
            if "gog" in (overrides.get(g["id"]) or {}):
                continue
            try:
                link = gog_link(g["title"], cfg["gog"], cached)
                if link:
                    g["gog"] = link
                elif "gog" in g:
                    del g["gog"]  # no longer sold
            except ConnectionError as e:
                errors += 1
                if errors >= 3:
                    log(f"GOG not reachable ({e}); links kept from the last run")
                    break
            time.sleep(cfg["gog"].get("pause", 0.3))
        state["gog"] = {"cache": cached, "at": int(time.time())}
    if a.retry_failed:
        for g in games:
            for ed in g["editions"]:
                if (ed.get("validated") or {}).get("ok") is False:
                    ed.pop("validated")
    checked = validate(games, a.cache, a.validate) if a.validate else 0
    counts = {s: sum(g["status"] == s for g in games) for s in RANK}
    doc = {"_doc": "Generated by tools/sync_catalog.py (do not edit: corrections go in data/catalog.overrides.json).",
           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "counts": counts, "sources": state, "games": games}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
    os.replace(tmp, a.out)
    log(f"catalogue: {len(games)} games · {counts['playable']} playable · {counts['pending']} pending · {counts['record']} record only"
        f" · {checked} editions checked -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
