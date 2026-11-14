"""Walkthroughs for Murray: when a visitor is stuck, find the game's guide on the web and pick the passages that
answer the question, so that Murray can give a hint in his own words and link the guide.

Sources (data/murray.json -> guides):
  * Adventure Gamers (adventuregamers.com): thousands of adventure walkthroughs, searched through its public
    WordPress API (/wp-json/wp/v2/walkthroughs?search=…), which also returns the guide's text. No key needed.
  * Optionally, a SearXNG instance (MURRAY_SEARCH_URL, e.g. a self-hosted http://searxng:8080) to find guides on the
    other allowed sites (guides.sites). Results outside those sites are ignored.

Manners: only https pages of the allowed sites (redirects included), robots.txt is honoured for our own user agent
and for the usual AI agents (a site that keeps AI agents out is skipped), small pages only, short timeouts and a
cache of a day, so a popular question costs the guide's site one request. Only short passages go to the model,
marked as untrusted third-party text. Standard library only.

Environment: MURRAY_GUIDES (1 = on, default; 0 = off), MURRAY_SEARCH_URL (SearXNG base URL, optional),
MURRAY_GUIDES_TEST_HOSTS (tests only: hosts allowed over plain http, e.g. 127.0.0.1).
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser

from knowledge import tokens

UA = "PointAndClickMuseum-Murray/1.0 (+museum guide; fetches a walkthrough when a visitor asks)"
AI_AGENTS = ("PointAndClickMuseum-Murray", "Claude-User", "ClaudeBot", "anthropic-ai", "ChatGPT-User", "GPTBot", "CCBot")
MAX_BYTES = 2_000_000
TTL = 86400
TIMEOUT = 10
EXCERPT_CHARS = 2400


def enabled() -> bool:
    return os.environ.get("MURRAY_GUIDES", "1") != "0"


def test_hosts() -> set[str]:
    return {h.strip() for h in os.environ.get("MURRAY_GUIDES_TEST_HOSTS", "").split(",") if h.strip()}


class Cache:
    def __init__(self, size: int = 300):
        self.size, self.data, self.lock = size, {}, threading.Lock()

    def get(self, key):
        with self.lock:
            hit = self.data.get(key)
            return hit[1] if hit and time.time() - hit[0] < TTL else None

    def put(self, key, value):
        with self.lock:
            if len(self.data) >= self.size:
                self.data.pop(min(self.data, key=lambda k: self.data[k][0]))
            self.data[key] = (time.time(), value)
        return value


CACHE, ROBOTS = Cache(), Cache(100)


def host_allowed(url: str, sites: list[str]) -> bool:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme == "http" and host in test_hosts():
        return True
    return u.scheme == "https" and any(host == s or host.endswith("." + s) for s in sites)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, sites):
        self.sites = sites

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl, self.sites):
            raise urllib.error.URLError(f"redirect outside the guide sites: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, sites: list[str], accept: str = "text/html,application/json,text/plain") -> str:
    if not host_allowed(url, sites):
        raise ValueError(f"not a guide site: {url}")
    hit = CACHE.get(("page", url))
    if hit is not None:
        return hit
    opener = urllib.request.build_opener(_Redirects(sites))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with opener.open(req, timeout=TIMEOUT) as r:
        kind = r.headers.get("Content-Type", "")
        if not re.search(r"html|json|text/plain", kind):
            raise ValueError(f"not a web page ({kind})")
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("page too large")
    return CACHE.put(("page", url), data.decode("utf-8", "replace"))


def robots_ok(url: str, sites: list[str]) -> bool:
    """False if the site's robots.txt keeps us, or any well-known AI agent, out of this page."""
    u = urllib.parse.urlsplit(url)
    root = f"{u.scheme}://{u.netloc}"
    rp = ROBOTS.get(root)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(fetch(root + "/robots.txt", sites, "text/plain").splitlines())
        except urllib.error.HTTPError as e:
            rp.parse([] if e.code in (404, 410) else ["User-agent: *", "Disallow: /"])  # missing = allowed; errors = wait
        except Exception:
            rp.parse(["User-agent: *", "Disallow: /"])
        ROBOTS.put(root, rp)
    return all(rp.can_fetch(agent, url) for agent in AI_AGENTS)


class _Text(HTMLParser):
    """Text of a page in blocks (paragraphs, list items, headings, preformatted guides), without menus or scripts."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "iframe", "button"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "br", "tr", "section", "article", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.parts = 0, [""]

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def page_text(markup: str) -> list[str]:
    p = _Text()
    p.feed(markup)
    text = re.sub(r"[ \t ]+", " ", "".join(p.parts))
    blocks = [b.strip() for b in re.split(r"\n\s*\n|\n(?=\s*[=\-–—_]{6,})", text)]
    out = []
    for b in blocks:
        b = re.sub(r"\s*\n\s*", "\n", b)
        if len(re.sub(r"[\W_]+", "", b)) >= 12:  # rules of ===== and empty lines are not passages
            out.extend(b[i:i + 900] for i in range(0, len(b), 900))
    return out


def stem(w: str) -> str:
    """Enough English stemming to match a question with a guide: balloons/balloon, opening/open, used/use."""
    for end in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(end) + 3 and w.endswith(end):
            return w[: -len(end)] + ("y" if end == "ies" else "")
    return w


def excerpts(blocks: list[str], question: str, limit: int = EXCERPT_CHARS, window: int = 700) -> list[str]:
    """The stretches of the guide that share most words with the question, in the guide's order. Guides are often
    written one short line per step: consecutive lines are grouped into windows of about `window` characters."""
    want = {stem(w) for w in tokens(question, stop=True)}
    lines = [ln for b in blocks for ln in b.split("\n") if ln.strip()]
    keep, run = [True] * len(lines), []  # runs of 3+ numbered lines are a table of contents: they explain nothing
    for k, ln in enumerate(lines + [""]):
        if k < len(lines) and TOC.match(ln):
            run.append(k)
            continue
        if len(run) >= 3:
            for r in run:
                keep[r] = False
        run = []
    blocks = [ln for k, ln in enumerate(lines) if keep[k]]
    wins, i = [], 0
    while i < len(blocks):
        j, size = i, 0
        while j < len(blocks) and (size == 0 or size + len(blocks[j]) <= window):
            size += len(blocks[j]) + 1
            j += 1
        wins.append((i, j))
        i = j if j > i else i + 1
    if not want:
        return ["\n".join(blocks[a:b]) for a, b in wins[:2]]
    def score(a, b):
        lines = "\n".join(blocks[a:b]).split("\n")
        have = {stem(w) for w in tokens(" ".join(lines))}
        sc = len(want & have)
        index = sum(1 for ln in lines if TOC.match(ln))  # a table of contents names everything and explains nothing
        return sc * 0.2 if index >= max(3, len(lines) // 3) else sc
    ranked = sorted(((score(a, b), a, b) for a, b in wins), key=lambda x: (-x[0], x[1]))
    chosen, size = [], 0
    for sc, a, b in ranked:
        text = "\n".join(blocks[a:b])
        if sc <= 0 or (chosen and size + len(text) > limit):
            break
        chosen.append((a, text))
        size += len(text)
    return [t for _, t in sorted(chosen)]


TOC = re.compile(r"^\s*(\d+(\.\d+)*\.?|[ivx]+\.|author:|e-?mail:|version:|updated:)\s", re.I)
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
MINOR = {"the", "of", "a", "an", "and", "to", "in", "s", "el", "la", "de", "der", "die", "le"}


def title_words(t: str) -> set[str]:
    """Words of a title with sequel numbers kept and Roman numerals as digits (King's Quest V -> king quest 5)."""
    t = re.sub(r"['’]", "", t)  # King's and King’s are the same word
    folded = " ".join(tokens(t, stop=False) + re.findall(r"(?<![a-z'’])(?:i{1,3}|iv|vi{0,3}|ix|x|\d)(?![a-z])", t.lower()))
    return {ROMAN.get(w, w) for w in folded.split()} - MINOR


def similarity(a: str, b: str) -> float:
    """How well a guide's title matches the game asked for: the words of the game should all be there, few extra
    ones, and the same sequel number (Monkey Island 2 is not Return to Monkey Island)."""
    wa, wb = title_words(a), title_words(b)
    if not wa or not wb:
        return 0.0
    if wa == wb:
        return 1.0
    common = len(wa & wb)
    sc = 0.7 * common / len(wa) + 0.3 * common / len(wb)
    nums_a, nums_b = {w for w in wa if w.isdigit()}, {w for w in wb if w.isdigit()}
    if nums_a != nums_b and not (nums_a == {"1"} and not nums_b):
        sc *= 0.5
    return sc


def adventure_gamers(game: str, question: str, cfg: dict, sites: list[str]) -> dict | None:
    base = os.environ.get("MURRAY_GUIDES_AG_BASE", cfg.get("base", "https://adventuregamers.com")).rstrip("/")
    api = f"{base}/wp-json/wp/v2/walkthroughs"
    # per_page first: its robots.txt has "Disallow: *?s" (WordPress search pages, ?s=), which ?search= would match
    # its search wants plain words: first the main title ("King's Quest V", not "…: Absence…!"), then the whole title
    plain = lambda t: re.sub(r"\s+", " ", re.sub(r"[^\w\s'’]", " ", t)).strip()
    best = (0, None)
    for words in dict.fromkeys(w for w in (plain(game.split(":")[0]), plain(game)) if w):
        q = urllib.parse.urlencode({"per_page": 20, "_fields": "id,link,title", "search": words[:80]})
        if not robots_ok(f"{api}?{q}", sites):
            return None
        found = json.loads(fetch(f"{api}?{q}", sites, "application/json"))
        best = max([best] + [(similarity(game, html.unescape(r["title"]["rendered"])), r) for r in found if isinstance(r, dict)],
                   key=lambda x: x[0])
        if best[0] >= 0.6:
            break
    if best[0] < 0.6:
        return None
    r = best[1]
    title, link = html.unescape(r["title"]["rendered"]), r.get("link", "")
    if not host_allowed(link, sites):
        link = f"{base}/walkthroughs/"
    body = json.loads(fetch(f"{api}/{int(r['id'])}?_fields=content", sites, "application/json"))
    blocks = page_text((body.get("content") or {}).get("rendered", ""))
    return {"site": cfg.get("name", "Adventure Gamers"), "title": f"{title} walkthrough", "url": link,
            "excerpts": excerpts(blocks, question)}


def searxng(game: str, question: str, sites: list[str]) -> dict | None:
    base = os.environ.get("MURRAY_SEARCH_URL", "").rstrip("/")
    if not base:
        return None
    q = urllib.parse.urlencode({"q": f"{game} walkthrough", "format": "json"})
    req = urllib.request.Request(f"{base}/search?{q}", headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # our own search service, not a guide site
        results = json.loads(r.read(MAX_BYTES)).get("results", [])
    for res in results[:20]:
        url = res.get("url", "")
        if not host_allowed(url, sites) or similarity(game, res.get("title", "")) < 0.3 or not robots_ok(url, sites):
            continue
        blocks = page_text(fetch(url, sites))
        if len(blocks) >= 5:
            return {"site": urllib.parse.urlsplit(url).hostname, "title": res.get("title") or url, "url": url,
                    "excerpts": excerpts(blocks, question)}
    return None


def find(game: str, question: str, conf: dict) -> dict:
    """-> {"found": bool, "guide": {...}} or {"found": False, "error": "..."}; never raises."""
    game, question = re.sub(r"\s+", " ", game or "").strip()[:100], (question or "")[:300]
    if not enabled():
        return {"found": False, "error": "guide search is turned off"}
    if not game:
        return {"found": False, "error": "say which game"}
    key = ("find", game.lower(), question.lower())
    hit = CACHE.get(key)
    if hit is not None:
        return hit
    sites = [s.lower() for s in conf.get("sites", [])]
    title_words = set(tokens(game))  # every passage of the guide names the game: only the question's own words count
    question = " ".join(w for w in tokens(question, stop=True) if w not in title_words) or question
    errors = []
    for source in (lambda: adventure_gamers(game, question, conf.get("adventureGamers", {}), sites),
                   lambda: searxng(game, question, sites)):
        try:
            g = source()
        except Exception as e:  # network, bad JSON…: try the next source
            errors.append(type(e).__name__)
            continue
        if g:
            return CACHE.put(key, {"found": True, "guide": g})
    out = {"found": False, "error": "no guide found for that game" + (f" ({', '.join(errors)})" if errors else "")}
    return out if errors else CACHE.put(key, out)


def wants_solution(message: str, words: list[str]) -> bool:
    folded = " " + " ".join(tokens(message)) + " "
    return any(f" {' '.join(tokens(w))} " in folded for w in words)
