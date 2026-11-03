"""Tests for Murray's external knowledge base: tools/build_murray_kb.py and its use in server/knowledge.py.
Wikipedia is a fake MediaWiki API on localhost: no network."""
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
sys.path.insert(0, str(ROOT / "tools"))
import build_murray_kb as kb  # noqa: E402
import knowledge  # noqa: E402


class FakeWiki(BaseHTTPRequestHandler):
    lagged = set()

    def log_message(self, *a):
        pass

    def send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        lang = self.path.split("/")[1]
        titles = q["titles"].split("|")
        if q.get("prop") != "langlinks" and titles[0].startswith("Broken"):    # API error, HTTP 200, no "query"
            return self.send({"error": {"code": "badvalue", "info": "Unrecognized value"}})
        if q.get("prop") != "langlinks" and titles[0].startswith("Empty"):     # no "query" and no "error"
            return self.send({"batchcomplete": True})
        if q.get("prop") != "langlinks" and titles[0].startswith("Lagging") and titles[0] not in FakeWiki.lagged:
            FakeWiki.lagged.add(titles[0])
            return self.send({"error": {"code": "maxlag", "info": "Waiting for a database server"}})
        if q.get("prop") == "langlinks":
            pages = [{"title": t, "langlinks": [{"lang": "es", "title": t + " (es)"}]} if t != "Nope" else {"title": t, "missing": True}
                     for t in titles]
        else:
            text = ("Intro paragraph about " + titles[0] + ".\n\n== History ==\n" + "A long paragraph. " * 40 +
                    "\n\n== References ==\nShould be skipped.")
            pages = [{"title": titles[0], "extract": text, "fullurl": f"https://{lang}.wikipedia.org/wiki/x"}]
        data = json.dumps({"query": {"pages": pages}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


class BuilderTests(unittest.TestCase):
    def test_parse_scummvm_yaml(self):
        text = "# generated\n-\n    id: 'scumm:monkey'\n    name: 'The Secret of Monkey Island'\n    year: '1990'\n-\n    id: x\n    name: 'It''s ok'\n"
        items = kb.parse_list_yaml(text)
        self.assertEqual(items[0], {"id": "scumm:monkey", "name": "The Secret of Monkey Island", "year": "1990"})
        self.assertEqual(items[1]["name"], "It's ok")

    def test_passages_skip_reference_sections(self):
        p = kb.passages("Intro.\n== History ==\n" + "x " * 600 + "\n== References ==\nref", 500)
        self.assertEqual(p[0], ("", "Intro."))
        self.assertTrue(all(sec != "References" for sec, _ in p))

    def test_wikipedia_with_fake_api(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeWiki)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ["PCM_WIKI_API"] = f"http://127.0.0.1:{srv.server_address[1]}/{{lang}}/api.php"
        old = kb.TOPICS, kb.museum_titles
        kb.TOPICS, kb.museum_titles = ["Adventure game", "Nope", "Broken one", "Empty one", "Lagging one"], lambda: ["Loom (video game)"]
        old_sleep, kb.PAUSE = kb.time.sleep, 0
        kb.time.sleep = lambda s: None
        try:
            out = kb.build_wikipedia(["es", "en"], 300)
        finally:
            kb.TOPICS, kb.museum_titles = old
            kb.time.sleep = old_sleep
            del os.environ["PCM_WIKI_API"]
            srv.shutdown()
        self.assertTrue(out["en"] and out["es"])
        d = out["es"][0]
        self.assertEqual((d["kind"], d["lang"]), ("wikipedia", "es"))
        self.assertIn("CC BY-SA", d["license"])
        self.assertFalse(any("Should be skipped" in x["text"] for x in out["en"]))
        titles = {x["title"].split(" · ")[0] for x in out["en"]}
        self.assertIn("Lagging one", titles)          # retried after maxlag
        self.assertNotIn("Broken one", titles)        # skipped, the rest still built
        self.assertNotIn("Empty one", titles)


class KnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = knowledge.Museum(ROOT / "data")

    def test_history_articles_have_sources(self):
        hist = [d for d in self.m.docs["en"] if d.kind == "history"]
        self.assertGreaterEqual(len(hist), 10)
        self.assertTrue(all(d.fields["sources"] and d.fields["sources"][0].startswith("https://") for d in hist))

    def test_spanish_questions_reach_english_articles(self):
        self.assertEqual(self.m.search("¿Por qué murieron las aventuras gráficas?", "es", 1)[0].id, "history:decline-late-1990s")
        self.assertEqual(self.m.search("Kickstarter de Double Fine", "es", 1)[0].id, "history:kickstarter-revival")

    def test_about_answers_what_this_museum_is(self):
        top = self.m.search("¿Este museo es el Museo de Informática de la UPV?", "es", 1)[0]
        self.assertEqual(top.kind, "about")
        self.assertIn("UPV", top.text)

    def test_resolve_target(self):
        r = self.m.resolve_target
        self.assertEqual(r("timeline"), {"page": "timeline", "hash": "", "title": ""})
        self.assertEqual(r("game:loom")["hash"], "loom")
        self.assertEqual(r("Grim Fandango", "en")["hash"], "grim-fandango")
        self.assertEqual(r("engine:scumm")["hash"], "engine-scumm")
        self.assertEqual(r("era:golden")["hash"], "era-golden")
        self.assertIsNone(r("history:telltale"))        # web articles are not places in the museum
        self.assertIsNone(r("game:does-not-exist"))

    def test_scummvm_catalogue_extends_lists(self):
        self.assertTrue(any(d.kind == "catalogue" for d in self.m.search("Gobliins 2", "en", 3)))
        games = self.m.list_games("en", 1993, 1993)
        self.assertEqual(games[0].kind, "game")
        self.assertTrue(any(d.kind == "catalogue" for d in games))


if __name__ == "__main__":
    unittest.main()
