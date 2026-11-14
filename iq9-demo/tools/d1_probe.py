"""Probe d1 on named + random scenes: latency and whether state/image answers separate fault from healthy. Prints JSONL + summary."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from iq9sim import d1svc, scenes  # noqa: E402

svc = d1svc.D1Service()
while svc.state in ("idle", "loading"):
    time.sleep(0.5)
print(json.dumps(svc.status()), flush=True)
rows = []
items = [(n, scenes.named_scene(n, 1)) for n in scenes.SCENE_NAMES] + [("rand%d" % i, scenes.random_scene(1000 + i)) for i in range(int(sys.argv[1]) if len(sys.argv) > 1 else 12)]
for name, sc in items:
    r = svc.assess(sc)
    r.update(name=name, truth=scenes.ground_truth(sc)["label"])
    rows.append(r)
    print(json.dumps(r), flush=True)
ok = [r for r in rows if "error" not in r]
for lab in ("OK", "FAULT", "INCONCLUSIVE"):
    g = [r for r in ok if r["truth"] == lab]
    if g:
        m = lambda f: sum(f(r) for r in g) / len(g)  # noqa: E731
        print(lab, len(g), "p_fault text %.2f vision %.2f fused %.2f" % (m(lambda r: r["p_fault"]), m(lambda r: r["vision"]["p_fault"]), m(lambda r: r["fused"]["p_fault"])),
              "severity-level text %.2f vision %.2f fused %.2f" % (m(lambda r: r["severity_level"]), m(lambda r: r["vision"]["severity_level"]), m(lambda r: r["fused"]["severity_level"])),
              "p_hotspot %.2f" % m(lambda r: r["p_hotspot_image"]),
              "ms state/image median", sorted(r["ms"]["state"] for r in g)[len(g) // 2], sorted(r["ms"]["image"] for r in g)[len(g) // 2], "fused", sorted(r["ms"]["fused"] for r in g)[len(g) // 2])
