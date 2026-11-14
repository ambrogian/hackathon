"""Work-order text: deterministic template, optional LLM rewrite, and a code check that every number
in the text matches a measured value (anything else is rejected and the template is used)."""
import re

from . import llm, rules

NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def evidence_kv(m):
    """Markdown-KV evidence block (also the d1 input)."""
    lines = [f"load_pct: {m['load_pct']:.0f}", f"ambient_c: {m['ambient_c']:.1f}"]
    for i, n in enumerate(("Lug A", "Lug B", "Lug C")):
        lines.append(f"{n}: max {m['lug_tmax_c'][i]:.1f} C, {m['lug_dt_c'][i]:+.1f} C vs the other two")
    lines += [f"hottest: {m['worst_lug']} ({m['dt_c']:.1f} C above similar lugs, tier {m['tier']})",
              f"acoustic_source_detected: {'yes' if m['acoustic_detected'] else 'no'}",
              f"coherence: {m['coherence']:.2f}",
              f"sound_character: {'impulsive crackle' if m['impulsive'] else 'steady hiss'}",
              f"sound_location: {m['target']} (az {m['az_deg']:.0f}, el {m['el_deg']:.0f} deg)",
              f"sound_at_hottest_lug: {'yes' if m['colocated'] else 'no'}"]
    return "\n".join(lines)


GUIDANCE = (f"Rules: temperature difference vs similar components: {rules.TIERS[2][0]:.0f}-{rules.TIERS[1][0]:.0f} C possible, "
            f"{rules.TIERS[1][0]:.0f}-{rules.TIERS[0][0]:.0f} C probable, over {rules.TIERS[0][0]:.0f} C critical. "
            f"Thermal readings are not valid below {rules.MIN_LOAD_PCT:.0f}% load. "
            "Crackle or hiss located on equipment indicates a partial discharge or an air leak.")


def template(m, d):
    if d["label"] == "INCONCLUSIVE":
        return (f"INCONCLUSIVE. Load is {m['load_pct']:.0f}%, below the {rules.MIN_LOAD_PCT:.0f}% needed for a valid thermal "
                f"reading ({m['worst_lug']} shows {m['dt_c']:.1f} C above similar lugs). {d['action']}.")
    if d["label"] == "OK":
        return (f"OK. All lugs are within {max(abs(x) for x in m['lug_dt_c']):.1f} C of each other at {m['load_pct']:.0f}% load "
                f"and no acoustic source was detected. {d['action']}.")
    parts = ["FAULT."]
    if m["load_pct"] >= rules.MIN_LOAD_PCT and m["dt_c"] >= rules.FAULT_MIN_DT:
        parts.append(f"{m['worst_lug']} runs {m['dt_c']:.1f} C above similar lugs ({m['tier_action']}).")
    if m["acoustic_detected"]:
        s = f"{'Impulsive crackle' if m['impulsive'] else 'Steady hiss'} detected at {m['target']} "
        s += f"(az {m['az_deg']:.0f}, el {m['el_deg']:.0f} deg, coherence {m['coherence']:.2f})"
        parts.append(s + (", at the hottest lug." if m["colocated"] else "."))
    parts.append(f"Action: {d['action']}.")
    return " ".join(parts)


def _flat(v, out):
    if isinstance(v, bool):
        return
    if isinstance(v, (int, float)):
        out.append(float(v))
    elif isinstance(v, (list, tuple)):
        for i in v:
            _flat(i, out)


def check_numbers(text, m):
    """Returns the list of numbers in text that match no measured value or rule constant."""
    vals = []
    for v in m.values():
        _flat(v, vals)
    vals += [lo for lo, _, _ in rules.TIERS] + [rules.MIN_LOAD_PCT, rules.FAULT_MIN_DT]
    vals += [abs(v) for v in vals]
    bad = []
    for tok in NUM.findall(text):
        d = len(tok.split(".")[1]) if "." in tok else 0
        if not any(round(v, d) == float(tok) for v in vals):
            bad.append(tok)
    return bad


def make_report(m, d, base_url=None):
    base = template(m, d)
    if not base_url:
        return base, "template"
    try:
        out = llm.chat(base_url,
                       "You write a two-sentence maintenance work order from inspection evidence. "
                       "Use only numbers that appear in the evidence. Do not add facts.",
                       f"Evidence:\n{evidence_kv(m)}\n\nDecision: {d['label']}. Action: {d['action']}.\n"
                       f"Draft to improve:\n{base}")
    except Exception as e:  # network, timeout, bad JSON: fall back, never fail the demo
        return base, f"template (llm error: {type(e).__name__})"
    bad = check_numbers(out, m)
    if bad or not out.strip() or len(out) > 700:
        return base, f"template (llm text rejected: numbers {bad[:3]})" if bad else "template (llm text rejected)"
    return out.strip(), "llm"
