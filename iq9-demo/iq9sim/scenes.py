"""Scenes: parameters -> simulated thermal frame + mic signals, plus ground truth known to the simulator."""
from dataclasses import asdict, dataclass, field

import numpy as np

from . import acoustic, rules, thermal


@dataclass(frozen=True)
class Component:
    name: str
    cx: int
    cy: int
    w: int
    h: int


LUGS = (Component("Lug A", 8, 12, 4, 8), Component("Lug B", 16, 12, 4, 8), Component("Lug C", 24, 12, 4, 8))
FITTING = Component("Air fitting", 29, 5, 2, 2)
OBJECTS = LUGS + (FITTING,)
BASE_RISE_100 = 11.0   # deg C rise of a lug at 100% load; scales with load squared (I^2 R)


@dataclass
class Source:
    kind: str          # "pd" (partial discharge crackle) or "hiss" (air leak)
    x: int
    y: int
    snr_db: float      # per-mic broadband SNR


@dataclass
class Scene:
    name: str
    seed: int
    ambient: float
    load_pct: float
    thermal_delta: float = 0.0     # extra deg C on the fault lug's centre pixel
    fault_lug: int = 1
    sources: list = field(default_factory=list)
    noise_c: float = 0.25
    lug_var: float = 0.10          # unit-to-unit variation of lug heating (relative sd)


def named_scene(name, seed=1):
    b = LUGS[1]
    table = {
        "panel_fault": Scene("panel_fault", seed, 24.0, 85.0, 18.0, 1, [Source("pd", b.cx, b.cy, 3.0)]),
        "air_leak": Scene("air_leak", seed, 22.0, 70.0, 0.0, 1, [Source("hiss", FITTING.cx, FITTING.cy, 4.0)]),
        "healthy": Scene("healthy", seed, 23.0, 75.0),
        "conflict": Scene("conflict", seed, 21.0, 25.0, 6.0, 2),
    }
    if name not in table:
        raise KeyError(name)
    return table[name]


SCENE_NAMES = ["panel_fault", "air_leak", "healthy", "conflict"]


def random_scene(seed):
    r = np.random.default_rng(seed)
    kind = r.choice(["healthy", "thermal", "pd_early", "leak", "low_load"], p=[.25, .25, .10, .20, .20])
    fl = int(r.integers(0, 3))
    lug = LUGS[fl]
    s = Scene(f"random-{seed}", seed, float(r.uniform(15, 35)), float(r.uniform(45, 100)),
              float(r.uniform(0, 3)), fl, [], float(r.uniform(0.15, 0.4)))
    if kind == "thermal":
        s.thermal_delta = float(r.uniform(4, 25))
        if r.random() < 0.5:
            s.sources.append(Source("pd", lug.cx, lug.cy, float(r.uniform(-6, 8))))
    elif kind == "pd_early":
        s.sources.append(Source("pd", lug.cx, lug.cy, float(r.uniform(-6, 8))))
    elif kind == "leak":
        s.sources.append(Source("hiss", int(r.integers(2, 30)), int(r.integers(2, 22)), float(r.uniform(-6, 8))))
    elif kind == "low_load":
        s.load_pct = float(r.uniform(15, 38))
        s.thermal_delta = float(r.uniform(0, 10))
    return s


def ground_truth(s):
    """Label from the injected parameters (what is really wrong), not from the measurements."""
    th_load_ok = s.load_pct >= rules.MIN_LOAD_PCT
    thermal_fault = th_load_ok and s.thermal_delta >= rules.FAULT_MIN_DT
    if s.sources or thermal_fault:
        label = "FAULT"
    elif not th_load_ok:
        label = "INCONCLUSIVE"
    else:
        label = "OK"
    sev = rules.tier(s.thermal_delta)[0] if th_load_ok else "none"
    if s.sources:
        pd = any(x.kind == "pd" for x in s.sources)
        sev = max(sev, "critical" if (pd and thermal_fault) else "probable", key=rules.SEVERITY.index)
    return {"label": label, "severity": sev,
            "sources": [x.kind for x in s.sources], "thermal_delta_c": s.thermal_delta}


def simulate(s):
    rng = np.random.default_rng(s.seed + 10_000)
    var = 1 + rng.normal(0, s.lug_var, 3)
    rise = BASE_RISE_100 * (s.load_pct / 100) ** 2
    comps = [(c, rise * v) for c, v in zip(LUGS, var)]
    hot = []
    if s.thermal_delta:
        c = LUGS[s.fault_lug]
        hot.append((c.cx, c.cy, s.thermal_delta, 1.2))
    return thermal.render(comps, s.ambient, hot, s.noise_c, rng), acoustic.simulate_mics(s.sources, rng)


def scene_info(s):
    return asdict(s)
