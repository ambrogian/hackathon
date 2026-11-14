"""Build the video demo page from the real detector output.

Runs scenarios/diagnose.py on the four telemetry files, takes a downsampled slice of
the key signal for each, and writes demo/index.html from demo/template.html.
The video plays next to it as demo/line.mp4.

Run: python3 demo/build_demo.py
"""
import json
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parent
sys.path.insert(0, str(ROOT / "scenarios"))
import diagnose as D  # noqa: E402

# Where the video freezes for each scenario, and what to draw on the frozen frame.
# Box = [left, top, width, height] as fractions of the video frame.
STOPS = {
    "F1": {"t": 0.25, "boxes": [{"r": [0.41, 0.06, 0.12, 0.24], "label": "Z1 drying hopper / dryer"}]},
    "F2": {"t": 1.00, "boxes": [{"r": [0.28, 0.29, 0.11, 0.41], "label": "Z3 screen changer"}]},
    "F4": {"t": 2.40, "boxes": [{"r": [0.31, 0.44, 0.30, 0.22], "label": "Z7 roll 2"}]},
    "F3": {"t": 6.00, "boxes": [
        {"r": [0.44, 0.18, 0.50, 0.18], "label": "Thickness gauge: lane 5 thin"},
        {"r": [0.44, 0.56, 0.34, 0.12], "label": "1172-1465 mm", "kind": "lane"},
    ]},
}

# The one signal shown in each alert card: column, x window (s), unit, markers.
CHARTS = {
    "F1": {"col": "dryer_dewpoint_C", "name": "Dryer dew point", "unit": "°C", "x": [0, 21600], "every": 2,
           "limit": {"y": -40, "label": "limit -40 °C"}, "xunit": "h"},
    "F2": {"col": "dp", "name": "Pressure difference across screen", "unit": "bar", "x": [240, 480], "every": 2,
           "xunit": "s"},
    "F3": {"col": "thickness_lane5_mm", "name": "Thickness, lane 5", "unit": "mm", "x": [600, 3600], "every": 2,
           "limit": {"y": 3.92, "label": "tolerance 3.92 mm"}, "xunit": "min"},
    "F4": {"col": "roll2_torque_pct", "name": "Roll 2 drive torque", "unit": "%", "x": [20, 300], "every": 1,
           "xunit": "s"},
}
# Second marker: when the sheet would have shown the problem without the AI.
SHOWS = {"F1": "vision_bubbles_per_m2", "F2": "vision_gels_per_m2", "F3": None, "F4": "vision_mark_pitch_mm"}


def series(sc, alert):
    c = D.load(D.HERE / sc["telemetry"])
    if "melt_p1_bar" in c:
        c["dp"] = [a - b for a, b in zip(c["melt_p1_bar"], c["melt_p2_bar"])]
    spec = CHARTS[sc["id"]]
    t, y = c["t_s"], c[spec["col"]]
    pts = [[t[i], round(y[i], 3)] for i in range(0, len(t), spec["every"])
           if spec["x"][0] <= t[i] <= spec["x"][1]]
    shows = None
    if alert.get("lead_time_s"):
        shows = alert["t_alert"] + alert["lead_time_s"]
    elif SHOWS[sc["id"]]:
        col = c[SHOWS[sc["id"]]]
        shows = next((t[i] for i in range(len(t)) if col[i] is not None and col[i] > 1), None)
    return {**spec, "pts": pts, "t_alert": alert["t_alert"], "t_shows": shows}


def main():
    data = []
    for sc in D.FAILURES["scenarios"]:
        alerts = D.diagnose(D.HERE / sc["telemetry"])
        assert len(alerts) == 1 and alerts[0]["failure_mode"] == sc["failure_mode"], sc["id"]
        a = alerts[0]
        data.append({"alert": a, "stop": STOPS[sc["id"]], "chart": series(sc, a)})
    data.sort(key=lambda d: d["stop"]["t"])
    payload = json.dumps({"line": D.CTX, "scenarios": data}, ensure_ascii=False)
    html = (DEMO / "template.html").read_text().replace("__DATA__", payload.replace("</", "<\\/"))
    (DEMO / "index.html").write_text(html)
    print(f"wrote {DEMO / 'index.html'} ({len(html) // 1024} KB), video at demo/line.mp4")


if __name__ == "__main__":
    main()
