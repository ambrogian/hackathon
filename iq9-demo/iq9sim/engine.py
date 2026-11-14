"""One call: scene -> simulated sensors -> measurements -> decision -> report, with ground truth alongside."""
import numpy as np

from . import analyze, report, scenes


def run_scene(scene, decider, llm_url=None, arrays=True):
    frame, mic = scenes.simulate(scene)
    meas, amap = analyze.measure(frame, mic, scene.load_pct)
    dec = decider.decide(meas)
    text, src = report.make_report(meas, dec, llm_url)
    truth = scenes.ground_truth(scene)
    out = {"scene": scenes.scene_info(scene), "measure": meas, "decision": dec, "report": text,
           "report_source": src, "truth": truth, "correct": dec["label"] == truth["label"]}
    if arrays:
        out["frame"] = np.round(frame, 2).tolist()
        out["acoustic_map"] = np.round(amap, 3).tolist()
        out["objects"] = [{"name": c.name, "cx": c.cx, "cy": c.cy, "w": c.w, "h": c.h} for c in scenes.OBJECTS]
    return out
