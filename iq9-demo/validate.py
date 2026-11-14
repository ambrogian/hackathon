#!/usr/bin/env python3
"""Ground-truth sweep: N random scenes, accuracy, confusion matrix, calibration.
Usage: python3 -I validate.py [--n 300] [--seed 1000] [--decider rules|d1] [--llm URL]
Writes out/validate-<decider>-<timestamp>.{json,md} (never overwrites)."""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iq9sim import engine, scenes  # noqa: E402

LABELS = ["FAULT", "OK", "INCONCLUSIVE"]


def run_validation(n, seed, decider, progress=None):
    conf = {t: {p: 0 for p in LABELS} for t in LABELS}
    rows = []
    t0 = time.time()
    for i in range(n):
        r = engine.run_scene(scenes.random_scene(seed + i), decider, arrays=False)
        t, p = r["truth"]["label"], r["decision"]["label"]
        conf[t][p] += 1
        rows.append({"seed": seed + i, "truth": t, "pred": p, "p": r["decision"]["p"], "correct": t == p,
                     "dt_c": r["measure"]["dt_c"], "coherence": r["measure"]["coherence"],
                     "load_pct": r["measure"]["load_pct"]})
        if progress:
            progress(i + 1)
    conf_arr = np.array([r["p"] for r in rows])
    ok = np.array([r["correct"] for r in rows], float)
    bins, ece = [], 0.0
    edges = np.linspace(0, 1, 11)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf_arr >= lo) & ((conf_arr < hi) | (hi == 1.0))
        if m.any():
            bins.append({"lo": float(lo), "hi": float(hi), "n": int(m.sum()),
                         "mean_conf": float(conf_arr[m].mean()), "accuracy": float(ok[m].mean())})
            ece += m.mean() * abs(conf_arr[m].mean() - ok[m].mean())
    return {"decider": decider.name, "n": n, "seed": seed, "seconds": round(time.time() - t0, 1),
            "accuracy": float(ok.mean()), "ece": float(ece), "brier": float(np.mean((conf_arr - ok) ** 2)),
            "confusion": conf, "bins": bins, "errors": [r for r in rows if not r["correct"]][:20], "rows": rows}


def to_markdown(res):
    L = [f"# Validation: {res['decider']}, {res['n']} random scenes (seeds {res['seed']}..{res['seed'] + res['n'] - 1})", "",
         f"- accuracy: {res['accuracy']:.3f}", f"- ECE (calibration error, lower is better): {res['ece']:.3f}",
         f"- Brier score: {res['brier']:.3f}", f"- run time: {res['seconds']} s", "",
         "## Confusion (rows = truth, columns = predicted)", "", "| truth \\ pred | " + " | ".join(LABELS) + " |",
         "|---|" + "---|" * len(LABELS)]
    for t in LABELS:
        L.append(f"| {t} | " + " | ".join(str(res["confusion"][t][p]) for p in LABELS) + " |")
    L += ["", "## Reliability (does confidence match accuracy?)", "", "| confidence bin | n | mean confidence | accuracy |", "|---|---|---|---|"]
    for b in res["bins"]:
        L.append(f"| {b['lo']:.1f}-{b['hi']:.1f} | {b['n']} | {b['mean_conf']:.2f} | {b['accuracy']:.2f} |")
    L += ["", "## First errors", ""]
    for e in res["errors"][:10]:
        L.append(f"- seed {e['seed']}: truth {e['truth']}, predicted {e['pred']} (p {e['p']:.2f}), "
                 f"dT {e['dt_c']:.1f} C, coherence {e['coherence']:.3f}, load {e['load_pct']:.0f}%")
    return "\n".join(L) + "\n"


def make_decider(name):
    if name == "d1":
        from iq9sim.d1 import D1Decider
        return D1Decider()
    from iq9sim.decide import RuleDecider
    return RuleDecider()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--decider", default="rules", choices=["rules", "d1"])
    a = ap.parse_args()
    res = run_validation(a.n, a.seed, make_decider(a.decider))
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, "out"), exist_ok=True)
    stem = os.path.join(here, "out", f"validate-{a.decider}-{time.strftime('%Y%m%d_%H%M%S')}")
    with open(stem + ".json", "x") as f:
        json.dump(res, f)
    with open(stem + ".md", "x") as f:
        f.write(to_markdown(res))
    print(to_markdown(res))
    print("wrote", stem + ".md")
