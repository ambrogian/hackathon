"""Detect machine failures in line telemetry and point to the failing part.

Every rule runs on every telemetry file (a rule skips files that lack its signals),
so the scenario labels are never used for detection. Each alert is then joined with:
  kb/line.json      zone name, parts list, safety rules
  kb/defects.json   the sheet defects this failure causes (what to check, when fixed)
  failures.json     repair-and-restart playbook for the failure mode

Run:
  python3 scenarios/diagnose.py                 # all four scenarios, operator cards
  python3 scenarios/diagnose.py --json          # machine-readable alerts (for a UI)
  python3 scenarios/diagnose.py path/to/file.csv
"""
import csv
import json
import math
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LINE = json.loads((ROOT / "kb" / "line.json").read_text())
DEFECTS = {d["id"]: d for d in json.loads((ROOT / "kb" / "defects.json").read_text())}
FAILURES = json.loads((HERE / "failures.json").read_text())
CTX = FAILURES["line_context"]
PLAYBOOK = {s["failure_mode"]: s for s in FAILURES["scenarios"]}


# --- helpers ----------------------------------------------------------------
def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    cols = {k: [float(r[k]) if r[k] != "" else None for r in rows] for k in rows[0]}
    return cols


def first(t, cond, n=1):
    """Time of the first sample where cond(i) holds for n consecutive samples."""
    run = 0
    for i in range(len(t)):
        run = run + 1 if cond(i) else 0
        if run >= n:
            return t[i - n + 1]
    return None


def hms(s):
    if s is None:
        return "never"
    s = int(round(s))
    return f"+{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def baseline(x, n=10):
    return st.median(v for v in x[:n] if v is not None)


# --- rules ------------------------------------------------------------------
def rule_dryer(c):
    need = ["dryer_regen_heater_A", "dryer_regen_temp_C", "dryer_process_air_C", "dryer_dewpoint_C"]
    if not all(k in c for k in need):
        return None
    t, amp, regen, proc, dew = c["t_s"], *(c[k] for k in need)
    a0, r0, p0 = baseline(amp), baseline(regen), baseline(proc)
    t_alert = first(t, lambda i: amp[i] < 0.1 * a0, n=2)
    if t_alert is None:
        return None
    i = t.index(t_alert)
    if abs(proc[i] - p0) > 5:
        return None  # process air also off: a different failure, not in this playbook
    bub = c.get("vision_bubbles_per_m2")
    return {
        "failure_mode": "dryer_regen_heater_failure",
        "t_alert": t_alert,
        "evidence": [
            f"Regeneration heater current {a0:.1f} A -> {amp[i]:.1f} A",
            f"Regeneration air {r0:.0f} °C -> {regen[min(i + 10, len(t) - 1)]:.0f} °C 10 min later",
            f"Process air steady at {proc[i]:.0f} °C (process heater OK)",
            f"Dew point passes -35 °C at {hms(first(t, lambda j: dew[j] > -35, n=3))}",
            f"First bubbles on camera at {hms(first(t, lambda j: bub[j] > 1, n=2)) if bub else 'n/a'}",
        ],
        "lead_time_s": (first(t, lambda j: bub[j] > 1, n=2) - t_alert) if bub else None,
    }


def rule_screen(c):
    need = ["melt_p1_bar", "melt_p2_bar", "screw_rpm"]
    if not all(k in c for k in need):
        return None
    t, p1, p2, rpm = c["t_s"], c["melt_p1_bar"], c["melt_p2_bar"], c["screw_rpm"]
    dp = [a - b for a, b in zip(p1, p2)]

    def back(i, sec):
        j = i
        while j > 0 and t[j] > t[i] - sec:
            j -= 1
        return j

    def tear(i):
        j = back(i, 30)
        return (j < i and dp[i] < 0.65 * dp[j]
                and abs(rpm[i] - rpm[j]) < 0.02 * rpm[j])
    t_alert = first(t, tear, n=2)
    if t_alert is None:
        return None
    i = t.index(t_alert)
    before = st.mean(dp[back(i, 60):back(i, 30) + 1])
    after = st.mean(dp[-30:])
    gels = c.get("vision_gels_per_m2")
    t_gel = first(t, lambda j: gels[j] > 2, n=2) if gels else None
    return {
        "failure_mode": "screen_pack_rupture",
        "t_alert": t_alert,
        "evidence": [
            f"Pressure difference across screen {before:.0f} bar -> {after:.0f} bar within seconds",
            f"Screw speed steady at {rpm[i]:.1f} rpm, gear pump inlet steady at {p2[i]:.0f} bar",
            f"Gels on camera from {hms(t_gel)} ({(t_gel - t_alert):.0f} s after alert)" if t_gel else "No gels on camera yet",
        ],
        "lead_time_s": (t_gel - t_alert) if t_gel else None,
    }


def rule_die(c):
    zones = sorted(int(m.group(1)) for k in c if (m := re.fullmatch(r"die_D(\d+)_amp", k)))
    if not zones:
        return None
    t = c["t_s"]
    for k in zones:
        out, amp, temp = c[f"die_D{k}_out_pct"], c[f"die_D{k}_amp"], c[f"die_D{k}_temp_C"]
        t_alert = first(t, lambda i: out[i] >= 95 and amp[i] < 1.0, n=3)
        if t_alert is None:
            continue
        sp = baseline(temp)
        lane = c.get(f"thickness_lane{k}_mm")
        target = baseline(lane) if lane else None
        t_temp = first(t, lambda i: temp[i] < sp - 5, n=2)
        t_thick = first(t, lambda i: lane[i] < 0.98 * target, n=2) if lane else None
        w = CTX["die_zone_width_mm"]
        return {
            "failure_mode": "die_heater_open_circuit",
            "t_alert": t_alert,
            "location": f"die zone D{k}, sheet width {(k - 1) * w}-{k * w} mm",
            "evidence": [
                f"D{k} controller output {out[t.index(t_alert)]:.0f} % but heater current {amp[t.index(t_alert)]:.1f} A",
                f"D{k} temperature below setpoint by 5 °C at {hms(t_temp)}, {temp[-1]:.0f} °C by end of record",
                f"Lane {k} thickness out by 2 % at {hms(t_thick)}, now {lane[-1]:.2f} mm (target {target:.2f})" if lane else "No thickness gauge",
            ],
            "lead_time_s": (t_thick - t_alert) if t_thick else None,
        }
    return None


def autocorr_period(x, dt, lo_s, hi_s):
    m = st.mean(x)
    x = [v - m for v in x]
    var = sum(v * v for v in x) / len(x)
    if var == 0:
        return None, 0
    best = (None, 0.0)
    acs = {}
    for lag in range(int(lo_s / dt), int(hi_s / dt) + 1):
        n = len(x) - lag
        if n < 20:
            break
        acs[lag] = sum(x[i] * x[i + lag] for i in range(n)) / n / var
        if acs[lag] > best[1]:
            best = (lag, acs[lag])
    lag, ac = best
    if lag is None:
        return None, 0
    a, b, cc = acs.get(lag - 1, ac), ac, acs.get(lag + 1, ac)  # parabolic refine
    den = a - 2 * b + cc
    shift = 0.5 * (a - cc) / den if den else 0
    return (lag + shift) * dt, ac


def match_element(pitch_mm, tol=0.02):
    for name, d in CTX["rotating_elements_mm_diameter"].items():
        circ = math.pi * d
        if abs(pitch_mm - circ) / circ <= tol:
            return name, circ
    return None, None


def rule_chatter(c):
    rolls = sorted(int(m.group(1)) for k in c if (m := re.fullmatch(r"roll(\d)_torque_pct", k)))
    if not rolls or "line_speed_m_min" not in c:
        return None
    t, speed = c["t_s"], c["line_speed_m_min"]
    dt = t[1] - t[0]
    win = 130.0
    n = int(win / dt)
    for end in range(n, len(t), int(10 / dt)):
        v = st.mean(speed[end - n:end]) / 60 * 1000  # mm/s
        for r in rolls:
            x = c[f"roll{r}_torque_pct"][end - n:end]
            if max(x) - min(x) < 3:
                continue
            period, ac = autocorr_period(x, dt, 5, 120)
            if period is None or ac < 0.4:
                continue
            pitch = period * v
            name, circ = match_element(pitch)
            if name != f"roll {r} (Z7)":
                continue
            bear = [c[k] for k in c if k.startswith(f"roll{r}_bearing")]
            hot = any(max(b[:end]) > 70 or b[end - 1] - b[0] > 5 for b in bear)
            cam = [p for p in c.get("vision_mark_pitch_mm", []) if p is not None]
            cam_pitch = st.median(cam) if cam else None
            cam_name = match_element(cam_pitch)[0] if cam_pitch else None
            others = [f"roll {o}" for o in rolls if o != r]
            return {
                "failure_mode": "roll_bearing_failure" if hot else "roll_drive_coupling_wear",
                "t_alert": t[end - 1],
                "location": f"roll {r}",
                "evidence": [
                    f"Roll {r} torque repeats every {period:.1f} s (autocorrelation {ac:.2f})",
                    f"Period x line speed = {pitch:.0f} mm = roll {r} circumference {circ:.0f} mm",
                    f"No periodic torque on {', '.join(others)}",
                    f"Camera mark spacing {cam_pitch:.0f} mm -> matches {cam_name}" if cam_pitch else "Camera has not measured mark spacing yet",
                    "Roll bearing temperatures HIGH or rising -> bearing" if hot else "Roll bearing temperatures normal -> coupling / drive, not bearing",
                ],
                "lead_time_s": None,
            }
    return None


RULES = [rule_dryer, rule_screen, rule_die, rule_chatter]


# --- knowledge base join ----------------------------------------------------
def safety_for(zone):
    zn = int(zone[1:])
    out = []
    for s in LINE["safety"]:
        hit = any(int(a) <= zn <= int(b) for a, b in re.findall(r"Z(\d+)-Z(\d+)", s))
        hit |= zone in re.findall(r"Z\d+", s) and not re.search(rf"{zone}-Z\d+|Z\d+-{zone}", s)
        hit |= zone == "Z3" and "screen" in s.lower()
        if hit:
            out.append(s)
    out.append(LINE["safety"][-1])
    return out


def enrich(alert, source):
    pb = PLAYBOOK.get(alert["failure_mode"])
    if pb is None:
        alert.update({"source": source, "playbook": None})
        return alert
    zone = pb["zone"]
    z = LINE["zones"][zone]
    if pb["kb_part"] not in z["parts"]:
        raise SystemExit(f"{pb['id']}: part '{pb['kb_part']}' not in KB zone {zone}")
    alert.update({
        "source": source,
        "scenario": pb["id"],
        "title": pb["title"],
        "zone": zone,
        "zone_name": z["name"],
        "kb_part": pb["kb_part"],
        "failing_part": pb["failing_part"],
        "zone_typical": z["typical"],
        "ruled_out": pb["ruled_out"],
        "sheet_defects": [
            {"id": d, "name": DEFECTS[d]["name"], "severity": DEFECTS[d]["severity"],
             "confirm_fix": DEFECTS[d]["confirm_fix"]}
            for d in pb["expected_defects"] if d in DEFECTS
        ],
        "repair": pb["repair"],
        "safety": safety_for(zone),
    })
    return alert


def card(a):
    if a.get("playbook", 1) is None:
        return f"ALERT {a['failure_mode']} at {hms(a['t_alert'])} (no playbook yet)"
    r = a["repair"]
    L = [
        "=" * 78,
        f"[{a['scenario']}] MACHINE ALERT at {hms(a['t_alert'])}   {a['title']}",
        "=" * 78,
        f"WHERE:   {a['zone']} {a['zone_name']}  ->  part: {a['kb_part']}",
        f"FAILING: {a['failing_part']}" + (f"  [{a['location']}]" if a.get("location") else ""),
        "EVIDENCE:",
        *[f"  - {e}" for e in a["evidence"]],
        "RULED OUT:",
        *[f"  - {e}" for e in a["ruled_out"]],
    ]
    if a.get("lead_time_s"):
        L.append(f"WARNING AHEAD OF SCRAP: alert came {a['lead_time_s'] / 60:.1f} min before the sheet showed it")
    L.append("SHEET WILL SHOW: " + "; ".join(f"{d['name']} ({d['id']}, {d['severity']})" for d in a["sheet_defects"]))
    L.append("DO NOW:")
    L += [f"  {i}. {s}" for i, s in enumerate(r["do_now"], 1)]
    L.append(f"SPARES:  {', '.join(r['spares'])}")
    L.append(f"EST. TIME TO RESUME: about {r['estimated_repair_min']} min")
    L.append("RESUME WHEN:")
    L += [f"  - {s}" for s in r["resume_when"]]
    L.append(f"HOLD:    {r['quality_containment']}")
    L.append("SAFETY:")
    L += [f"  - {s}" for s in a["safety"]]
    return "\n".join(L)


def diagnose(path):
    c = load(path)
    alerts = [a for rule in RULES if (a := rule(c))]
    return [enrich(a, str(Path(path).relative_to(ROOT) if Path(path).is_relative_to(ROOT) else path))
            for a in alerts]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if args:
        files, expected = [Path(a).resolve() for a in args], None
    else:
        files = [HERE / s["telemetry"] for s in FAILURES["scenarios"]]
        expected = [s["failure_mode"] for s in FAILURES["scenarios"]]
    results, ok = [], True
    for i, f in enumerate(files):
        alerts = diagnose(f)
        results += alerts
        if expected:
            got = [a["failure_mode"] for a in alerts]
            if got != [expected[i]]:
                ok = False
                print(f"MISMATCH {f.name}: expected {expected[i]}, got {got}", file=sys.stderr)
        if not alerts and not as_json:
            print(f"{f.name}: no failure detected")
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for a in results:
            print(card(a), end="\n\n")
        if expected:
            print("self-check:", "all 4 scenarios diagnosed correctly" if ok else "MISMATCHES, see above")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
