#!/usr/bin/env python3
"""Offline demo server (stdlib only). Serves ui/ and a small JSON API.
Usage: python3 -I server.py [--host 127.0.0.1] [--port 8088] [--decider rules|d1] [--llm http://127.0.0.1:8080]
Use --host 0.0.0.0 only on the demo LAN; there is no authentication."""
import argparse
import time
import json
import os
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iq9sim import engine, scenes  # noqa: E402
from validate import make_decider, run_validation  # noqa: E402
import ask as askmod  # noqa: E402
import plant as plantmod  # noqa: E402

UI = os.path.join(HERE, "ui")
CSP = "default-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".png": "image/png"}
STATE = {"decider": None, "llm": None, "job": {"state": "idle"}, "lock": threading.Lock()}


def start_validation(n, seed):
    with STATE["lock"]:
        if STATE["job"].get("state") == "running":
            return
        STATE["job"] = {"state": "running", "done": 0, "total": n}

    def work():
        try:
            res = run_validation(n, seed, STATE["decider"], lambda i: STATE["job"].__setitem__("done", i))
            res.pop("rows")
            STATE["job"] = {"state": "done", "done": n, "total": n, "result": res}
        except Exception as e:
            STATE["job"] = {"state": "error", "error": f"{type(e).__name__}: {e}"}
    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/scenes":
                return self._json({"scenes": scenes.SCENE_NAMES, "decider": STATE["decider"].name,
                                   "llm": bool(STATE["llm"])})
            if u.path == "/api/scene":
                seed = int(q.get("seed", 1))
                s = scenes.random_scene(seed) if q.get("name") == "random" else scenes.named_scene(q.get("name", ""), seed)
                return self._json(engine.run_scene(s, STATE["decider"], STATE["llm"]))
            if u.path == "/api/plant":
                return self._json(STATE["plant"].state())
            if u.path == "/api/log":
                return self._json(STATE["plant"].log(int(q.get("after", 0)), q.get("asset") or None, min(int(q.get("n", 80)), 500)))
            if u.path == "/api/asset":
                return self._json(STATE["plant"].asset_run(q.get("asset", "")))
            if u.path == "/api/incidents":
                return self._json({"incidents": STATE["plant"].incidents()})
            if u.path == "/api/incident":
                return self._json(STATE["plant"].incident(q.get("id", "")))
            if u.path == "/api/system":
                return self._json(STATE["plant"].system())
            if u.path == "/api/validate_start":
                start_validation(min(int(q.get("n", 100)), 1000), int(q.get("seed", 1000)))
                return self._json(STATE["job"])
            if u.path == "/api/validate_status":
                return self._json(STATE["job"])
        except KeyError:
            return self._json({"error": "unknown scene"}, 404)
        except ValueError:
            return self._json({"error": "bad parameter"}, 400)
        rel = "index.html" if u.path in ("", "/") else u.path.lstrip("/")
        path = os.path.realpath(os.path.join(UI, rel))
        if not path.startswith(UI + os.sep) or not os.path.isfile(path):
            return self._json({"error": "not found"}, 404)
        with open(path, "rb") as f:
            self._send(200, f.read(), TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))

    def do_POST(self):
        u = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._json({"error": "cross-origin"}, 403)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            if u.path == "/api/ask":
                q = str(body.get("q", ""))
                if not q.strip():
                    raise ValueError("empty question")
                pl = STATE["plant"]
                return self._json(askmod.ask(pl, q, STATE["llm"], os.path.join(HERE, "out", f"ask_log_{pl.stamp}.jsonl")))
            if u.path == "/api/d1":
                return self._json(STATE["plant"].d1_run(str(body.get("asset"))))
            if u.path == "/api/inject":
                STATE["plant"].inject(str(body.get("asset")), str(body.get("mode")))
                return self._json({"ok": True})
        except (KeyError, ValueError):
            return self._json({"error": "bad request"}, 400)
        return self._json({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--decider", default="rules", choices=["rules", "d1"])
    ap.add_argument("--d1", nargs="?", const="auto", default=None, help="enable d1-2B second opinion (needs torch + transformers==5.19 + local snapshot); optional snapshot path")
    ap.add_argument("--llm", default=None, help="base URL of an OpenAI-compatible server (geniex serve / llama-server)")
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between plant ticks")
    a = ap.parse_args()
    STATE["decider"], STATE["llm"] = make_decider(a.decider), a.llm
    d1 = None
    if a.d1:
        from iq9sim.d1svc import D1Service
        os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
        d1 = D1Service(None if a.d1 == "auto" else a.d1, os.path.join(HERE, "out", f"d1_log_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"))
    STATE["d1"] = d1
    STATE["plant"] = plantmod.Plant(STATE["decider"], a.llm, a.interval, d1=d1)
    STATE["plant"].start()
    print(f"serving http://{a.host}:{a.port}  decider={STATE['decider'].name}  llm={a.llm or 'off (template report)'}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
