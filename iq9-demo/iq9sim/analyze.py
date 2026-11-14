"""Measurements from sensor data only (never from scene parameters)."""
import math

import numpy as np

from . import acoustic, rules
from .geometry import H, W, pix_to_angles
from .scenes import LUGS, OBJECTS


def _roi(c, pad=0):
    yy, xx = np.mgrid[0:H, 0:W]
    return (np.abs(xx - c.cx) <= c.w / 2 + pad) & (np.abs(yy - c.cy) <= c.h / 2 + pad)


def thermal_measure(frame):
    tmax = [float(frame[_roi(c)].max()) for c in LUGS]
    bg = ~np.any([_roi(c, 1) for c in OBJECTS], axis=0)
    dts = [tmax[i] - float(np.mean([tmax[j] for j in range(3) if j != i])) for i in range(3)]
    w = int(np.argmax(dts))
    tier, action = rules.tier(dts[w])
    return {"ambient_c": float(np.median(frame[bg])), "lug_tmax_c": tmax, "lug_dt_c": dts,
            "worst_idx": w, "worst_lug": LUGS[w].name, "dt_c": dts[w], "tier": tier, "tier_action": action}


def measure(frame, mic, load_pct):
    """Returns (measurements dict, acoustic map 24x32 in 0..1)."""
    m = thermal_measure(frame)
    ac = acoustic.analyze(mic)
    x, y = ac["px"]
    az, el = pix_to_angles(x, y)
    lug = LUGS[m["worst_idx"]]
    laz, lel = pix_to_angles(lug.cx, lug.cy)
    near = min(OBJECTS, key=lambda c: math.hypot(c.cx - x, c.cy - y))
    detected = bool(ac["coherence"] >= rules.COH_DETECT)
    sep = math.hypot(az - laz, el - lel)
    m.update({
        "load_pct": float(load_pct),
        "acoustic_detected": detected, "coherence": ac["coherence"], "kurtosis": ac["kurtosis"],
        "impulsive": bool(ac["kurtosis"] >= rules.KURT_IMPULSIVE),
        "px": [x, y], "az_deg": float(az), "el_deg": float(el),
        "target": near.name if math.hypot(near.cx - x, near.cy - y) <= 4 else "unknown",
        "sep_deg": float(sep),
        "colocated": bool(detected and sep <= rules.COLOC_DEG and m["dt_c"] >= rules.FAULT_MIN_DT),
    })
    return m, ac["map"]
