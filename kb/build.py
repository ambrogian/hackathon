"""Validate the knowledge base and render it.

Outputs:
  docs/KNOWLEDGE_BASE.md - readable version for people (review, demo slides)
  kb/context.txt     - compact version to put in the local model's prompt

Run: python3 kb/build.py
"""
import json
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent
ROOT = KB.parent

line = json.loads((KB / "line.json").read_text())
defects = json.loads((KB / "defects.json").read_text())
zones = line["zones"]
ids = [d["id"] for d in defects]

# --- validation -------------------------------------------------------------
errors = []
if len(ids) != len(set(ids)):
    errors.append("duplicate defect ids")
for d in defects:
    for z in d["origin_zones"]:
        if z not in zones:
            errors.append(f"{d['id']}: unknown zone {z}")
for pattern, refs in line["triage_by_pattern"].items():
    for r in refs:
        if r not in ids:
            errors.append(f"triage '{pattern}': unknown defect {r}")
untriaged = set(ids) - {r for refs in line["triage_by_pattern"].values() for r in refs}
if untriaged:
    errors.append(f"defects missing from triage: {sorted(untriaged)}")
if errors:
    sys.exit("KB errors:\n  " + "\n  ".join(errors))


def zone_label(z):
    return f"{z} {zones[z]['name']}"


# --- KNOWLEDGE_BASE.md --------------------------------------------------------
md = [f"# {line['line']}: troubleshooting knowledge base", "",
      f"> {line['note']}", "",
      "## Line layout", "",
      "| Zone | Section | Parts | Typical |", "|---|---|---|---|"]
for z in line["flow"]:
    v = zones[z]
    md.append(f"| {z} | {v['name']} | {', '.join(v['parts'])} | {v['typical']} |")
md += ["", f"Diagram: {line['diagram']}", "", "## Safety", ""]
md += [f"- {s}" for s in line["safety"]]
md += ["", "## Triage by what you see", "", "| Pattern | Check these defects |", "|---|---|"]
for p, refs in line["triage_by_pattern"].items():
    md.append(f"| {p} | {', '.join(refs)} |")
md += ["", "## Defects", ""]
for d in defects:
    md += [f"### {d['name']} (`{d['id']}`)", "",
           f"**What it looks like:** {d['visual_signature']}", "",
           f"**Where it starts:** {', '.join(zone_label(z) for z in d['origin_zones'])}  ",
           f"**Severity:** {d['severity']}", "",
           "**Likely causes (most likely first):**", ""]
    md += [f"- {c}" for c in d["likely_causes"]]
    md += ["", "**Operator steps:**", ""]
    md += [f"{i}. {s}" for i, s in enumerate(d["operator_actions"], 1)]
    md += ["", f"**Fixed when:** {d['confirm_fix']}  ", f"**Escalate if:** {d['escalate_if']}"]
    if d["confusable_with"]:
        md.append(f"**Don't confuse with:** {'; '.join(d['confusable_with'])}")
    md.append("")
(ROOT / "docs" / "KNOWLEDGE_BASE.md").write_text("\n".join(md))

# --- context.txt (compact, for the model prompt) ----------------------------
ctx = [f"LINE: {line['line']}", "ZONES (in flow order):"]
ctx += [f"{z}: {zones[z]['name']} - {', '.join(zones[z]['parts'])}" for z in line["flow"]]
ctx += ["SAFETY:"] + [f"- {s}" for s in line["safety"]]
ctx += ["TRIAGE BY VISUAL PATTERN:"]
ctx += [f"- {p} -> {', '.join(r)}" for p, r in line["triage_by_pattern"].items()]
ctx.append("DEFECTS:")
for d in defects:
    ctx += [f"[{d['id']}] {d['name']}",
            f" looks like: {d['visual_signature']}",
            f" zones: {', '.join(zone_label(z) for z in d['origin_zones'])}",
            f" causes: {' | '.join(d['likely_causes'])}",
            " steps: " + " ".join(f"({i}) {s}" for i, s in enumerate(d["operator_actions"], 1)),
            f" fixed when: {d['confirm_fix']}",
            f" escalate: {d['escalate_if']}"]
(KB / "context.txt").write_text("\n".join(ctx) + "\n")

# --- showcase page (data injected from the KB) ------------------------------
tpl = ROOT / "showcase" / "template.html"
if tpl.exists():
    data = json.dumps({"line": line, "defects": defects}, ensure_ascii=False)
    html = tpl.read_text().replace("/*__KB__*/null", data)
    (ROOT / "showcase" / "index.html").write_text(html)

words = len((KB / "context.txt").read_text().split())
print(f"OK: {len(defects)} defects, {len(zones)} zones. context.txt ~{words} words (~{int(words * 1.4)} tokens)")
