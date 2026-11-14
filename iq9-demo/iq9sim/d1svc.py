"""d1-2B service: named decisions in one forward pass (no output tokens), on the CPU, loaded once.

Two questions sets per assessment, as in the reference example:
  state  : the measurement block as text -> fault (noul), severity (score), category (choice)
  image  : the thermal frame rendered as a picture -> hotspot (noul)
d1 is a second opinion on the rule gate, run when an asset first leaves OK, or on demand. Loading is lazy in a
background thread; if torch/transformers or the snapshot are missing the status says so and everything else keeps working.
Only the code decides actions; d1 probabilities are logged and shown, never executed.
"""
import json
import os
import queue
import threading
import time

import numpy as np

from . import analyze, report, scenes

SNAPSHOTS = ("~/models/d1-2B", "~/Models/LiquidAI/d1-2B")
STATE_Q = {
    "fault": {"type": "noul", "instructions": "Do these inspection measurements show a fault that needs repair?"},
    "severity": {"type": "score", "instructions": "How severe is the condition?", "criteria": ["Low", "Moderate", "Critical"]},
    "category": {"type": "choice", "instructions": "Which category fits best?",
                 "criteria": {"thermal": "Overheating at a terminal", "acoustic": "Air leak or other acoustic source", "normal": "Nothing notable"}},
}
IMAGE_Q = {"hotspot": {"type": "noul", "instructions": "Is there a bright hot spot on one of the three terminals, much hotter than the other two?"}}
STOPS = np.array([[0, 0, 4], [87, 16, 110], [188, 55, 84], [249, 142, 9], [252, 255, 164]], dtype=float)


def thermal_image(frame, scale=8):
    """Render a thermal frame (deg C) as a labelled-free RGB picture with a fixed colour scale (20-60 C)."""
    from PIL import Image
    v = np.clip((np.asarray(frame, dtype=float) - 20.0) / 40.0, 0, 1) * (len(STOPS) - 1)
    i = np.minimum(v.astype(int), len(STOPS) - 2)
    f = (v - i)[..., None]
    rgb = (STOPS[i] * (1 - f) + STOPS[i + 1] * f).astype(np.uint8)
    return Image.fromarray(rgb).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.BICUBIC)


def _probs(x):
    """choice/score probabilities as a plain JSON value (dict name->p or list of p), rounded"""
    if isinstance(x, dict):
        return {str(k): round(float(v), 4) for k, v in x.items()}
    return [round(float(v), 4) for v in x]


class D1Service:
    def __init__(self, path=None, log_path=None):
        self.path = next((os.path.expanduser(p) for p in ([path] if path else SNAPSHOTS) if os.path.isdir(os.path.expanduser(p))), None)
        self.log_path = log_path
        self.model = None
        self.state = "idle"   # idle | loading | ready | error
        self.error = None
        self.load_s = None
        self.q = queue.Queue(maxsize=16)
        self.calls = 0
        self.lock = threading.Lock()
        threading.Thread(target=self._load, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def _load(self):
        self.state = "loading"
        t0 = time.perf_counter()
        try:
            if not self.path:
                raise FileNotFoundError("no d1 snapshot at " + " or ".join(SNAPSHOTS))
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            import torch
            from transformers import AutoModel
            self.model = AutoModel.from_pretrained(self.path, trust_remote_code=True, local_files_only=True,
                                                   dtype=torch.float32).to("cpu").eval()
            with torch.inference_mode():  # warm-up pays one-time setup
                self.model.system_one("{}", {"x": {"type": "noul", "instructions": "Is this empty?"}})
            self.load_s = round(time.perf_counter() - t0, 1)
            self.state = "ready"
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"[:200]
            self.state = "error"

    def status(self):
        return {"state": self.state, "error": self.error, "load_s": self.load_s, "path": self.path, "calls": self.calls,
                "queued": self.q.qsize(), "precision": "float32 on CPU"}

    def assess_text(self, text):
        """Blocking, no picture: the extrusion-line signals as text, with line-specific categories."""
        if self.state != "ready":
            return {"error": f"d1 {self.state}" + (f": {self.error}" if self.error else "")}
        import torch
        q = {**STATE_Q, "category": {"type": "choice", "instructions": "Which failure family fits best?",
                                      "criteria": {"heating": "A heater or dryer element has failed", "pressure": "Filter or pressure loss in the melt path",
                                                   "mechanical": "A drive, coupling or roll problem", "normal": "Nothing notable"}}}
        with self.lock, torch.inference_mode():
            t0 = time.perf_counter()
            a = self.model.system_one(text, q)
            t1 = time.perf_counter()
        sa = a["answers"]
        self.calls += 1
        return {"p_fault": round(float(sa["fault"]["noul"]), 4), "severity_level": round(float(sa["severity"]["score"]), 2),
                "severity": ["Low", "Moderate", "Critical"][min(2, int(round(float(sa["severity"]["score"]))))],
                "category": sa["category"]["choice"], "category_confidence": round(float(sa["category"]["confidence"]), 3),
                "category_probs": _probs(sa["category"]["probabilities"]), "severity_probs": _probs(sa["severity"]["probabilities"]),
                "p_hotspot_image": None, "ms": {"state": round((t1 - t0) * 1e3), "image": 0}, "output_tokens": int(a["usage"]["output_tokens"]),
                "input_tokens": {"state": int(a["usage"]["input_tokens"]), "image": 0}}

    def assess(self, scene):
        """Blocking. Returns the d1 verdict for one scene, or {'error': ...}."""
        if isinstance(scene, dict):
            return self.assess_text(scene["text"])
        if self.state != "ready":
            return {"error": f"d1 {self.state}" + (f": {self.error}" if self.error else "")}
        import torch
        frame, mic = scenes.simulate(scene)
        meas, _ = analyze.measure(frame, mic, scene.load_pct)
        text = report.GUIDANCE + "\n\n" + report.evidence_kv(meas)
        with self.lock, torch.inference_mode():
            t0 = time.perf_counter()
            a = self.model.system_one(text, STATE_Q)
            t1 = time.perf_counter()
            b = self.model.system_one(None, IMAGE_Q, media=[thermal_image(frame)])
            t2 = time.perf_counter()
        sa, sb = a["answers"], b["answers"]
        out = {"p_fault": round(float(sa["fault"]["noul"]), 4), "severity_level": round(float(sa["severity"]["score"]), 2),
               "severity": ["Low", "Moderate", "Critical"][min(2, int(round(float(sa["severity"]["score"]))))],
               "category": sa["category"]["choice"], "category_confidence": round(float(sa["category"]["confidence"]), 3),
               "category_probs": _probs(sa["category"]["probabilities"]), "severity_probs": _probs(sa["severity"]["probabilities"]),
               "p_hotspot_image": round(float(sb["hotspot"]["noul"]), 4),
               "ms": {"state": round((t1 - t0) * 1e3), "image": round((t2 - t1) * 1e3)},
               "output_tokens": int(a["usage"]["output_tokens"]) + int(b["usage"]["output_tokens"]),
               "input_tokens": {"state": int(a["usage"]["input_tokens"]), "image": int(b["usage"]["input_tokens"])}}
        self.calls += 1
        return out

    def submit(self, key, scene, done):
        """Non-blocking: queue one assessment; done(key, result) runs on the worker thread. Drops when the queue is full."""
        try:
            self.q.put_nowait((key, scene, done))
            return True
        except queue.Full:
            return False

    def _worker(self):
        while True:
            key, scene, done = self.q.get()
            while self.state in ("idle", "loading"):
                time.sleep(0.5)
            try:
                res = self.assess(scene)
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {e}"[:200]}
            res["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            if self.log_path:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"key": key, **res}) + "\n")
                    f.flush()
            done(key, res)
