"""Museum knowledge base for Murray: the same JSON the website is built from, indexed for retrieval.

Standard library only (so it can be tested without the API): a small BM25 index over one document per game,
studio, engine, technique and era, in every language, plus the lookup helpers exposed to the model as tools.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

LANGS = ("es", "en", "de", "fr")


def loc(v, lang: str, default: str = "es"):
    if isinstance(v, dict) and v and set(v) <= set(LANGS):
        return v.get(lang) or v.get(default) or next(iter(v.values()))
    if isinstance(v, dict):
        return {k: loc(x, lang, default) for k, x in v.items()}
    if isinstance(v, list):
        return [loc(x, lang, default) for x in v]
    return v


STOP = set("""
el la los las un una unos unas de del al y o en que qué con por para es son fue hay como cual cuales quien quienes
sobre mas muy su sus se lo le me mi tu te este esta estos estas ese esa eso juego juegos aventura aventuras grafica graficas
the a an of and or in on at to is are was were what which who whom how about for with from by it its this that these those
me my your you game games adventure adventures there any some do does did tell
der die das ein eine und oder in im von zu mit ist sind war was welche welcher wer wie uber fur es gibt spiel spiele
le la les un une des de du et ou en au aux est sont etait quel quels quelle quelles qui comment sur pour avec il y a jeu jeux
""".split())


def tokens(s: str, stop: bool = False) -> list[str]:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    out = [w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 1 or w.isdigit()]
    return [w for w in out if w not in STOP] if stop else out


# museum records first, then curated history, Wikipedia passages and the (very terse) ScummVM catalogue
KIND_WEIGHT = {"about": 1.3, "history": 1.15, "wikipedia": 0.95, "catalogue": 0.8}


@dataclass
class Doc:
    id: str            # e.g. game:monkey-island
    kind: str          # game | studio | engine | technique | era
    title: str
    text: str          # what the model / offline answer reads
    url: str           # path inside the site, relative to the language root (e.g. "timeline/#loom")
    year: int | None = None
    fields: dict = field(default_factory=dict)


class Museum:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        load = lambda n: json.loads((self.data_dir / n).read_text("utf-8"))
        self.raw = {"timeline": load("timeline.json"), "studios": load("studios.json")["studios"],
                    "engines": load("engines.json")["engines"], "techniques": load("techniques.json")}
        self.about = load("murray.json").get("about", {}) if (self.data_dir / "murray.json").exists() else {}
        self.external = self._external()
        self.docs: dict[str, list[Doc]] = {l: self._docs(l) + [d for d in self.external if d.fields["lang"] in (l, "en")] for l in LANGS}
        self.index = {l: self._bm25(d) for l, d in self.docs.items()}

    # ------------------------------------------------------------------ external knowledge (data/murray_kb)
    def _external(self) -> list[Doc]:
        """Curated web articles (history.json) and generated passages (*.jsonl: ScummVM catalogue, Wikipedia)."""
        kb, out = self.data_dir / "murray_kb", []
        if not kb.is_dir():
            return out
        hist = kb / "history.json"
        if hist.exists():
            for a in json.loads(hist.read_text("utf-8"))["articles"]:
                out.append(Doc(f"history:{a['id']}", "history", a["title"], a["text"], a["sources"][0], None,
                               {"lang": "en", "sources": a["sources"], "keywords": a.get("keywords", ""), "external": True}))
        for f in sorted(kb.glob("*.jsonl")):
            for line in f.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                out.append(Doc(r["id"], r.get("kind", "web"), r["title"], r["text"], r.get("source", ""), r.get("year"),
                               {"lang": r.get("lang", "en"), "sources": [r.get("source", "")], "license": r.get("license", ""), "external": True,
                                "company": r.get("company", ""), "engine": r.get("engine", "")}))
        return out

    # ------------------------------------------------------------------ documents
    def _docs(self, lang: str) -> list[Doc]:
        tl = loc(self.raw["timeline"], lang)
        eras = {e["id"]: e for e in tl["eras"]}
        studio_of = {g: s["name"] for s in self.raw["studios"] for g in s.get("games", [])}
        out = []
        if self.about:
            out.append(Doc("about:museum", "about", "Point and Click Museum", loc(self.about, lang), "", None, {"lang": lang}))
        for g in tl["games"]:
            e = eras[g["era"]]
            out.append(Doc(f"game:{g['id']}", "game", g["title"],
                           f"{g['title']} ({g['year']}). {g['studio']}. Engine: {g['engine']}. Era: {e['name']} ({e['range']}). "
                           f"{g['text']['d']} {g['text']['f']}",
                           f"timeline/#{g['id']}", g["year"],
                           {"studio": g["studio"], "engine": g["engine"], "era": e["name"], "link": g.get("link", ""),
                            "museumStudio": studio_of.get(g["id"], "")}))
        for e in tl["eras"]:
            out.append(Doc(f"era:{e['id']}", "era", e["name"], f"{e['name']} ({e['range']}). {e.get('summary', '')}",
                           f"timeline/#era-{e['id']}"))
        for s in loc(self.raw["studios"], lang):
            qa = " ".join(f"{q} {a}" for q, a in s["dialog"])
            games = [g["title"] for g in tl["games"] if g["id"] in s.get("games", [])]
            out.append(Doc(f"studio:{s['id']}", "studio", s["name"], f"{s['name']} ({s['years']}). {qa} Games: {', '.join(games)}.",
                           "studios/", None, {"link": s.get("link", "")}))
        for en in loc(self.raw["engines"], lang):
            out.append(Doc(f"engine:{en['id']}", "engine", en["name"], f"{en['name']} ({en['year']}, {en['by']}). {en['text']}",
                           "engines/", en["year"]))
        T = loc(self.raw["techniques"], lang)
        for k, d in T.get("demos", {}).items():
            out.append(Doc(f"technique:{k}", "technique", d["title"], f"{d['title']}. {d['body']}", f"techniques/#tech-{k}"))
        for u in T.get("interfaces", []):
            out.append(Doc(f"interface:{u['id']}", "technique", u["label"], f"{u['label']} ({u['game']}, {u['year']}). {u['desc']}",
                           "techniques/#tech-interface", u["year"]))
        for i, idea in enumerate(T.get("ideas", [])):
            out.append(Doc(f"idea:{i}", "technique", idea["title"], f"{idea['title']}. {idea['body']}", "techniques/#tech-ideas"))
        return out

    @staticmethod
    def _bm25(docs: list[Doc]):
        toks = [tokens(d.title + " " + d.title + " " + d.text + " " + d.fields.get("keywords", "")) for d in docs]
        df: dict[str, int] = {}
        for t in toks:
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        n, avg = len(docs), sum(map(len, toks)) / max(1, len(docs))
        idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        tf = [{w: t.count(w) for w in set(t)} for t in toks]
        return {"idf": idf, "tf": tf, "len": [len(t) for t in toks], "avg": avg}

    # ------------------------------------------------------------------ queries
    def search(self, query: str, lang: str = "es", k: int = 5, kind: str | None = None) -> list[Doc]:
        lang = lang if lang in LANGS else "es"
        ix, docs, q = self.index[lang], self.docs[lang], tokens(query, stop=True)
        years = {int(w) for w in q if w.isdigit() and 1970 <= int(w) <= 2100}
        scored = []
        for i, d in enumerate(docs):
            if kind and d.kind != kind:
                continue
            s = 0.0
            for w in q:
                f = ix["tf"][i].get(w)
                if f:
                    s += ix["idf"][w] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * ix["len"][i] / ix["avg"]))
            if d.year in years:
                s += 2.0
            tt = tokens(d.title)
            if s and tt == q:
                s += 10.0          # exact title
            elif s and tt and set(tt) <= set(q):
                s += 3.0           # every word of the title asked for
            if s > 0:
                scored.append((s * KIND_WEIGHT.get(d.kind, 1.0), i))
        scored.sort(reverse=True)
        return [docs[i] for _, i in scored[:k]]

    def get(self, doc_id_or_title: str, lang: str = "es") -> Doc | None:
        lang = lang if lang in LANGS else "es"
        key = doc_id_or_title.strip().lower()
        for d in self.docs[lang]:
            if d.id == key or d.id.split(":", 1)[1] == key or d.title.lower() == key:
                return d
        hits = self.search(doc_id_or_title, lang, 1)
        return hits[0] if hits else None

    def list_games(self, lang: str = "es", year_from: int | None = None, year_to: int | None = None,
                   studio: str | None = None, engine: str | None = None, limit: int = 40) -> list[Doc]:
        """Museum games first, then matching entries of the ScummVM catalogue that the museum doesn't cover."""
        def keep(d: Doc, haystack_studio: str, haystack_engine: str) -> bool:
            if d.year is None and (year_from or year_to):
                return False
            if year_from and d.year < year_from or year_to and d.year > year_to:
                return False
            if studio and studio.lower() not in haystack_studio.lower():
                return False
            return not (engine and engine.lower() not in haystack_engine.lower())
        docs = self.docs[lang if lang in LANGS else "es"]
        museum = [d for d in docs if d.kind == "game" and keep(d, d.fields["studio"] + " " + d.fields["museumStudio"], d.fields["engine"])]
        seen = {tokens(d.title).__str__() for d in museum}
        extra = [d for d in docs if d.kind == "catalogue" and str(tokens(d.title)) not in seen and keep(d, d.fields.get("company", ""), d.fields.get("engine", ""))]
        museum.sort(key=lambda d: (d.year, d.title))
        extra.sort(key=lambda d: (d.year or 0, d.title))
        return (museum + extra)[:limit]

    def stats(self) -> dict:
        games = [d for d in self.docs["es"] if d.kind == "game"]
        return {"games": len(games), "first": min(d.year for d in games), "last": max(d.year for d in games),
                "studios": sum(d.kind == "studio" for d in self.docs["es"]), "engines": sum(d.kind == "engine" for d in self.docs["es"])}


# ---------------------------------------------------------------------- tools exposed to the model
TOOLS = [
    {"name": "search_museum",
     "description": "Full-text search of Murray's knowledge base on the history of graphic adventures: the museum's own "
                    "records (games, studios, engines, techniques, eras), history articles written from web sources, Wikipedia "
                    "passages and the ScummVM catalogue of ~1,200 adventure games (company, year, engine, series). English "
                    "keywords work best. Use it before stating any fact about a game, person, company, date or technique.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["query"],
                      "properties": {"query": {"type": "string", "description": "Keywords, titles, names or years."},
                                     "kind": {"type": "string", "enum": ["game", "studio", "engine", "technique", "era", "history", "wikipedia", "catalogue"],
                                              "description": "Optional: restrict to one kind: museum records (game, studio, engine, technique, era), "
                                                             "history articles from web sources, Wikipedia passages, or the ScummVM catalogue of ~1,200 games."}}}},
    {"name": "get_record",
     "description": "Get one museum record by id (e.g. 'monkey-island', 'game:loom', 'studio:lucasarts') or exact title.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": ["id"],
                      "properties": {"id": {"type": "string"}}}},
    {"name": "list_games",
     "description": "List the museum's games filtered by year range, studio and/or engine, sorted by year. "
                    "Use for questions like 'which SCUMM games…', 'adventures from 1993', 'Sierra games'.",
     "input_schema": {"type": "object", "additionalProperties": False, "required": [],
                      "properties": {"year_from": {"type": "integer"}, "year_to": {"type": "integer"},
                                     "studio": {"type": "string"}, "engine": {"type": "string"}}}},
]


def doc_brief(d: Doc) -> dict:
    out = {"id": d.id, "title": d.title, "text": d.text}
    if d.fields.get("external"):
        out["sources"] = d.fields.get("sources", [])
    else:
        out["museum_page"] = d.url
        if d.fields.get("link"):
            out["source"] = d.fields["link"]
    return out


def run_tool(museum: Museum, name: str, args: dict, lang: str) -> tuple[str, list[Doc]]:
    """Returns (JSON text for the model, records used, for the 'sources' list shown to the visitor)."""
    if name == "search_museum":
        docs = museum.search(str(args.get("query", ""))[:200], lang, 6, args.get("kind"))
        return json.dumps({"results": [doc_brief(d) for d in docs]}, ensure_ascii=False), docs
    if name == "get_record":
        d = museum.get(str(args.get("id", ""))[:120], lang)
        return json.dumps(doc_brief(d) if d else {"error": "not found"}, ensure_ascii=False), [d] if d else []
    if name == "list_games":
        def num(k):
            try:
                return int(args[k]) if args.get(k) is not None else None
            except (TypeError, ValueError):
                return None
        docs = museum.list_games(lang, num("year_from"), num("year_to"), args.get("studio"), args.get("engine"))
        rows = [{"id": d.id, "title": d.title, "year": d.year, "studio": d.fields["studio"], "engine": d.fields["engine"]}
                if d.kind == "game" else {"id": d.id, "title": d.title, "year": d.year, "info": d.text} for d in docs]
        return json.dumps({"count": len(docs), "games": rows}, ensure_ascii=False), docs[:6]
    return json.dumps({"error": f"unknown tool {name}"}), []
