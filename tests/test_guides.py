"""Murray's walkthrough search (server/guides.py): a fake Adventure Gamers (WordPress API) and a fake model on
localhost, no network. What is checked: the right guide is found, the passages answer the question, robots.txt and the
list of sites are respected, and the guide reaches the model (tool or prompt) and the visitor (link)."""
import json
import os
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
for k in [k for k in os.environ if k.startswith("MURRAY_LLM_")]:
    del os.environ[k]
import guides  # noqa: E402
import murray  # noqa: E402

LOOM = ("<h2>Contents</h2><p>1. Introduction<br>2. Walkthrough<br>2.1. The island<br>3. Drafts<br>4. Credits</p>"
        "<p>Bobbin starts on the island of Loom. Walk left to the village.</p>"
        "<p>One of the first puzzles requires an egg to Open. Look at the egg to get the Open draft, then cast the "
        "Open draft on the egg.</p><script>alert('no')</script><nav>Menu Home Reviews</nav>"
        "<p>At the forge, use the Sharpen draft on the sword.</p>" + "<p>Filler paragraph about the weather.</p>" * 30)
WALKTHROUGHS = [{"id": 1, "title": {"rendered": "Return to Monkey Island"}, "link": "/walkthroughs/return-to-monkey-island"},
                {"id": 2, "title": {"rendered": "Loom"}, "link": "/walkthroughs/loom"},
                {"id": 3, "title": {"rendered": "Monkey Island 2: LeChuck&#8217;s Revenge"}, "link": "/walkthroughs/monkey-island-2"}]


class FakeSite(BaseHTTPRequestHandler):
    robots, hits = "User-agent: *\nDisallow: /wp-admin/\n", []

    def log_message(self, *a):
        pass

    def do_GET(self):
        FakeSite.hits.append(self.path)
        u = urllib.parse.urlsplit(self.path)
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        if u.path == "/robots.txt":
            return self.send(200, FakeSite.robots, "text/plain")
        if u.path == "/wp-json/wp/v2/walkthroughs":
            assert not u.query.startswith("s"), "their robots.txt forbids *?s"
            q = urllib.parse.parse_qs(u.query)["search"][0].lower()
            found = [dict(w, link=base + w["link"]) for w in WALKTHROUGHS if any(t in w["title"]["rendered"].lower() for t in q.split())]
            return self.send(200, json.dumps(found), "application/json")
        if u.path.startswith("/wp-json/wp/v2/walkthroughs/"):
            return self.send(200, json.dumps({"content": {"rendered": LOOM}}), "application/json")
        if u.path == "/search":  # a SearXNG instance
            return self.send(200, json.dumps({"results": [
                {"url": "https://evil.example/zak", "title": "Zak McKracken walkthrough"},          # not a guide site
                {"url": base + "/zak.html", "title": "Zak McKracken and the Alien Mindbenders - walkthrough"}]}), "application/json")
        if u.path == "/zak.html":
            return self.send(200, "<p>Intro to the guide.</p>" * 4 + "<p>Use the kazoo with the bus driver to get on the bus.</p>"
                             + "<p>More steps here.</p>" * 4, "text/html")
        if u.path == "/elsewhere":
            self.send_response(302)
            self.send_header("Location", "https://evil.example/x")
            self.end_headers()
            return
        self.send(404, "no", "text/plain")

    def send(self, code, text, kind):
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class FakeLLM(BaseHTTPRequestHandler):
    """First turn: calls search_guides; then answers with a hint. Records what it was sent."""
    requests = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLLM.requests.append(body)
        if "You are a topic filter" in body["messages"][0]["content"]:
            msg = {"role": "assistant", "content": "ON"}
        elif "tools" in body and body["messages"][-1]["role"] == "user":
            msg = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "search_guides", "arguments": json.dumps({"game": "Loom", "question": "open the egg"})}}]}
        else:
            msg = {"role": "assistant", "content": "Mira bien el huevo, mortal."}
        data = json.dumps({"choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
        cls.llm = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
        for s in (cls.site, cls.llm):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.site.server_address[1]}"
        os.environ.update(MURRAY_GUIDES_AG_BASE=cls.base, MURRAY_GUIDES_TEST_HOSTS="127.0.0.1")

    @classmethod
    def tearDownClass(cls):
        for s in (cls.site, cls.llm):
            s.shutdown()
        for k in ("MURRAY_GUIDES_AG_BASE", "MURRAY_GUIDES_TEST_HOSTS"):
            os.environ.pop(k, None)

    def setUp(self):
        guides.CACHE.data.clear()
        guides.ROBOTS.data.clear()
        FakeSite.robots, FakeSite.hits, FakeLLM.requests = "User-agent: *\nDisallow: /wp-admin/\n", [], []

    def tearDown(self):
        for k in ("MURRAY_LLM_BASE_URL", "MURRAY_LLM_MODEL", "MURRAY_LLM_TOOLS"):
            os.environ.pop(k, None)

    def model(self, **extra):
        os.environ.update(MURRAY_LLM_BASE_URL=f"http://127.0.0.1:{self.llm.server_address[1]}/v1", MURRAY_LLM_MODEL="m", **extra)

    def test_finds_the_guide_and_the_passage(self):
        r = guides.find("Loom", "how do I open the egg", murray.GUIDES)
        self.assertTrue(r["found"], r)
        g = r["guide"]
        self.assertEqual((g["site"], g["url"]), ("Adventure Gamers", self.base + "/walkthroughs/loom"))
        text = "\n".join(g["excerpts"])
        self.assertIn("Open draft", text)
        self.assertNotIn("alert", text)                 # no scripts
        self.assertNotIn("2.1. The island", text)       # not the table of contents
        self.assertLessEqual(len(text), guides.EXCERPT_CHARS + 900)
        guides.find("Loom", "how do I open the egg", murray.GUIDES)
        self.assertEqual(sum("/wp-json/wp/v2/walkthroughs/" in h for h in FakeSite.hits), 1, "cached for a day")

    def test_sequel_numbers_matter(self):
        self.assertLess(guides.similarity("Monkey Island 2", "Return to Monkey Island"), 0.6)
        self.assertGreater(guides.similarity("Monkey Island 2", "Monkey Island 2: LeChuck’s Revenge"), 0.6)
        self.assertGreater(guides.similarity("King's Quest V", "King’s Quest V: Absence Makes the Heart Go Yonder"), 0.6)
        self.assertLess(guides.similarity("King's Quest", "King’s Quest VI: Heir Today, Gone Tomorrow"), 0.6)
        r = guides.find("Monkey Island 2: LeChuck's Revenge", "spit contest", murray.GUIDES)
        self.assertIn("monkey-island-2", r["guide"]["url"])

    def test_which_game(self):
        self.assertEqual(murray.game_in("soluce de Monkey Island 2", "fr"), "Monkey Island 2: LeChuck's Revenge")
        self.assertEqual(murray.game_in("¿cómo paso el puzzle del mono en Monkey Island?", "es"), "The Secret of Monkey Island")
        self.assertTrue(murray.game_in("pista para el King's Quest V", "es").startswith("King's Quest V"))
        self.assertEqual(murray.game_in("¿qué tiempo hace?", "es"), "")

    def test_robots_and_allowed_sites(self):
        FakeSite.robots = "User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        self.assertFalse(guides.find("Loom", "egg", murray.GUIDES)["found"], "a site that keeps AI agents out is skipped")
        self.assertFalse(any("/wp-json/" in h for h in FakeSite.hits))
        with self.assertRaises(ValueError):
            guides.fetch("https://evil.example/x", murray.GUIDES["sites"])
        with self.assertRaises(Exception):
            guides.fetch(self.base + "/elsewhere", murray.GUIDES["sites"])   # redirect to another site
        self.assertTrue(guides.host_allowed("https://www.adventuregamers.com/x", ["adventuregamers.com"]))
        self.assertFalse(guides.host_allowed("http://adventuregamers.com/x", ["adventuregamers.com"]))   # https only
        self.assertFalse(guides.host_allowed("https://adventuregamers.com.evil.example/", ["adventuregamers.com"]))

    def test_offline_murray_links_the_guide(self):
        r = murray.answer({"lang": "es", "messages": [{"role": "user", "content": "Estoy atascado en Loom, ¿cómo abro el huevo?"}]})
        self.assertEqual(r["sources"][0]["url"], self.base + "/walkthroughs/loom")
        self.assertIn("Adventure Gamers", r["reply"])
        r = murray.answer({"lang": "es", "messages": [{"role": "user", "content": "¿Quién creó Loom?"}]})
        self.assertNotIn("walkthroughs", json.dumps(r["sources"]), "no guide unless the visitor is stuck")

    def test_model_calls_the_tool(self):
        self.model()
        r = murray.answer({"lang": "es", "messages": [{"role": "user", "content": "¿Cómo abro el huevo en Loom?"}]})
        self.assertEqual(r["reply"], "Mira bien el huevo, mortal.")
        first = next(b for b in FakeLLM.requests if "tools" in b)
        self.assertIn("search_guides", {t["function"]["name"] for t in first["tools"]})
        tool = next(m for b in FakeLLM.requests for m in b["messages"] if m["role"] == "tool")
        self.assertIn("Open draft", tool["content"])
        self.assertIn("untrusted", tool["content"])
        self.assertEqual(r["sources"][0]["url"], self.base + "/walkthroughs/loom")

    def test_model_without_tools_gets_the_guide_in_the_prompt(self):
        self.model(MURRAY_LLM_TOOLS="0")
        murray.answer({"lang": "en", "messages": [{"role": "user", "content": "I'm stuck in Loom, how do I open the egg?"}]})
        system = next(b for b in FakeLLM.requests if "topic filter" not in b["messages"][0]["content"])["messages"][0]["content"]
        self.assertIn("Walkthrough for the visitor's question", system)
        self.assertIn("Open draft", system)

    def test_other_sites_through_searxng(self):
        os.environ["MURRAY_SEARCH_URL"] = self.base
        try:
            r = guides.find("Zak McKracken and the Alien Mindbenders", "bus driver", murray.GUIDES)
        finally:
            del os.environ["MURRAY_SEARCH_URL"]
        self.assertTrue(r["found"], r)
        self.assertEqual(r["guide"]["url"], self.base + "/zak.html")
        self.assertIn("kazoo", " ".join(r["guide"]["excerpts"]))

    def test_can_be_turned_off(self):
        os.environ["MURRAY_GUIDES"] = "0"
        try:
            self.assertFalse(guides.find("Loom", "egg", murray.GUIDES)["found"])
            self.assertFalse(murray.asked_for_solution("solución de Loom"))
        finally:
            del os.environ["MURRAY_GUIDES"]
        self.assertEqual(FakeSite.hits, [])


if __name__ == "__main__":
    unittest.main()
