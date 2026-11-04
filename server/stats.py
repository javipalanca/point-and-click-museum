"""Usage statistics of the museum, without cookies and without storing anyone's IP address.

Two kinds of numbers, kept per day in <PCM_STATS_DIR>/<prefix>-<YYYY-MM-DD>.json:

  counters  {group: {key: n}}           pages seen, languages, games played, Murray's answers…
  timings   {group: {key: histogram}}   load times (Core Web Vitals), time on a page, Murray's latency…

Visitors are counted the way Plausible or GoatCounter do it: a hash of the IP address and the browser with a salt
that lives only in memory and changes every day, so the same visitor cannot be followed from one day to the next and
nothing stored points back to a person. The browser sends its events to POST /api/stats (served by server/games.py);
Murray and the games proxy count their own work with hit() and time(). The control panel reads it all with load().
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import Path

# histogram edges (ms, or CLS × 1000); the last bucket is "more than that"
EDGES = [25, 50, 100, 200, 300, 500, 800, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 8000, 10000, 15000, 20000,
         30000, 60000, 120000, 300000, 600000, 1800000]
MAX_KEYS = 400            # per group and day; anything beyond goes to "(other)"
VALUE = re.compile(r"[^\w .:/@>+#()'%,·-]", re.UNICODE)
# Google's thresholds for "good" and "poor" (https://web.dev/articles/vitals)
VITALS = {"LCP": (2500, 4000), "INP": (200, 500), "CLS": (100, 250), "FCP": (1800, 3000), "TTFB": (800, 1800)}


def clean(v, n: int = 60) -> str:
    return VALUE.sub("_", str(v if v is not None else "")).strip()[:n]


def bucket(v: float) -> int:
    for i, e in enumerate(EDGES):
        if v <= e:
            return i
    return len(EDGES)


def percentile(h: dict, p: float) -> float | None:
    """Upper edge of the bucket where the p-th percentile falls (good enough for a dashboard)."""
    n = h.get("n", 0)
    if not n:
        return None
    want, seen = math.ceil(n * p), 0
    for i, c in enumerate(h.get("b", [])):
        seen += c
        if seen >= want:
            return float(EDGES[i]) if i < len(EDGES) else float(h.get("max", 0))
    return float(h.get("max", 0))


class Stats:
    def __init__(self, folder: Path | str | None, prefix: str, every: float = 15):
        self.folder = Path(folder) if folder else None
        self.prefix, self.lock, self.every = prefix, threading.Lock(), every
        self.day, self.doc, self.dirty, self.seen, self.salt = None, None, False, set(), b""
        if self.folder:
            threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------ storage
    def _file(self, day: str) -> Path:
        return self.folder / f"{self.prefix}-{day}.json"

    def _today(self) -> dict:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        if day != self.day:
            if self.doc is not None and self.dirty:
                self._write()
            self.day, self.seen, self.salt = day, set(), secrets.token_bytes(16)
            self.doc = {"counters": {}, "timings": {}, "visitors": 0}
            if self.folder and self._file(day).exists():
                try:
                    self.doc.update(json.loads(self._file(day).read_text("utf-8")))
                except (OSError, ValueError):
                    pass
        return self.doc

    def _write(self):
        if not self.folder or self.doc is None:
            return
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            tmp = self._file(self.day).with_suffix(".tmp")
            tmp.write_text(json.dumps(self.doc, separators=(",", ":")), "utf-8")
            tmp.replace(self._file(self.day))
            self.dirty = False
        except OSError:
            pass  # statistics never break the site

    def _loop(self):
        while True:
            time.sleep(self.every)
            self.flush()

    def flush(self):
        with self.lock:
            if self.dirty:
                self._write()

    # ------------------------------------------------------------ counting
    def hit(self, group: str, key: str = "total", n: int = 1):
        with self.lock:
            g = self._today()["counters"].setdefault(group, {})
            key = clean(key, 140) or "(none)"
            if key not in g and len(g) >= MAX_KEYS:
                key = "(other)"
            g[key] = g.get(key, 0) + n
            self.dirty = True

    def time(self, group: str, key: str, value: float):
        if not isinstance(value, (int, float)) or value != value or value < 0:
            return
        with self.lock:
            g = self._today()["timings"].setdefault(group, {})
            key = clean(key) or "(none)"
            if key not in g and len(g) >= MAX_KEYS:
                key = "(other)"
            h = g.setdefault(key, {"n": 0, "sum": 0, "max": 0, "b": [0] * (len(EDGES) + 1)})
            h["n"] += 1
            h["sum"] += value
            h["max"] = max(h["max"], value)
            h["b"][bucket(value)] += 1
            self.dirty = True

    def visitor(self, ip: str, ua: str) -> bool:
        """True the first time this IP and browser are seen today (only the salted hash is kept, in memory)."""
        with self.lock:
            doc = self._today()
            h = hashlib.sha256(self.salt + ip.encode() + b"|" + ua.encode()).digest()[:12]
            if h in self.seen:
                return False
            self.seen.add(h)
            doc["visitors"] = doc.get("visitors", 0) + 1
            self.dirty = True
            return True


# -------------------------------------------------------------- events from the browser
def _host(ref: str) -> str:
    m = re.match(r"^https?://([^/:?#]+)", str(ref or ""))
    return m.group(1).lower().removeprefix("www.")[:60] if m else ""


def ingest(st: Stats, payload: dict, ip: str, ua: str, own_host: str = "") -> int:
    """Applies the events of one beacon ({"e": [{"n": name, "p": {...}}, …]}); returns how many were valid.
    Unknown events and parameters are ignored: the browser cannot write anything else."""
    events = payload.get("e") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return 0
    ok = 0
    for ev in events[:40]:
        if not isinstance(ev, dict) or not isinstance(ev.get("p", {}), dict):
            continue
        n, p = ev.get("n"), ev.get("p") or {}
        page, lang = clean(p.get("page"), 30), clean(p.get("lang"), 5)
        if n == "page_view":
            if re.search(r"bot|crawl|spider|slurp|headless|preview|lighthouse", ua, re.I):
                st.hit("bots", "page_view")
                continue
            st.hit("pageviews", "total")
            st.hit("pages", page)
            st.hit("langs", lang)
            st.hit("page_lang", f"{page}·{lang}")
            st.hit("devices", clean(p.get("dev"), 10))
            st.hit("navigation", clean(p.get("nav"), 14))
            if p.get("blang"):
                st.hit("browser_langs", clean(p.get("blang"), 5).lower())
            ref = _host(p.get("ref"))
            st.hit("referrers", ref if ref and ref != own_host else "(direct)")
            if st.visitor(ip, ua):
                st.hit("entry_pages", page)
        elif n == "engage":
            sec, scroll = p.get("sec"), p.get("scroll")
            if isinstance(sec, (int, float)) and 0 <= sec < 4 * 3600:
                st.time("time_on_page", page, sec * 1000)
            if isinstance(scroll, (int, float)) and 0 <= scroll <= 100:
                st.hit("scroll_depth", f"{page}·{int(scroll) // 25 * 25}%")
        elif n == "vital":
            name, v = clean(p.get("name"), 5).upper(), p.get("value")
            if name not in VITALS or not isinstance(v, (int, float)):
                continue
            v = v * 1000 if name == "CLS" else v
            st.time("vitals", name, v)
            good, poor = VITALS[name]
            st.hit("vitals_rating", f"{name}·{'good' if v <= good else 'poor' if v > poor else 'needs-improvement'}")
        elif n in ("award", "score_complete", "timeline_open", "arcade_play", "arcade_error", "murray_open",
                   "murray_ask", "murray_go", "lang_switch", "outbound", "toggle", "js_error", "consent", "catalog_search"):
            key = {
                "award": lambda: clean(p.get("key"), 30),
                "score_complete": lambda: "total",
                "timeline_open": lambda: clean(p.get("id")),
                "arcade_play": lambda: clean(p.get("id")),
                "arcade_error": lambda: f"{clean(p.get('id'))}·{clean(p.get('kind'), 20)}",
                "murray_open": lambda: page,
                "murray_ask": lambda: page,
                "murray_go": lambda: clean(p.get("to")),
                "lang_switch": lambda: f"{clean(p.get('from'), 5)}>{clean(p.get('to'), 5)}",
                "outbound": lambda: _host(p.get("url")) or "(none)",
                "toggle": lambda: f"{clean(p.get('what'), 10)}·{'on' if p.get('on') else 'off'}",
                "js_error": lambda: f"{clean(p.get('src'), 30)}:{int(p.get('line') or 0)} {clean(p.get('msg'), 100)}",
                "consent": lambda: "granted" if p.get("granted") else "denied",
                "catalog_search": lambda: "results" if p.get("results") else "no results",
            }[n]()
            st.hit(n, key)
            if n == "arcade_play":
                st.hit("arcade_engine", clean(p.get("engine"), 10))
                st.hit("arcade_source", clean(p.get("src"), 10))
        else:
            continue
        ok += 1
    return ok


# -------------------------------------------------------------- reading
def load(folder: Path | str | None, days: int = 30, prefixes: tuple[str, ...] | None = None) -> dict:
    """{"days": {date: {prefix: doc}}} for the last `days` days (today included)."""
    out: dict = {}
    if not folder or not Path(folder).exists():
        return {"days": out}
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - (days - 1) * 86400))
    for f in sorted(Path(folder).glob("*-????-??-??.json")):
        prefix, day = f.stem[:-11], f.stem[-10:]
        if day < since or (prefixes and prefix not in prefixes):
            continue
        try:
            out.setdefault(day, {})[prefix] = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
    return {"days": out}


def summary(raw: dict) -> dict:
    """Adds up the days of load() (several sources merged) into what the panel shows."""
    counters: dict = {}
    timings: dict = {}
    daily = []
    for day in sorted(raw.get("days", {})):
        row = {"date": day, "visitors": 0, "pageviews": 0, "murray": 0, "plays": 0}
        for prefix, doc in raw["days"][day].items():
            row["visitors"] += doc.get("visitors", 0)
            c = doc.get("counters", {})
            row["pageviews"] += c.get("pageviews", {}).get("total", 0)
            if prefix == "murray":
                row["murray"] += c.get("requests", {}).get("total", 0)
            row["plays"] += sum(c.get("arcade_play", {}).values())
            for g, kv in c.items():
                tgt = counters.setdefault(f"{prefix}.{g}", {})
                for k, n in kv.items():
                    tgt[k] = tgt.get(k, 0) + n
            for g, kv in doc.get("timings", {}).items():
                tgt = timings.setdefault(f"{prefix}.{g}", {})
                for k, h in kv.items():
                    t = tgt.setdefault(k, {"n": 0, "sum": 0, "max": 0, "b": [0] * (len(EDGES) + 1)})
                    t["n"] += h.get("n", 0)
                    t["sum"] += h.get("sum", 0)
                    t["max"] = max(t["max"], h.get("max", 0))
                    t["b"] = [a + b for a, b in zip(t["b"], h.get("b", []) + [0] * (len(t["b"]) - len(h.get("b", []))))]
        daily.append(row)
    times = {g: {k: {"n": h["n"], "avg": round(h["sum"] / h["n"], 1) if h["n"] else None, "max": round(h["max"], 1),
                     "p50": percentile(h, .5), "p75": percentile(h, .75), "p95": percentile(h, .95)} for k, h in kv.items()}
             for g, kv in timings.items()}
    return {"daily": daily, "counters": counters, "timings": times,
            "totals": {k: sum(r[k] for r in daily) for k in ("visitors", "pageviews", "murray", "plays")}}


def folder_from_env(default: Path) -> Path | None:
    v = os.environ.get("PCM_STATS_DIR")
    if v == "off":
        return None
    return Path(v) if v else default
