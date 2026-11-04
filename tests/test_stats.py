"""Usage statistics (server/stats.py): what the browser may write, visitors, histograms, files and the summary."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import stats  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"


def doc(st):
    with st.lock:
        return json.loads(json.dumps(st._today()))


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.st = stats.Stats(None, "web")

    def test_page_view_counts_page_language_device_and_referrer_host(self):
        n = stats.ingest(self.st, {"e": [{"n": "page_view", "p": {"page": "timeline", "lang": "es", "dev": "mobile",
                                                                  "ref": "https://www.google.com/search?q=monkey", "nav": "navigate"}}]},
                         "1.2.3.4", UA, "museum.example")
        self.assertEqual(n, 1)
        c = doc(self.st)["counters"]
        self.assertEqual(c["pages"], {"timeline": 1})
        self.assertEqual(c["langs"], {"es": 1})
        self.assertEqual(c["devices"], {"mobile": 1})
        self.assertEqual(c["referrers"], {"google.com": 1}, "only the host of the referrer, never the query")
        self.assertEqual(doc(self.st)["visitors"], 1)

    def test_own_site_and_empty_referrer_are_direct(self):
        for ref in ("", "https://museum.example/es/"):
            stats.ingest(self.st, {"e": [{"n": "page_view", "p": {"page": "home", "ref": ref}}]}, "1.2.3.4", UA, "museum.example")
        self.assertEqual(doc(self.st)["counters"]["referrers"], {"(direct)": 2})

    def test_unknown_events_and_bad_shapes_are_ignored(self):
        n = stats.ingest(self.st, {"e": [{"n": "steal", "p": {"x": 1}}, "nope", {"n": "award", "p": "x"}, {"n": "award", "p": {"key": "hero"}}]}, "1.1.1.1", UA)
        self.assertEqual(n, 1)
        self.assertEqual(set(doc(self.st)["counters"]), {"award"})
        self.assertEqual(stats.ingest(self.st, ["e"], "1.1.1.1", UA), 0)

    def test_values_are_cleaned_and_short(self):
        stats.ingest(self.st, {"e": [{"n": "timeline_open", "p": {"id": "<script>alert(1)</script>" + "x" * 200}}]}, "1.1.1.1", UA)
        key = next(iter(doc(self.st)["counters"]["timeline_open"]))
        self.assertNotIn("<", key)
        self.assertLessEqual(len(key), 60)

    def test_same_visitor_counts_once_a_day(self):
        for _ in range(3):
            stats.ingest(self.st, {"e": [{"n": "page_view", "p": {"page": "home"}}]}, "9.9.9.9", UA)
        stats.ingest(self.st, {"e": [{"n": "page_view", "p": {"page": "home"}}]}, "9.9.9.8", UA)
        d = doc(self.st)
        self.assertEqual(d["visitors"], 2)
        self.assertEqual(d["counters"]["pageviews"], {"total": 4})
        self.assertNotIn("9.9.9.9", json.dumps(d), "no IP address is stored")

    def test_bots_are_not_page_views(self):
        stats.ingest(self.st, {"e": [{"n": "page_view", "p": {"page": "home"}}]}, "1.1.1.1", "Googlebot/2.1")
        c = doc(self.st)["counters"]
        self.assertNotIn("pageviews", c)
        self.assertEqual(c["bots"], {"page_view": 1})

    def test_vitals_are_rated_with_googles_thresholds(self):
        stats.ingest(self.st, {"e": [{"n": "vital", "p": {"name": "LCP", "value": 1800}}, {"n": "vital", "p": {"name": "CLS", "value": 0.3}},
                                     {"n": "vital", "p": {"name": "XYZ", "value": 1}}]}, "1.1.1.1", UA)
        d = doc(self.st)
        self.assertEqual(d["counters"]["vitals_rating"], {"LCP·good": 1, "CLS·poor": 1})
        self.assertEqual(d["timings"]["vitals"]["CLS"]["max"], 300)

    def test_too_many_keys_fold_into_other(self):
        for i in range(stats.MAX_KEYS + 5):
            self.st.hit("outbound", f"site{i}.example")
        g = doc(self.st)["counters"]["outbound"]
        self.assertEqual(len(g), stats.MAX_KEYS + 1)
        self.assertEqual(g["(other)"], 5)


class SummaryTest(unittest.TestCase):
    def test_percentiles_from_the_histogram(self):
        st = stats.Stats(None, "murray")
        for v in [90] * 50 + [900] * 45 + [9000] * 5:
            st.time("latency", "first word", v)
        h = doc(st)["timings"]["latency"]["first word"]
        self.assertEqual(stats.percentile(h, .5), 100)
        self.assertEqual(stats.percentile(h, .95), 1000)
        self.assertEqual(stats.percentile(h, .99), 10000)

    def test_files_on_disk_and_summary_of_several_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            web, murray = stats.Stats(tmp, "web", every=3600), stats.Stats(tmp, "murray", every=3600)
            stats.ingest(web, {"e": [{"n": "page_view", "p": {"page": "home"}}, {"n": "arcade_play", "p": {"id": "paint", "engine": "dosbox", "src": "museum"}}]}, "1.1.1.1", UA)
            murray.hit("requests", "total")
            murray.time("latency", "whole answer", 1200)
            web.flush(); murray.flush()
            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 2)
            again = stats.Stats(tmp, "web", every=3600)   # a restart keeps today's numbers
            again.hit("pages", "home")
            self.assertEqual(doc(again)["counters"]["pages"]["home"], 2)
            s = stats.summary(stats.load(tmp, 7))
            self.assertEqual(s["totals"], {"visitors": 1, "pageviews": 1, "murray": 1, "plays": 1})
            self.assertEqual(s["counters"]["web.arcade_engine"], {"dosbox": 1})
            self.assertEqual(s["timings"]["murray.latency"]["whole answer"]["p50"], 1500)


if __name__ == "__main__":
    unittest.main()
