"""Ask-the-plant tool calling: envelope/schema validation, allowlist, write policy, LLM loop against a mock server."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ask  # noqa: E402
import plant  # noqa: E402
from validate import make_decider  # noqa: E402

SCRIPT = []  # canned model replies, consumed in order


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["max_completion_tokens"] > 0
        out = SCRIPT.pop(0)
        b = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def log_message(self, *a):
        pass


def call(name, args, cid="call_1"):
    return {"choices": [{"message": {"content": "", "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {"completion_tokens": 12}}


def final(text):
    return {"choices": [{"message": {"content": text}}], "usage": {"completion_tokens": 20}}


class Ask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        cls.tmp = tempfile.mkdtemp()
        cls.p = plant.Plant(make_decider("rules"), None, 0.0, log_path=os.path.join(cls.tmp, "l.jsonl"))
        cls.p.orders_path = os.path.join(cls.tmp, "o.jsonl")
        with open(cls.p.log_path, "a") as log:
            for _ in range(30):
                for a in plant.ASSETS:
                    cls.p._step(a, log)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_allowlist_schema_policy(self):
        self.assertFalse(ask.run_tool(self.p, "rm_rf", "{}")[1])
        self.assertFalse(ask.run_tool(self.p, "read_asset", '{"asset":"../x"}')[1])
        self.assertFalse(ask.run_tool(self.p, "read_asset", "not json")[1])
        self.assertFalse(ask.run_tool(self.p, "read_asset", '{"asset":"sg1","extra":1}')[1])
        res, ok = ask.run_tool(self.p, "open_work_order", json.dumps({"asset": "sg1", "reason": "x", "severity": "critical"}))
        self.assertFalse(ok)
        self.assertIn("refused by policy", res["error"])  # SG-1 is healthy

    def test_llm_loop_with_policy_refusal(self):
        SCRIPT[:] = [call("open_work_order", {"asset": "sg1", "reason": "test", "severity": "critical"}),
                     final("I could not open it: SG-1 is OK.")]
        r = ask.ask(self.p, "Open a work order for SG-1", self.url)
        self.assertEqual(r["mode"], "LFM chose the tools")
        self.assertEqual([s["tool"] for s in r["steps"]], ["open_work_order"])
        self.assertFalse(r["steps"][0]["ok"])
        self.assertFalse(os.path.exists(self.p.orders_path) and "sg1" in open(self.p.orders_path).read())

    def test_answer_with_invented_number_falls_back(self):
        SCRIPT[:] = [call("read_asset", {"asset": "sg2"}), final("SG-2 is 99.7 C hot.")]
        r = ask.ask(self.p, "Why is SG-2 flagged?", self.url)
        self.assertIn("summary rejected", r["error"])
        self.assertNotIn("99.7", r["answer"])  # invented number never reaches the answer
        self.assertIn("SG-2: FAULT", r["answer"])  # the code-rendered facts still do

    def test_empty_reply_and_server_down_fall_back(self):
        SCRIPT[:] = [{"choices": [{"message": {"content": ""}}], "usage": {"completion_tokens": 5}}]
        self.assertTrue(ask.ask(self.p, "status of sg2", self.url)["mode"].startswith("rules"))
        self.assertTrue(ask.ask(self.p, "status of sg2", "http://127.0.0.1:9")["mode"].startswith("rules"))


if __name__ == "__main__":
    unittest.main()
