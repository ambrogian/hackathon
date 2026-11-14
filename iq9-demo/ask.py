"""Ask the plant: an operator question answered with tool calls. The model proposes, code decides.

Pattern from the hackathon tool-calling example: OpenAI-style tool schemas, validate the call envelope and
arguments, allowlist, write policy in code, a bounded number of turns, every step logged. If no local model server is
configured, a deterministic planner calls the same tools so the page still works (labelled 'rules, no LLM').
"""
import json
import os
import re
import time
import urllib.request
import uuid

import extrusion
import plant as plantmod
from iq9sim import llm

MAX_STEPS = 4
TOOLS = {
    "list_assets": {"description": "List every monitored asset with its current decision.",
                    "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    "read_asset": {"description": "Read one asset's latest measurements and decision.",
                   "parameters": {"type": "object", "properties": {"asset": {"type": "string", "enum": list(plantmod.ASSETS)}},
                                  "required": ["asset"], "additionalProperties": False}},
    "open_work_order": {"description": "Open a repair work order. Only allowed for an asset that is currently in FAULT.",
                        "parameters": {"type": "object", "properties": {
                            "asset": {"type": "string", "enum": list(plantmod.ASSETS)},
                            "reason": {"type": "string", "description": "one sentence citing measured values"},
                            "severity": {"type": "string", "enum": ["warning", "critical"]}},
                            "required": ["asset", "reason", "severity"], "additionalProperties": False}},
}
TOOLS["d1_assess"] = {"description": "Run the d1 decision model on one asset's thermal frame and measurements: fault probability, severity, category and a hotspot check on the picture. Takes a few seconds.",
                      "parameters": {"type": "object", "properties": {"asset": {"type": "string", "enum": [a for a, m in plantmod.ASSETS.items() if m["kind"] != "board"]}},
                                     "required": ["asset"], "additionalProperties": False}}
WRITE_TOOLS = {"open_work_order"}
SYSTEM = ("You are an inspection assistant for a plant. Use the tools to read measurements before answering. "
          "Answer in at most three short sentences using only numbers returned by tools. "
          "The plant has switchgear, a compressor, an edge board and a PC sheet extrusion line (Z1 dryer, Z3 screen pack, Z6 die, Z7 roll stack). Use d1_assess when the user asks to confirm or check a fault. Open a work order only when the user asks and the asset is in FAULT.")
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def openai_tools():
    return [{"type": "function", "function": {"name": n, **spec}} for n, spec in TOOLS.items()]


def validate(args, schema):
    errs = []
    if not isinstance(args, dict):
        return ["arguments must be an object"]
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in args:
            errs.append(f"missing required argument '{k}'")
    for k, v in args.items():
        if k not in props:
            errs.append(f"unexpected argument '{k}'")
            continue
        if props[k].get("type") == "string" and not isinstance(v, str):
            errs.append(f"'{k}' must be string")
        elif "enum" in props[k] and v not in props[k]["enum"]:
            errs.append(f"'{k}' must be one of {props[k]['enum']}")
    return errs


def brief(a):
    k = {x: a[x] for x in ("id", "name", "room", "label", "severity", "worst", "dt_c", "coherence", "acoustic", "impulsive", "load_pct",
                           "temp_c", "mode", "age", "d1", "headline", "part") if x in a and a[x] is not None}
    kb = extrusion.KB.get(a.get("fault") or "")
    if kb:
        k.update(zone=kb["zone"], effect=kb["why"], next=kb["steps"][0], resume_min=kb["resume_min"], lead=kb["lead"], defect=kb["defect"])
    return k


def run_tool(plant, name, raw_args):
    """-> (result, ok). Allowlist, schema, then policy for writes."""
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'. Allowed: {sorted(TOOLS)}"}, False
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except ValueError:
        return {"error": "arguments are not valid JSON (the model emitted a malformed call)"}, False
    errs = validate(args, TOOLS[name]["parameters"])
    if errs:
        return {"error": "; ".join(errs)}, False
    st = {a["id"]: a for a in plant.state()["assets"]}
    if name == "list_assets":
        return {"assets": [{k: v for k, v in brief(a).items() if k in ("id", "name", "label", "severity", "headline")} for a in st.values()]}, True
    if name == "read_asset":
        return brief(st[args["asset"]]), True
    if name == "d1_assess":
        plant._ask_d1 = getattr(plant, "_ask_d1", []) + [args["asset"]]
        if len(plant._ask_d1) > 2:
            return {"error": "d1 limit: at most two d1 checks per question"}, False
        try:
            r = plant.d1_run(args["asset"])
        except KeyError as e:
            return {"error": str(e)}, False
        if "error" in r:
            return {"error": r["error"]}, False
        return {"asset": args["asset"], "name": plantmod.ASSETS[args["asset"]]["name"], "p_fault": r["p_fault"], "severity": r["severity"], "category": r["category"],
                "category_confidence": r.get("category_confidence"), "severity_probs": r.get("severity_probs"), "category_probs": r.get("category_probs"),
                "p_hotspot_image": r["p_hotspot_image"], "ms_state": r["ms"]["state"], "ms_image": r["ms"]["image"]}, True
    return plant.request_order(args["asset"], args["reason"], args["severity"])  # write: policy inside


def _chat(base, messages, timeout=40, tools=True):
    body = {"model": llm.DEFAULT_MODEL, "messages": messages, **({"tools": openai_tools()} if tools else {}), "max_completion_tokens": 200,
            "compute": "npu", "enable_think": False, "chat_template_kwargs": {"enable_thinking": False}, "stream": False, "temperature": 0.1}
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    m = d["choices"][0]["message"]
    toks = (d.get("usage") or {}).get("completion_tokens", 0)
    calls = m.get("tool_calls") or []
    for c in calls:  # envelope check
        fn = c.get("function") if isinstance(c, dict) else None
        if not (isinstance(fn, dict) and isinstance(c.get("id"), str) and c.get("type") == "function" and isinstance(fn.get("name"), str)
                and isinstance(fn.get("arguments"), str)):
            raise ValueError("malformed tool-call envelope")
    if not isinstance(toks, int) or toks <= 0:
        raise ValueError("zero or missing completion tokens")
    return m, calls


def numbers_ok(text, results):
    pool = []

    def walk(v):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            pool.append(float(v))
        elif isinstance(v, dict):
            [walk(x) for x in v.values()]
        elif isinstance(v, list):
            [walk(x) for x in v]
        elif isinstance(v, str):
            pool.extend(float(t) for t in NUM.findall(v))  # numbers quoted in tool text (headlines, evidence)
    walk(results)
    bad = []
    for tok in NUM.findall(text):
        d = len(tok.split(".")[1]) if "." in tok else 0
        if not any(round(abs(v), d) == abs(float(tok)) or (int(abs(v) * 10 ** d) / 10 ** d) == abs(float(tok)) for v in pool) and not re.fullmatch(r"-?\d", tok):
            bad.append(tok)
    return bad


ALIASES = {"z1": ("dryer", "heater", "dew point", "resin", "drying"), "z3": ("screen", "filter", "pressure", "contamination", "speck"),
           "z6": ("die", "lane", "gauge", "thin"), "z7": ("roll", "coupling", "torque", "chatter", "marks")}


def rules_plan(plant, q):
    """No LLM: pick the same tools from keywords."""
    ql = q.lower()
    ids = [a for a, m in plantmod.ASSETS.items() if a in ql or m["name"].lower() in ql or m["name"].lower().replace("-", "") in ql]
    ids += [a for a, ws in ALIASES.items() if a not in ids and any(w in ql for w in ws)]
    want_order = any(w in ql for w in ("work order", "open", "ticket", "repair"))
    want_d1 = any(w in ql for w in ("d1", "second opinion", "confirm", "image", "picture", "verify", "hot spot", "hotspot"))
    if not ids:
        return [("list_assets", {})]
    plan = [("read_asset", {"asset": ids[0]})]
    if want_d1 and plantmod.ASSETS[ids[0]]["kind"] != "board":
        plan.append(("d1_assess", {"asset": ids[0]}))
    if want_order:
        plan.append(("open_work_order", {"asset": ids[0], "reason": "operator request; see measured values in the log", "severity": "critical"}))
    return plan


def render(steps):
    """One fixed plain-text layout for every answer, built in code from tool results only."""
    out = []
    for s in steps:
        r = s["result"]
        if s["tool"] == "list_assets" and s["ok"]:
            bad = [a for a in r["assets"] if a["label"] != "OK"]
            out.append(f"Needs attention ({len(bad)}):" if bad else "Nothing needs attention: every asset is OK.")
            out += [f"- {a['name']}: {a['label']}" + (f" - {a['headline']}" if a.get("headline") else "") for a in bad]
        elif s["tool"] == "read_asset" and s["ok"]:
            out.append(f"{r['name']}: {r['label']}" + (f" ({r['severity']})" if r["label"] == "FAULT" else ""))
            if r.get("headline"):
                out.append(f"  Signal: {r['headline']}")
            if r.get("part"):
                out += [f"  Likely part: {r['part']}", f"  Effect: {r['effect']}", f"  Next step: {r['next']}",
                        f"  Time to resume: about {r['resume_min']} min · warning lead: {r['lead']} · sheet defect: {r['defect']}"]
            elif r.get("temp_c") is not None:
                out.append(f"  SoC {r['temp_c']:.1f} °C, CPU load {r.get('load_pct', 0):.0f} %")
            elif r.get("dt_c") is not None and r["label"] != "OK":
                out.append(f"  {r.get('worst', 'Hottest point')} is {r['dt_c']:.1f} °C above the others" + (", crackle detected" if r.get("impulsive") else ", steady hiss detected" if r.get("acoustic") else ""))
        elif s["tool"] == "d1_assess":
            out.append((f"  d1 second opinion, {r.get('name', 'asset')}: fault {r['p_fault']:.2f} · severity {r['severity']} · category {r['category']}"
                        + (f" ({r['category_confidence']:.2f})" if r.get("category_confidence") is not None else "")
                        + (f" · hotspot in picture {r['p_hotspot_image']:.2f}" if r.get("p_hotspot_image") is not None else "")) if s["ok"]
                       else "  d1 not available: " + r["error"])
        elif s["tool"] == "open_work_order":
            out.append("  Work order: opened." if s["ok"] else "  Work order: not opened - " + r["error"].replace("refused by policy: ", ""))
        elif not s["ok"]:
            out.append("  Refused: " + r["error"])
    return "\n".join(out) or "No answer."


def clean_summary(text, results):
    """The model's optional one-sentence summary. Accepted only if it is plain, short and uses only numbers from tool results."""
    t = " ".join((text or "").split())
    if not t or len(t) > 260 or any(c in t for c in "<>*#|`_{}") or "tool_call" in t or t.count(".") > 3:
        return ""
    return "" if numbers_ok(t, results) else t


def ask(plant, q, llm_url=None, log_path=None):
    q = q.strip()[:300]
    t0 = time.perf_counter()
    steps, summary, mode, err = [], "", "rules, no LLM", None
    plant._ask_d1 = []
    if llm_url:
        mode = "LFM chose the tools"
        messages = [{"role": "system", "content": SYSTEM + f" [request:{uuid.uuid4().hex}]"}, {"role": "user", "content": q}]
        notools = False
        try:
            for _ in range(MAX_STEPS):
                m, calls = _chat(llm_url, messages, tools=not notools)
                if not calls:
                    summary = clean_summary(m.get("content"), [s["result"] for s in steps])
                    if (m.get("content") or "").strip() and not summary:
                        err = "model summary rejected (format or numbers not in tool results)"
                    break
                messages.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
                fresh = 0
                for c in calls:
                    name, raw = c["function"]["name"], c["function"]["arguments"]
                    prior = next((s for s in steps if s["tool"] == name and s["args"] == raw), None)
                    if prior:  # the model repeated a call: reuse the result, do not run or list it again
                        messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(prior["result"])})
                        continue
                    fresh += 1
                    res, ok = run_tool(plant, name, raw)
                    steps.append({"tool": name, "args": raw, "ok": ok, "result": res})
                    if not ok and name in WRITE_TOOLS:
                        notools = True  # a refused write ends tool use: no retry
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res)})
                if not fresh:
                    notools = True  # only repeats: let the model write its summary without tools
            else:
                err = f"model kept calling tools for {MAX_STEPS} turns; answer built from the {len(steps)} checked results"
        except Exception as e:  # network, timeout, bad envelope: fall back, never fail the page
            err = f"{type(e).__name__}: {e}"[:160]
        if not steps:
            mode = "rules, no LLM (LFM failed)" if err else "rules, no LLM (LFM chose no tool)"
            summary = ""
    if not steps:
        for name, args in rules_plan(plant, q):
            res, ok = run_tool(plant, name, json.dumps(args))
            steps.append({"tool": name, "args": json.dumps(args), "ok": ok, "result": res})
    answer = render(steps) + (f"\nSummary: {summary}" if summary else "")
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "q": q, "mode": mode, "steps": steps, "answer": answer, "error": err,
           "ms": round((time.perf_counter() - t0) * 1e3, 1)}
    if log_path:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
    return rec
