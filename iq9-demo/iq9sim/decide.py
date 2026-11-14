"""Decision step. RuleDecider = deterministic baseline (always available, the benchmark to beat).
D1Decider (d1.py) answers the same questions with the d1-2B model. Both return the same dict."""
import math

from . import rules


def _sig(z):
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def describe(m, label):
    """Severity, action and reason shared by every decider (derived from measurements only)."""
    load_ok = m["load_pct"] >= rules.MIN_LOAD_PCT
    sev = m["tier"] if load_ok else "none"
    if m["acoustic_detected"]:
        a = "critical" if (m["impulsive"] and m["colocated"]) else "probable"
        sev = max(sev, a, key=rules.SEVERITY.index)
    if label == "INCONCLUSIVE":
        return {"severity": "none", "action": f"Re-inspect with at least {rules.MIN_LOAD_PCT:.0f}% load",
                "reason": f"load {m['load_pct']:.0f}% is below the {rules.MIN_LOAD_PCT:.0f}% needed for a valid thermal reading"}
    if label == "FAULT":
        act = next((a for lo, k, a in rules.TIERS if k == sev), "Investigate")
        why = []
        if load_ok and m["dt_c"] >= rules.FAULT_MIN_DT:
            why.append(f"{m['worst_lug']} {m['dt_c']:.1f} C above similar lugs")
        if m["acoustic_detected"]:
            why.append(("crackle" if m["impulsive"] else "steady hiss") + f" at {m['target']}")
        return {"severity": sev, "action": act, "reason": "; ".join(why)}
    return {"severity": sev, "action": "No action; routine recheck" if sev == "none"
            else "No fault confirmed; recheck next quarter", "reason": "no fault evidence"}


class RuleDecider:
    name = "rules"

    def decide(self, m):
        load_ok = m["load_pct"] >= rules.MIN_LOAD_PCT
        p_th = _sig((m["dt_c"] - rules.FAULT_MIN_DT) / 1.2) if load_ok else 0.0
        p_ac = _sig((m["coherence"] - rules.COH_DETECT) / 0.01)
        p_fault = 1 - (1 - p_th) * (1 - p_ac)
        if p_fault >= 0.5:
            label, p = "FAULT", p_fault
        elif not load_ok:
            label, p = "INCONCLUSIVE", 1 - p_fault
        else:
            label, p = "OK", 1 - p_fault
        return {"label": label, "p": float(p), "decider": self.name, **describe(m, label)}
