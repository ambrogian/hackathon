"""PC sheet extrusion line: four failure scenarios and their detection rules + knowledge lookup.

Own implementation. The failure types (dryer heater, screen pack, die-zone heater circuit, roll drive coupling) follow the
anchor repo's scenario list in idea only (github.com/ambrogian/hackathon, no license: nothing copied). Tag names, values,
rules and repair texts below are written for this demo and are illustrative; replace with the real line's setpoints.
"""
import math
import random
from collections import deque

LINE = {
    "z1": {"name": "Z1 Dryer", "zone": "Z1 Drying", "room": "Extrusion line · Z1 Drying", "kind": "line"},
    "z3": {"name": "Z3 Screen pack", "zone": "Z3 Filtration", "room": "Extrusion line · Z3 Filtration", "kind": "line"},
    "z6": {"name": "Z6 Die", "zone": "Z6 Die", "room": "Extrusion line · Z6 Die", "kind": "line"},
    "z7": {"name": "Z7 Roll stack", "zone": "Z7 Roll stack", "room": "Extrusion line · Z7 Roll stack", "kind": "line"},
}
LINE_MODES = {"z1": ("healthy", "heater_failed"), "z3": ("healthy", "screen_torn"), "z6": ("healthy", "die_heater_open"),
              "z7": ("healthy", "coupling_wear")}
LINE_TITLES = {"healthy": "Healthy", "heater_failed": "Dryer heater failed", "screen_torn": "Screen pack torn",
               "die_heater_open": "Die zone D5 heater open", "coupling_wear": "Roll 2 coupling wear"}
DEFAULT_LINE_MODES = {"z1": "healthy", "z3": "healthy", "z6": "die_heater_open", "z7": "coupling_wear"}
ROLL_PERIOD = 8  # samples per roll-2 revolution in the simulation (42 s revolution, one sample per 5 s of line time)

# Chart layout the UI draws: panels of (key, label, colour); limit = dashed reference value
PANELS = {
    "z1": [{"name": "REGEN HEATER CURRENT (A)", "lo": 0, "hi": 25, "keys": [("heater_a", "current", "#e8785d")], "limit": None},
           {"name": "DEW POINT (°C)", "lo": -60, "hi": 0, "keys": [("dew_point_c", "dew point", "#86b6f0")], "limit": -30}],
    "z3": [{"name": "PRESSURE ACROSS SCREEN (bar)", "lo": 0, "hi": 100, "keys": [("screen_dp_bar", "screen dP", "#e8785d")], "limit": 50},
           {"name": "SCREW SPEED (rpm)", "lo": 50, "hi": 70, "keys": [("screw_rpm", "speed", "#86b6f0")], "limit": None}],
    "z6": [{"name": "ZONE D5 CONTROLLER OUTPUT (%) AND CURRENT (A x 5)", "lo": 0, "hi": 110,
            "keys": [("d5_out_pct", "output", "#e8785d"), ("d5_a5", "current x5", "#86b6f0")], "limit": None},
           {"name": "SHEET GAUGE AT LANE 1172-1465 mm (% of target)", "lo": 90, "hi": 105, "keys": [("lane_gauge_pct", "gauge", "#d9b26a")], "limit": 96}],
    "z7": [{"name": "ROLL 2 TORQUE (N m)", "lo": 90, "hi": 150, "keys": [("roll2_torque_nm", "torque", "#e8785d")], "limit": None},
           {"name": "ROLL 2 BEARING VIBRATION (mm/s)", "lo": 0, "hi": 6, "keys": [("bearing_vib_mm_s", "vibration", "#86b6f0")], "limit": 4}],
}
# Operator knowledge, one entry per failure (own wording)
KB = {
    "heater_failed": {"zone": "Z1 Drying", "part": "Dryer regeneration heater (element or contactor)", "why": "Resin is no longer dried to spec; dew point climbs and moisture shows up later as bubbles and silver streaks in the sheet.",
                      "steps": ["Stop resin feed to the hopper only if dew point is above -30 °C", "Lock out the dryer, check the heater element and contactor", "Restart regeneration and confirm current returns to about 18 A"],
                      "lead": "about 2.5 h before bubbles appear", "resume_min": 45, "defect": "Bubbles, silver streaks"},
    "screen_torn": {"zone": "Z3 Filtration", "part": "Screen pack in the screen changer", "why": "Melt bypasses the filter, so contamination reaches the die: specks, gels and gauge streaks.",
                    "steps": ["Index the screen changer to a fresh pack", "Hold the line speed until pressure recovers", "Inspect the sheet for specks and rework or scrap affected length"],
                    "lead": "about 1 min before contaminated sheet", "resume_min": 5, "defect": "Black specks, gels, gauge streaks"},
    "die_heater_open": {"zone": "Z6 Die", "part": "Die zone D5 heater cartridge or its contactor", "why": "The zone cools while the controller demands full power, so melt thickens at that lane and the sheet thins there.",
                        "steps": ["Lock out zone D5, check cartridge resistance and the contactor", "Replace the failed part and bring the zone back to setpoint", "Re-check gauge across lane 1172-1465 mm before releasing the product"],
                        "lead": "about 6.5 min before a thin lane shows", "resume_min": 20, "defect": "Thin lane, gauge variation"},
    "coupling_wear": {"zone": "Z7 Roll stack", "part": "Roll 2 drive coupling", "why": "Torque repeats once per roll 2 revolution while bearings read normal, which points at the coupling and not the bearings; marks follow in the sheet.",
                      "steps": ["Slow the stack and inspect the coupling for play and wear", "Replace the coupling insert and re-check alignment", "Check roll marks along the sheet at one roll circumference spacing"],
                      "lead": "about 2 min before marks show", "resume_min": 60, "defect": "Repeating roll marks, chatter"},
}


class LineSim:
    """Per-asset telemetry generator plus detector. One call = one sample."""

    def __init__(self):
        self.torque = deque(maxlen=24)
        self.rng = random.Random(7)

    def sample(self, asset, mode, age):
        r = self.rng
        n = lambda s: r.gauss(0, s)  # noqa: E731
        f = max(0, age - 3)  # fault starts after 3 healthy samples
        bad = mode != "healthy"
        if asset == "z1":
            heater = 0.0 if bad and f > 0 else 18.0 + n(0.3)
            return {"heater_a": max(0.0, heater), "demand_pct": 100.0, "process_air_c": 120 + n(0.4),
                    "dew_point_c": -45 + (min(f, 40) * 0.9 if bad else 0) + n(0.4)}
        if asset == "z3":
            dp = 85 + n(1.0) if not (bad and f > 0) else max(23.0, 85 - 22 * f) + n(0.8)
            return {"screen_dp_bar": dp, "screw_rpm": 60 + n(0.25)}
        if asset == "z6":
            if bad and f > 0:
                return {"d5_out_pct": 100.0, "d5_a": max(0.0, 0.0 + abs(n(0.05))), "d5_a5": 0.0,
                        "lane_gauge_pct": 100 - (min(max(0, f - 6), 6) * 1.0) + n(0.2)}
            a = 11 + n(0.25)
            return {"d5_out_pct": 55 + n(1.5), "d5_a": a, "d5_a5": a * 5, "lane_gauge_pct": 100 + n(0.25)}
        amp = (1.0 + (min(f, 10) * 1.6 if bad else 0))
        t = 120 + amp * math.sin(2 * math.pi * age / ROLL_PERIOD) + n(0.6)
        return {"roll2_torque_nm": t, "bearing_vib_mm_s": 1.2 + abs(n(0.1))}

    def detect(self, asset, s):
        """-> (mode_label or None, headline, evidence list). Reads only the signals, never the injected mode."""
        if asset == "z1":
            if s["heater_a"] < 1.0 and s["demand_pct"] > 50:
                return "heater_failed", f"regeneration heater current {s['heater_a']:.1f} A while demanded at {s['demand_pct']:.0f} %", \
                    [f"heater current {s['heater_a']:.1f} A (normal about 18 A)", f"process air {s['process_air_c']:.0f} °C, dew point {s['dew_point_c']:.0f} °C"]
        elif asset == "z3":
            if s["screen_dp_bar"] < 50 and abs(s["screw_rpm"] - 60) < 3:
                return "screen_torn", f"pressure across screen {s['screen_dp_bar']:.0f} bar (normal about 85) at steady {s['screw_rpm']:.0f} rpm", \
                    [f"screen dP {s['screen_dp_bar']:.0f} bar", f"screw speed {s['screw_rpm']:.0f} rpm, steady"]
        elif asset == "z6":
            if s["d5_out_pct"] >= 95 and s["d5_a"] < 1.0:
                return "die_heater_open", f"zone D5 output {s['d5_out_pct']:.0f} % but current {s['d5_a']:.1f} A", \
                    [f"D5 output {s['d5_out_pct']:.0f} %, current {s['d5_a']:.1f} A", f"gauge at lane 1172-1465 mm {s['lane_gauge_pct']:.1f} % of target"]
        elif asset == "z7":
            self.torque.append(s["roll2_torque_nm"])
            w = list(self.torque)[-16:]
            if len(w) >= 16:
                m = sum(w) / len(w)
                x = [v - m for v in w]
                den = sum(v * v for v in x) or 1.0
                ac = sum(x[i] * x[i + ROLL_PERIOD] for i in range(len(x) - ROLL_PERIOD)) / den
                p2p = max(w) - min(w)
                if p2p > 12 and ac > 0.35 and s["bearing_vib_mm_s"] < 4:
                    return "coupling_wear", f"torque swings {p2p:.0f} N m once per roll 2 revolution while bearing vibration is normal ({s['bearing_vib_mm_s']:.1f} mm/s)", \
                        [f"torque peak-to-peak {p2p:.0f} N m", f"repeats every {ROLL_PERIOD} samples (one revolution), autocorrelation {ac:.2f}", f"bearing vibration {s['bearing_vib_mm_s']:.1f} mm/s, normal"]
        return None, "", []


def report_text(asset, mode, headline, evidence):
    k = KB[mode]
    return (f"FAULT. {k['zone']}: {headline}. Likely part: {k['part']}. {k['why']} "
            f"Next: {k['steps'][0]}. Estimated time to resume {k['resume_min']} min.")


NORMAL = {"z1": "normal: regeneration heater current about 18 A when demanded, dew point about -45 C; failure: current 0 A while demanded",
          "z3": "normal: pressure across the screen about 85 bar at 60 rpm; failure: pressure collapses below 50 bar while screw speed holds",
          "z6": "normal: zone D5 output about 55 percent with about 11 A; failure: output 100 percent but 0 A, lane gauge drops",
          "z7": "normal: roll 2 torque about 120 N m with small ripple, bearing vibration about 1.2 mm/s; failure: large torque swing repeating once per revolution with normal bearing vibration"}
