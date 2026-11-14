"""Generate simulated line telemetry for the four failure scenarios.

Writes scenarios/telemetry/F1_dryer.csv ... F4_rolls.csv.
The data is synthetic but follows the physics of each failure (see failures.json).
Fixed random seed, so the output is the same every run.

Run: python3 scenarios/simulate.py
"""
import csv
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "telemetry"
OUT.mkdir(exist_ok=True)
rng = random.Random(42)


def noise(sd):
    return rng.gauss(0, sd)


def ramp(t, t0, tau):
    """0 before t0, then 1 - exp(-(t - t0) / tau)."""
    return 0.0 if t < t0 else 1 - math.exp(-(t - t0) / tau)


def logistic(t, mid, width):
    return 1 / (1 + math.exp(-(t - mid) / width))


def write(name, header, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r[0]] + [("" if v is None else round(v, 3)) for v in r[1:]])
    print(f"wrote {OUT / name} ({len(rows)} rows)")


# F1: dryer regeneration heater fails at t = 60 min. 1-minute samples, 6 h.
def f1():
    fail = 60 * 60
    rows = []
    for t in range(0, 6 * 3600 + 1, 60):
        regen_a = 18.0 + noise(0.2) if t < fail else max(0.0, noise(0.05))
        regen_c = 185 - 145 * ramp(t, fail, 6 * 60) + noise(0.8)
        process = 120 + noise(0.3)
        dew = -42 + 30 * logistic(t, fail + 110 * 60, 30 * 60) + noise(0.4)
        vacuum = 20 + 25 * logistic(t, fail + 180 * 60, 30 * 60) + noise(0.5)
        bubbles = 0.1 + 12 * logistic(t, fail + 190 * 60, 15 * 60) + abs(noise(0.05))
        rows.append([t, regen_a, regen_c, process, dew, vacuum, bubbles])
    write("F1_dryer.csv",
          ["t_s", "dryer_regen_heater_A", "dryer_regen_temp_C", "dryer_process_air_C",
           "dryer_dewpoint_C", "vent_vacuum_mbar_abs", "vision_bubbles_per_m2"], rows)


# F2: screen pack tears at t = 300 s. 1-second samples, 10 min.
def f2():
    tear, transport = 300, 75
    rows = []
    for t in range(0, 601):
        p2 = 100 + noise(0.4)
        dp = 84 + 2 * t / 600                         # slow loading before the tear
        if t >= tear:
            dp = dp - 63 * min(1.0, (t - tear) / 15)  # collapse over ~15 s
            p2 += 3 * math.exp(-(t - tear) / 10) * math.sin((t - tear) / 3)  # control loop wobble
        p1 = p2 + dp + noise(0.6)
        gels = 0.2 + abs(noise(0.1))
        if t >= tear + transport:
            gels = 8 + noise(1.2)
        rows.append([t, 42.0 + noise(0.05), p1, p2, 31.0 + noise(0.03), max(gels, 0)])
    write("F2_screen.csv",
          ["t_s", "screw_rpm", "melt_p1_bar", "melt_p2_bar", "gearpump_rpm", "vision_gels_per_m2"], rows)


# F3: die zone D5 heater circuit opens at t = 900 s. 10-second samples, 1 h.
def f3():
    fail, sp, zones = 900, 290.0, 7
    header = ["t_s"]
    for k in range(1, zones + 1):
        header += [f"die_D{k}_temp_C", f"die_D{k}_out_pct", f"die_D{k}_amp"]
    header += [f"thickness_lane{k}_mm" for k in range(1, zones + 1)]
    rows = []
    for t in range(0, 3601, 10):
        r = [t]
        drop5 = 30 * ramp(t, fail, 900)
        for k in range(1, zones + 1):
            temp, out = sp + noise(0.3), 45 + noise(1.5)
            if k == 5 and t >= fail:
                temp = sp - drop5 + noise(0.3)
                out = min(100.0, 45 + 55 * min(1.0, (t - fail) / 40))
                amp = max(0.0, noise(0.03))
            else:
                if k in (4, 6):
                    temp -= 0.07 * drop5
                    out += 0.35 * drop5
                amp = 9.0 * out / 100 + noise(0.05)
            r += [temp, out, amp]
        thin = 0.26 * ramp(t, fail + 120, 900)
        for k in range(1, zones + 1):
            th = 4.00 + noise(0.008)
            if k == 5:
                th -= thin
            elif k in (4, 6):
                th += 0.2 * thin
            r.append(th)
        rows.append(r)
    write("F3_die.csv", header, rows)


# F4: roll 2 coupling starts kicking once per revolution at t = 60 s. 0.5 s samples, 6 min.
def f4():
    speed = 2.0  # m/min
    d2 = 0.450   # m
    period = math.pi * d2 / (speed / 60)  # s per roll 2 revolution, about 42.4 s
    onset, transport = 60, 45
    rows = []
    t = 0.0
    while t <= 360:
        r1 = 34 + noise(0.5)
        r3 = 31 + noise(0.5)
        r2 = 38 + noise(0.5)
        if t >= onset:
            phase = ((t - onset) % period)
            r2 += 7 * math.exp(-((phase - 5) ** 2) / (2 * 0.8 ** 2))  # kick once per rev
            r2 += 1.2 * math.sin(2 * math.pi * (t - onset) / period)
        pitch = None
        if t >= onset + transport + period:  # camera needs two marks to measure a spacing
            pitch = math.pi * d2 * 1000 + noise(4)
        rows.append([round(t, 1), speed + noise(0.002), r1, r2, r3,
                     52 + noise(0.2), 49 + noise(0.2), pitch])
        t += 0.5
    write("F4_rolls.csv",
          ["t_s", "line_speed_m_min", "roll1_torque_pct", "roll2_torque_pct", "roll3_torque_pct",
           "roll2_bearing_DS_C", "roll2_bearing_OS_C", "vision_mark_pitch_mm"], rows)


if __name__ == "__main__":
    f1(); f2(); f3(); f4()
