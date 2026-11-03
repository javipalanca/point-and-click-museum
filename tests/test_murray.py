"""Tests for Murray's chat service (server/murray.py, server/knowledge.py).
The language model is a fake OpenAI-compatible server on localhost: no network, no API keys."""
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
for k in [k for k in os.environ if k.startswith("MURRAY_LLM_")]:
    del os.environ[k]
import knowledge  # noqa: E402
import murray  # noqa: E402

SECRET = "sk-test-THIS-MUST-NEVER-LEAK"


class FakeLLM(BaseHTTPRequestHandler):
    """OpenAI-compatible /v1/chat/completions. Behaviour is set by FakeLLM.mode."""
    mode, requests = "tools", []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeLLM.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if FakeLLM.mode == "down":
            return self.reply(503, {"error": "overloaded"})
        if FakeLLM.mode == "no-tools" and "tools" in body:
            return self.reply(400, {"error": {"message": "tools are not supported"}})
        last = body["messages"][-1]
        tool_turn = "tools" in body and last["role"] == "user"
        tool = ("go_to", {"target": "game:loom"}) if FakeLLM.mode == "nav" else ("search_museum", {"query": "SCUMM"})
        if tool_turn:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": tool[0], "arguments": json.dumps(tool[1])}}]}
        elif FakeLLM.mode == "marker":
            msg = {"role": "assistant", "content": "¡Vamos a la vitrina de LucasArts! [[go:studio:lucasarts]]"}
        else:
            msg = {"role": "assistant", "content": "<think>The visitor asks about SCUMM.</think>\n¡SCUMM, mortal! El motor de Maniac Mansion."}
        if not body.get("stream") or FakeLLM.mode == "json":  # some servers ignore "stream" and answer with plain JSON
            return self.reply(200, {"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]})
        # Server-Sent Events, with tags and tool-call arguments split across chunks like real servers do
        if tool_turn:
            args = msg["tool_calls"][0]["function"]["arguments"]
            deltas = [{"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": tool[0], "arguments": args[:7]}}]},
                      {"tool_calls": [{"index": 0, "function": {"arguments": args[7:]}}]}]
        elif FakeLLM.mode == "marker":
            deltas = [{"content": p} for p in ("¡Vamos a la vitrina de LucasArts! [", "[go:studio:", "lucasarts]]")]
        else:
            deltas = [{"content": p} for p in ("<thi", "nk>The visitor asks about SCUMM.</th", "ink>\n¡SCUMM", ", mortal! El motor ", "de Maniac Mansion.")]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for d in deltas:
            self.wfile.write(b"data: " + json.dumps({"choices": [{"index": 0, "delta": d}]}).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")

    def reply(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class KnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = knowledge.Museum(ROOT / "data")

    def test_every_game_indexed_in_every_language(self):
        n = len(json.loads((ROOT / "data/timeline.json").read_text("utf-8"))["games"])
        for lang in knowledge.LANGS:
            self.assertEqual(sum(d.kind == "game" for d in self.m.docs[lang]), n)

    def test_search_finds_titles_engines_and_years(self):
        self.assertEqual(self.m.search("Grim Fandango", "en", 1)[0].id, "game:grim-fandango")
        self.assertIn("engine:scumm", [d.id for d in self.m.search("SCUMM", "es", 3)])
        self.assertTrue(all(d.year == 1993 for d in self.m.search("1993", "es", 3)))

    def test_list_games_filters(self):
        scumm = self.m.list_games("es", engine="SCUMM")
        self.assertTrue(scumm and all("SCUMM" in d.fields["engine"] for d in scumm))
        self.assertTrue(all(1990 <= d.year <= 1999 for d in self.m.list_games("es", 1990, 1999)))

    def test_tools_return_json(self):
        out, docs = knowledge.run_tool(self.m, "get_record", {"id": "loom"}, "fr")
        self.assertEqual(json.loads(out)["title"], "Loom")
        self.assertIn("error", json.loads(knowledge.run_tool(self.m, "nope", {}, "es")[0]))


class AnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.llm = ThreadingHTTPServer(("127.0.0.1", 0), FakeLLM)
        threading.Thread(target=cls.llm.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.llm.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.llm.shutdown()

    def setUp(self):
        FakeLLM.mode, FakeLLM.requests = "tools", []

    def tearDown(self):
        for k in ("MURRAY_LLM_BASE_URL", "MURRAY_LLM_MODEL", "MURRAY_LLM_API_KEY", "MURRAY_LLM_TOOLS"):
            os.environ.pop(k, None)

    def configure(self, **extra):
        os.environ.update({"MURRAY_LLM_BASE_URL": self.base + "/", "MURRAY_LLM_MODEL": "qwen3.8", "MURRAY_LLM_API_KEY": SECRET, **extra})

    def ask(self, q="¿Qué es SCUMM?", lang="es"):
        return murray.answer({"lang": lang, "messages": [{"role": "user", "content": q}]})

    def test_offline_mode_cites_records(self):
        r = self.ask()
        self.assertEqual(r["mode"], "offline")
        self.assertTrue(r["sources"])
        self.assertIn("SCUMM", r["reply"])

    def test_validation(self):
        for b in [{}, {"messages": []}, {"messages": [{"role": "system", "content": "x"}]},
                  {"messages": [{"role": "user", "content": 3}]}, {"messages": [{"role": "assistant", "content": "hola"}]}]:
            with self.assertRaises(ValueError):
                murray.validate(b)
        lang, h = murray.validate({"lang": "xx", "messages": [{"role": "user", "content": "a" * 5000}]})
        self.assertEqual((lang, len(h[0]["content"])), ("es", murray.MAX_CHARS))

    def test_tool_call_loop_rag_and_no_key_leak(self):
        self.configure()
        r = self.ask()
        self.assertEqual(r["mode"], "llm")
        self.assertEqual(r["reply"], "¡SCUMM, mortal! El motor de Maniac Mansion.")  # <think> removed
        self.assertTrue(r["sources"])
        first, second = FakeLLM.requests
        self.assertEqual(first["path"], "/v1/chat/completions")
        self.assertEqual(first["auth"], "Bearer " + SECRET)
        self.assertEqual(first["body"]["model"], "qwen3.8")
        self.assertEqual({t["function"]["name"] for t in first["body"]["tools"]}, {"search_museum", "get_record", "list_games", "go_to"})
        self.assertIn("[engine:scumm]", first["body"]["messages"][0]["content"])  # RAG records in the system prompt
        self.assertEqual(second["body"]["messages"][-1]["role"], "tool")
        self.assertNotIn(SECRET, json.dumps(r))

    def test_streamed_events(self):
        self.configure()
        events = list(murray.answer_events({"lang": "es", "messages": [{"role": "user", "content": "¿Qué es SCUMM?"}]}))
        deltas = [v for k, v in events if k == "delta"]
        self.assertGreater(len(deltas), 1)                                  # the reply really arrives in pieces
        self.assertEqual("".join(deltas), "¡SCUMM, mortal! El motor de Maniac Mansion.")
        self.assertEqual(events[-1][0], "done")
        self.assertTrue(FakeLLM.requests[0]["body"]["stream"])

    def test_server_that_ignores_stream(self):
        self.configure()
        FakeLLM.mode = "json"
        self.assertEqual(self.ask()["reply"], "¡SCUMM, mortal! El motor de Maniac Mansion.")

    def test_think_filter_split_tags(self):
        f, out = murray.ThinkFilter(), ""
        for piece in ("<", "think>secret", " stuff</", "think>", "\nHello <b>", "world</b> <thin", "k>x</think> end"):
            out += f.feed(piece)
        out += f.flush()
        self.assertEqual(out, "Hello <b>world</b>  end")

    def test_go_to_tool_navigates(self):
        self.configure()
        FakeLLM.mode = "nav"
        r = murray.answer({"lang": "es", "page": "studios", "messages": [{"role": "user", "content": "Llévame a Loom"}]})
        self.assertEqual(r["navigate"], {"page": "timeline", "hash": "loom", "title": "Loom"})
        self.assertIn("studios", FakeLLM.requests[0]["body"]["messages"][0]["content"])   # Murray knows where you are

    def test_marker_navigates_without_tools(self):
        self.configure(MURRAY_LLM_TOOLS="0")
        FakeLLM.mode = "marker"
        r = self.ask("Llévame a LucasArts")
        self.assertEqual(r["reply"], "¡Vamos a la vitrina de LucasArts!")             # the marker never reaches the visitor
        self.assertEqual(r["navigate"]["hash"], "studio-lucasarts")

    def test_no_navigation_by_default(self):
        self.configure()
        self.assertNotIn("navigate", self.ask())

    def test_go_marker_filter(self):
        g, out = murray.GoMarker(), ""
        for piece in ("Mira [esto] y ", "[[go:time", "line]] fin [[otra]]"):
            out += g.feed(piece)
        out += g.flush()
        self.assertEqual((out, g.target), ("Mira [esto] y  fin [[otra]]", "timeline"))

    def test_server_without_function_calling(self):
        self.configure()
        FakeLLM.mode = "no-tools"
        r = self.ask()
        self.assertEqual(r["mode"], "llm")
        self.assertNotIn("tools", FakeLLM.requests[-1]["body"])

    def test_tools_can_be_disabled(self):
        self.configure(MURRAY_LLM_TOOLS="0")
        self.ask()
        self.assertEqual(len(FakeLLM.requests), 1)
        self.assertNotIn("tools", FakeLLM.requests[0]["body"])

    def test_model_down_falls_back_offline(self):
        self.configure()
        FakeLLM.mode = "down"
        self.assertEqual(self.ask("Monkey Island", "en")["mode"], "offline")


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), murray.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(self.base + "/api/murray/chat", data=data, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_health(self):
        with urllib.request.urlopen(self.base + "/api/murray/health") as r:
            self.assertEqual(json.loads(r.read())["mode"], "offline")

    def test_chat_and_errors(self):
        code, r = self.post({"lang": "en", "messages": [{"role": "user", "content": "Loom"}]})
        self.assertEqual((code, r["sources"][0]["title"]), (200, "Loom"))
        self.assertEqual(self.post(b"{")[0], 400)
        self.assertEqual(self.post({"x": 1}, "text/plain")[0], 415)
        self.assertEqual(self.post(b"x" * (murray.MAX_BODY + 1))[0], 413)

    def test_sse_stream(self):
        req = urllib.request.Request(self.base + "/api/murray/chat", data=json.dumps(
            {"lang": "en", "stream": True, "messages": [{"role": "user", "content": "Loom"}]}).encode(),
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
        with urllib.request.urlopen(req) as r:
            self.assertIn("text/event-stream", r.headers["Content-Type"])
            events = [json.loads(l[5:]) for l in r.read().decode().splitlines() if l.startswith("data:")]
        self.assertTrue(events[0]["delta"])
        self.assertTrue(events[-1]["done"])
        self.assertEqual(events[-1]["sources"][0]["title"], "Loom")

    def test_rate_limit(self):
        old = murray.LIMITS.rate
        murray.LIMITS.rate, murray.LIMITS.hits = 2, {}
        try:
            self.assertEqual([self.post({"messages": [{"role": "user", "content": "Zork"}]})[0] for _ in range(3)], [200, 200, 429])
        finally:
            murray.LIMITS.rate, murray.LIMITS.hits = old, {}


if __name__ == "__main__":
    unittest.main()
