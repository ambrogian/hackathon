"""d1 on the PC sheet extrusion line: each failure scenario and its healthy twin, text / image (signal chart) / fused.
Builds the d1 inputs exactly as plant.py does. Prints a table and JSONL rows. Simulated signals, small sample."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import extrusion  # noqa: E402
from iq9sim import d1svc  # noqa: E402

svc = d1svc.D1Service()
while svc.state in ("idle", "loading"):
    time.sleep(0.5)
print(json.dumps(svc.status()), flush=True)
FAULT_MODE = {"z1": "heater_failed", "z3": "screen_torn", "z6": "die_heater_open", "z7": "coupling_wear"}
rows = []
for asset in extrusion.LINE:
    for mode in ("healthy", FAULT_MODE[asset]):
        sim, hist, last = extrusion.LineSim(), [], None
        for age in range(1, 31):
            s = sim.sample(asset, mode, age)
            sim.detect(asset, s)
            hist.append({**s, "d5_a5": s.get("d5_a", 0) * 5})
            last = s
        body = "\n".join(f"{k}: {round(v, 2)}" for k, v in last.items())
        fm, headline, _ = sim.detect(asset, last)
        text = f"PC sheet extrusion line, {extrusion.LINE[asset]['zone']}\n{extrusion.NORMAL[asset]}\n{body}\nrule evidence: {headline or 'none'}"
        r = svc.assess({"text": text, "history": hist[-40:], "panels": extrusion.PANELS[asset]})
        r.update(asset=asset, mode=mode, rule="FAULT" if fm else "OK")
        rows.append(r)
        print(json.dumps(r), flush=True)
print("\nzone  scenario            rule   fault text/image/fused   severity text/image/fused   family")
for r in rows:
    print(f"{r['asset']:4}  {r['mode']:18}  {r['rule']:5}  {r['p_fault']:.2f} / {r['vision']['p_fault']:.2f} / {r['fused']['p_fault']:.2f}"
          f"        {r['severity']} / {r['vision']['severity']} / {r['fused']['severity']}   {r['category']} ({r['category_confidence']:.2f})")
