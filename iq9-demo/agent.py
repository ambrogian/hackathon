#!/usr/bin/env python3
"""Always-on inspection agent (offline, stdlib + numpy).

Loop: observe (thermal + acoustic sensors) -> decide (rule, or d1 on the CPU) -> act (allowlist)
      -> explain (local LFM, only when something is wrong) -> log (flushed JSONL) -> wait.

Code authorizes actions; the model only writes words. Every iteration is one JSON line (state, decision,
action record, explanation, per-stage timings, errors). Failures become logged data, never a crash.

  python3 -I agent.py --iterations 8 --interval 0                  # smoke run, rule gate, template text
  python3 -I agent.py --llm http://127.0.0.1:18181 --interval 5     # forever, LFM on the board
  python3 -I agent.py --decider d1 --iterations 20                  # d1 gate (needs torch + local snapshot)
"""
import argparse
import json
import os
import resource
import statistics
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from iq9sim import analyze, llm, report, scenes  # noqa: E402
from validate import make_decider  # noqa: E402

ALLOWED_ACTIONS = {"no_op", "flag_for_repair", "request_reinspection"}
ACTION_FOR = {"FAULT": "flag_for_repair", "OK": "no_op", "INCONCLUSIVE": "request_reinspection"}


def pick_scene(i, seed):
    """Deterministic walk: the four named scenes, then random ones. Real deployments replace this with a sensor read."""
    if i < len(scenes.SCENE_NAMES):
        return scenes.named_scene(scenes.SCENE_NAMES[i], seed)
    return scenes.random_scene(seed * 100003 + i)


def run_action(name, record, orders_path):
    """Only allowlisted actions run. Everything else is refused and logged. The only side effect here is a local work-order queue."""
    if name not in ALLOWED_ACTIONS:
        return {"name": name, "status": f"refused:{name}"}
    if name != "no_op":
        with open(orders_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            f.flush()
    return {"name": name, "status": "executed"}


def iteration(i, a, decider, orders_path, scene=None):
    t0 = time.perf_counter()
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "i": i, "error": None}
    stage = "observe"
    try:
        scene = scene if scene is not None else pick_scene(i, a.seed)
        frame, mic = scenes.simulate(scene)
        meas, _ = analyze.measure(frame, mic, scene.load_pct)
        t1 = time.perf_counter()
        stage = "decide"
        dec = decider.decide(meas)
        t2 = time.perf_counter()
        stage = "act"
        proposed = ACTION_FOR.get(dec["label"], "no_op")
        act = run_action(proposed, {"i": i, "label": dec["label"], "worst": meas["worst_lug"], "dt_c": meas["dt_c"]}, orders_path)
        t3 = time.perf_counter()
        stage = "explain"
        llm.LAST.clear()
        when = getattr(a, "llm_when", None) or (lambda lab: lab != "OK")
        text, src = report.make_report(meas, dec, a.llm if (a.llm and when(dec["label"])) else None)
        t4 = time.perf_counter()
        truth = scenes.ground_truth(scene)
        rec.update({
            "sim_truth": truth["label"], "correct": dec["label"] == truth["label"],
            "measure": {k: meas[k] for k in ("load_pct", "ambient_c", "worst_lug", "dt_c", "tier", "acoustic_detected",
                                              "impulsive", "coherence", "target", "colocated")},
            "decision": {"label": dec["label"], "p": dec["p"], "severity": dec["severity"], "decider": dec["decider"]},
            "action": act, "report": text, "report_source": src, "llm": dict(llm.LAST) or None,
            "ms": {"observe": round((t1 - t0) * 1e3, 1), "decide": round((t2 - t1) * 1e3, 1),
                   "act": round((t3 - t2) * 1e3, 2), "explain": round((t4 - t3) * 1e3, 1)}})
    except Exception as e:  # the loop must survive anything
        rec["error"] = f"{stage}: {type(e).__name__}: {e}"[:300]
    rec["ms_total"] = round((time.perf_counter() - t0) * 1e3, 1)
    return rec


def rss_mib():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)  # bytes on macOS, KiB on Linux


def summary(recs):
    ok = [r for r in recs if not r["error"]]
    med = lambda xs: round(statistics.median(xs), 1) if xs else None  # noqa: E731
    out = {"iterations": len(recs), "errors": len(recs) - len(ok),
           "accuracy_vs_sim_truth": round(sum(r["correct"] for r in ok) / len(ok), 3) if ok else None,
           "actions": {n: sum(r["action"]["name"] == n for r in ok) for n in sorted(ALLOWED_ACTIONS)},
           "report_source": {s: sum(r["report_source"].split(" ")[0] == s for r in ok) for s in ("llm", "template")},
           "median_ms": {k: med([r["ms"][k] for r in ok]) for k in ("observe", "decide", "explain")},
           "median_ms_total": med([r["ms_total"] for r in recs]),
           "peak_rss_mib": rss_mib()}
    llm_ms = [r["llm"]["ms"] for r in ok if r.get("llm") and r["llm"].get("ok")]
    out["llm_calls"] = sum(1 for r in ok if r.get("llm"))
    out["llm_median_ms"] = med(llm_ms)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--decider", default="rules", choices=["rules", "d1"])
    ap.add_argument("--llm", default=None, help="local OpenAI-compatible server, e.g. http://127.0.0.1:18181 (none: template text)")
    ap.add_argument("--iterations", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between iterations")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--log", default=None, help="JSONL path (default out/agent_log_<timestamp>.jsonl; never overwritten)")
    a = ap.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    log_path = a.log or os.path.join(HERE, "out", f"agent_log_{stamp}.jsonl")
    orders_path = os.path.join(HERE, "out", f"work_orders_{stamp}.jsonl")
    if os.path.exists(log_path) and os.path.getsize(log_path):
        raise SystemExit(f"{log_path} exists and is not empty; pick a new --log name (logs are never overwritten)")
    decider = make_decider(a.decider)
    print(f"agent: decider={decider.name} llm={a.llm or 'off'} log={log_path}", flush=True)
    recs = []
    try:
        with open(log_path, "a", encoding="utf-8") as log:
            i = 0
            while a.iterations == 0 or i < a.iterations:
                rec = iteration(i, a, decider, orders_path)
                log.write(json.dumps(rec) + "\n")
                log.flush()
                recs.append(rec)
                d = rec.get("decision") or {}
                print(f"[{i:3d}] {d.get('label', 'ERROR'):13s} {rec.get('action', {}).get('name', '-'):20s} "
                      f"{rec['ms_total']:7.1f} ms  {rec['error'] or rec.get('report_source', '')}", flush=True)
                i += 1
                if a.interval > 0 and (a.iterations == 0 or i < a.iterations):
                    time.sleep(a.interval)
    except KeyboardInterrupt:
        print("stopped", flush=True)
    s = summary(recs) if recs else {}
    print(json.dumps(s), flush=True)
    if recs:
        with open(log_path.replace(".jsonl", ".summary.json"), "x") as f:
            json.dump(s, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
