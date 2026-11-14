"""Local LFM client (stdlib only) for `geniex serve` (127.0.0.1:18181) or llama-server.

Follows the hackathon rules (docs/runtimes.md "Handling unusable output"):
  - every request is capped (raw completion -> max_tokens)
  - the prompt carries a unique tag, so a repeated prompt is never served as a cached/empty reply
  - zero-token, empty or reasoning-only replies are retried once with a fresh tag, then returned as an error
  - raw ChatML with LFM3's reasoning block already closed (direct short answer)
Errors come back as data (`ok: False`); chat() raises only so report.make_report can fall back to the template.
"""
import json
import re
import time
import urllib.request
import uuid

DEFAULT_SERVER = "http://127.0.0.1:18181"
DEFAULT_MODEL = "LiquidAI/LFM3-1.7B-GGUF:Q4_0"
_THINK = re.compile(r"<think>.*?</think>", re.S)
LAST = {}  # stats of the most recent call, read by agent.py for the JSONL log


def _prompt(system, user, tag):
    return (f"<|startoftext|><|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user} [request:{tag}]<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")


def _once(base_url, prompt, model, max_tokens, timeout, compute):
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "stream": False, "temperature": 0.2}
    if compute:
        body["compute"] = compute
    req = urllib.request.Request(base_url.rstrip("/") + "/v1/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    ms = (time.perf_counter() - t0) * 1000
    c = d["choices"][0]
    text = _THINK.sub("", c.get("text") or "").strip()
    tokens = (d.get("usage") or {}).get("completion_tokens", 0)
    err = None
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
        err = "zero or missing completion tokens"
    elif not text:
        err = "empty answer (reasoning alone is not usable output)"
    return {"ok": err is None, "text": text, "tokens": tokens, "finish": c.get("finish_reason"),
            "ms": round(ms, 1), "error": err}


def complete(base_url, system, user, model=DEFAULT_MODEL, max_tokens=120, timeout=30, compute=None):
    """One capped, validated request; one retry with a fresh tag on unusable output. Never raises."""
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    res = {"ok": False, "text": "", "tokens": 0, "ms": 0.0, "error": "not called", "attempts": 0}
    for attempt in (1, 2):
        try:
            res = _once(base_url, _prompt(system, user, uuid.uuid4().hex), model, max_tokens, timeout, compute)
        except Exception as e:  # network, timeout, bad JSON: return as data
            res = {"ok": False, "text": "", "tokens": 0, "ms": 0.0, "error": f"{type(e).__name__}: {e}"[:200]}
        res["attempts"] = attempt
        if res["ok"]:
            break
    LAST.clear()
    LAST.update({k: res.get(k) for k in ("ok", "tokens", "ms", "attempts", "error", "finish")})
    return res


def chat(base_url, system, user, model=DEFAULT_MODEL, max_tokens=160, temperature=None, timeout=30):
    """Text or RuntimeError (report.make_report falls back to the template on any exception)."""
    r = complete(base_url, system, user, model=model, max_tokens=max_tokens, timeout=timeout)
    if not r["ok"]:
        raise RuntimeError(r["error"])
    return r["text"]
