"""d1-2B decider. Follows the d1-2B README (`model.system_one(text, questions)` -> answers[...]['noul'] = P(yes)).
UNTESTED until torch + transformers>=5.19 exist on the machine; the rule decider stays the fallback.
Heavy imports happen only when D1Decider is constructed."""
import os

from . import report
from .decide import describe


class D1Decider:
    name = "d1-2B"

    def __init__(self, path="~/Models/LiquidAI/d1-2B"):
        import torch
        from transformers import AutoModel
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = AutoModel.from_pretrained(os.path.expanduser(path), trust_remote_code=True,
                                               dtype=torch.float32 if dev == "cpu" else torch.bfloat16).to(dev)

    def decide(self, m):
        text = report.GUIDANCE + "\n\n" + report.evidence_kv(m)
        q = {"fault": {"type": "noul", "instructions": "Do these inspection measurements show a fault that needs repair?"},
             "unreliable": {"type": "noul", "instructions": "Is the evidence unreliable, so the equipment must be re-inspected under load?"}}
        a = self.model.system_one(text, q)["answers"]
        pf, pu = float(a["fault"]["noul"]), float(a["unreliable"]["noul"])
        if pf >= 0.5:
            label, p = "FAULT", pf
        elif pu >= 0.5:
            label, p = "INCONCLUSIVE", pu
        else:
            label, p = "OK", 1 - pf
        return {"label": label, "p": p, "decider": self.name, "p_fault": pf, "p_unreliable": pu, **describe(m, label)}
