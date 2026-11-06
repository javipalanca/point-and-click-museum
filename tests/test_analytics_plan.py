"""The Google Analytics measurement plan (data/analytics.json): the site sends what it says, its definitions fit
GA4's limits, and tools/ga_setup.py registers what is missing in a property (against a fake Admin API)."""
import json
import os
import re
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = json.loads((ROOT / "data/analytics.json").read_text("utf-8"))
JS = "\n".join((ROOT / "src/js" / f).read_text("utf-8") for f in os.listdir(ROOT / "src/js"))


class PlanTest(unittest.TestCase):
    def test_every_event_of_the_plan_is_sent(self):
        for name in PLAN["events"]:
            if name == "page_view":
                continue
            self.assertRegex(JS, rf'["\']{name}["\']', f"{name} is in the plan but no script sends it")

    def test_every_parameter_of_the_plan_is_sent(self):
        for d in PLAN["dimensions"] + PLAN["metrics"]:
            self.assertRegex(JS, rf"\b{d['parameter']}\b", f"{d['parameter']} is registered but never sent")

    def test_within_ga4_limits(self):
        event = [d for d in PLAN["dimensions"] if d["scope"] == "EVENT"]
        user = [d for d in PLAN["dimensions"] if d["scope"] == "USER"]
        self.assertLessEqual(len(event), 50)
        self.assertLessEqual(len(user), 25)
        self.assertLessEqual(len(PLAN["metrics"]), 50)
        for d in PLAN["dimensions"] + PLAN["metrics"]:
            self.assertRegex(d["parameter"], r"^[a-z][a-z0-9_]{0,39}$")
            self.assertLessEqual(len(d["name"]), 82)
        for k in PLAN["keyEvents"]:
            self.assertIn(k, PLAN["events"])

    def test_murray_questions_never_go_to_analytics(self):
        murray = (ROOT / "src/js/murray.js").read_text("utf-8")
        for call in re.findall(r"PCM\.(?:ga|track)\(([^;]*)\);", murray):
            self.assertNotRegex(call, r"\bq\b|content|text", call)


class FakeAdmin(BaseHTTPRequestHandler):
    created: list = []
    impersonated: list = []

    def log_message(self, *a):
        pass

    def reply(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        assert self.headers["Authorization"] == "Bearer tok"
        path = self.path.split("?")[0]
        if path.endswith("/customDimensions"):
            return self.reply({"customDimensions": [{"parameterName": "room", "scope": "EVENT"}]})
        if path.endswith("/customMetrics"):
            return self.reply({"customMetrics": []})
        return self.reply({"keyEvents": [{"eventName": "game_start"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith(":generateAccessToken"):
            assert self.headers["Authorization"] == "Bearer usertok" and body["scope"] == ["https://www.googleapis.com/auth/analytics.edit"]
            FakeAdmin.impersonated.append(self.path)
            return self.reply({"accessToken": "tok", "expireTime": "2030-01-01T00:00:00Z"})
        assert self.headers["Authorization"] == "Bearer tok"
        FakeAdmin.created.append((self.path.rsplit("/", 1)[1], body))
        self.reply(body)

    do_PATCH = do_POST


class SetupToolTest(unittest.TestCase):
    def test_creates_only_what_is_missing(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeAdmin)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = dict(os.environ, PCM_GA_ADMIN_API=f"http://127.0.0.1:{srv.server_address[1]}/v1beta", GA_TOKEN="tok")
        try:
            dry = subprocess.run([sys.executable, str(ROOT / "tools/ga_setup.py"), "--property", "123456789"], env=env, capture_output=True, text=True)
            self.assertIn("would create", dry.stdout)
            self.assertEqual(FakeAdmin.created, [], "a dry run changes nothing")
            subprocess.run([sys.executable, str(ROOT / "tools/ga_setup.py"), "--property", "123456789", "--apply", "--retention"],
                           env=env, capture_output=True, text=True, check=True)
        finally:
            srv.shutdown()
        kinds = [k for k, _ in FakeAdmin.created]
        params = {b.get("parameterName") for k, b in FakeAdmin.created if k == "customDimensions"}
        self.assertNotIn("room", params, "already there: left alone")
        self.assertEqual(kinds.count("customDimensions"), len(PLAN["dimensions"]) - 1)
        self.assertEqual(kinds.count("customMetrics"), len(PLAN["metrics"]))
        self.assertEqual(sorted(b["eventName"] for k, b in FakeAdmin.created if k == "keyEvents"), sorted(set(PLAN["keyEvents"]) - {"game_start"}))
        self.assertTrue(any(k.startswith("dataRetentionSettings") for k in kinds))

    def test_service_account_impersonation(self):
        FakeAdmin.created.clear()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeAdmin)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        env = dict(os.environ, PCM_GA_ADMIN_API=base + "/v1beta", PCM_IAM_API=base + "/v1")
        env.pop("GA_TOKEN", None)
        try:
            r = subprocess.run([sys.executable, str(ROOT / "tools/ga_setup.py"), "--property", "123456789", "--token", "usertok",
                                "--service-account", "ga@p.iam.gserviceaccount.com"], env=env, capture_output=True, text=True)
        finally:
            srv.shutdown()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would create", r.stdout)
        self.assertEqual(FakeAdmin.impersonated, ["/v1/projects/-/serviceAccounts/ga@p.iam.gserviceaccount.com:generateAccessToken"])

    def test_property_number_not_measurement_id(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools/ga_setup.py"), "--property", "G-ABC123"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("property NUMBER", r.stderr)


if __name__ == "__main__":
    unittest.main()
