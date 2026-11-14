"""Agent loop + local LLM client guards, against a mock /v1/completions server (no network, no model)."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agent  # noqa: E402
from iq9sim import llm  # noqa: E402

CALLS = []
MODE = {"v": "good"}


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CALLS.append(body)
        n = len(CALLS)
        if MODE["v"] == "empty_then_good" and n % 2 == 1:
            out = {"choices": [{"text": "<think>x</think>", "finish_reason": "length"}], "usage": {"completion_tokens": 9}}
        elif MODE["v"] == "zero":
            out = {"choices": [{"text": "", "finish_reason": "stop"}], "usage": {"completion_tokens": 0}}
        else:
            out = {"choices": [{"text": "FAULT. Lug B runs hot.", "finish_reason": "stop"}], "usage": {"completion_tokens": 7}}
        b = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


class Agent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        CALLS.clear()

    def test_cap_tag_and_retry(self):
        MODE["v"] = "empty_then_good"
        r = llm.complete(self.url, "sys", "user", max_tokens=50)
        self.assertTrue(r["ok"])
        self.assertEqual(r["attempts"], 2)
        self.assertTrue(all(c["max_tokens"] == 50 for c in CALLS))
        self.assertNotEqual(CALLS[0]["prompt"], CALLS[1]["prompt"])  # fresh unique tag on retry
        self.assertIn("<think>\n\n</think>", CALLS[0]["prompt"])

    def test_persistent_failure_is_data(self):
        MODE["v"] = "zero"
        r = llm.complete(self.url, "s", "u")
        self.assertFalse(r["ok"])
        self.assertEqual(len(CALLS), 2)  # exactly one retry
        with self.assertRaises(RuntimeError):
            llm.chat(self.url, "s", "u")

    def test_cap_must_be_positive(self):
        with self.assertRaises(ValueError):
            llm.complete(self.url, "s", "u", max_tokens=0)

    def test_unreachable_server_never_raises(self):
        r = llm.complete("http://127.0.0.1:9", "s", "u", timeout=1)
        self.assertFalse(r["ok"])

    def test_allowlist_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "o.jsonl")
            self.assertEqual(agent.run_action("open_breaker", {}, p)["status"], "refused:open_breaker")
            self.assertFalse(os.path.exists(p))
            self.assertEqual(agent.run_action("flag_for_repair", {"i": 1}, p)["status"], "executed")
            self.assertTrue(os.path.getsize(p) > 0)

    def test_loop_logs_every_iteration_and_survives_errors(self):
        MODE["v"] = "good"
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "log.jsonl")
            argv = sys.argv
            sys.argv = ["agent", "--iterations", "6", "--interval", "0", "--llm", self.url, "--log", log]
            try:
                agent.main()
            finally:
                sys.argv = argv
            rows = [json.loads(x) for x in open(log)]
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(r["error"] is None and r["action"]["status"] == "executed" for r in rows))
            self.assertTrue(any(r["report_source"] == "llm" or r["report_source"].startswith("template") for r in rows))
            for r in rows:  # OK scenes never call the model
                if r["decision"]["label"] == "OK":
                    self.assertIsNone(r["llm"])
            # a broken sensor read becomes a logged error, not a crash
            class Boom:
                name = "boom"
                def decide(self, m): raise RuntimeError("x")
            a = type("A", (), {"seed": 1, "llm": None})()
            rec = agent.iteration(0, a, Boom(), os.path.join(d, "o.jsonl"))
            self.assertTrue(rec["error"].startswith("decide:"))


if __name__ == "__main__":
    unittest.main()
