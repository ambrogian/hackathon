"""Live plant: simulated assets with evolving faults, stepped through the same loop as agent.py
(observe -> decide -> act -> explain -> log). Feeds the console's architecture view, log tail and incident replay."""
import collections
import json
import os
import platform
import resource
import statistics
import sys
import threading
import time

import agent
import extrusion
from iq9sim import engine, scenes

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = {
    "sg1": {"name": "SG-1", "room": "Switchgear room 2", "kind": "switchgear"},
    "sg2": {"name": "SG-2", "room": "Switchgear room 2", "kind": "switchgear"},
    "sg3": {"name": "SG-3", "room": "Switchgear room 2", "kind": "switchgear"},
    "sg4": {"name": "SG-4", "room": "Switchgear room 2", "kind": "switchgear"},
    "c1": {"name": "C1", "room": "Compressor room", "kind": "compressor"},
    **extrusion.LINE,
    "edge": {"name": "IQ-9075", "room": "Edge closet · real board telemetry", "kind": "board"},
}
MODES = ("healthy", "loose_lug", "air_leak", "low_load")  # allowlist for inject (plant assets)
BOARD_MODES = ("live", "hot_sim")  # hot_sim adds a clearly labelled synthetic temperature ramp
DEFAULT_MODES = {"sg2": "loose_lug", "c1": "air_leak", "edge": "live", **extrusion.DEFAULT_LINE_MODES}
SEV = {"OK": 0, "INCONCLUSIVE": 1, "FAULT": 2}


def scene_for(asset, mode, age):
    """Scenario at a given age (ticks since the mode was set). Faults ramp up so there is something to notice early."""
    base = 100 + 17 * list(ASSETS).index(asset)  # scene assets only
    seed = base * 1000 + age % 40
    b, f = scenes.LUGS[1], scenes.FITTING
    if mode == "loose_lug":
        delta = min(18.0, 0.5 * age)
        src = []
        if age >= 12:
            src = [scenes.Source("pd", b.cx, b.cy, min(3.0, -2.0 + 0.6 * (age - 12)))]
        return scenes.Scene("loose_lug", seed, 24.0, 85.0, delta, 1, src)
    if mode == "air_leak":
        return scenes.Scene("air_leak", seed, 22.0, 70.0, 0.0, 1, [scenes.Source("hiss", f.cx, f.cy, min(4.0, -3.0 + 0.7 * age))])
    if mode == "low_load":
        return scenes.Scene("low_load", seed, 21.0, 25.0, 6.0, 2)
    return scenes.Scene("healthy", seed, 23.0, 75.0)


THERMAL_LIMIT_C, THERMAL_RISE_C = 70.0, 8.0  # example thresholds from the reference always-on agent; set from your own readings


class BoardTelemetry:
    """The host's own SoC thermal zones and CPU load. Real data on the IQ-9075 (Linux); on a laptop there are no zones."""

    def __init__(self):
        self.hist = collections.deque(maxlen=600)  # (time, temp)

    @staticmethod
    def zones():
        import glob
        out = []
        for f in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            try:
                with open(f) as fh:
                    v = int(fh.read().strip()) / 1000.0
                if -20 < v < 150:
                    out.append(v)
            except (OSError, ValueError):
                pass
        return out

    def read(self, offset=0.0):
        z = self.zones() or ([45.0] if offset else [])  # no zones + hot_sim: synthetic 45 C base, labelled as simulated
        temp = (max(z) + offset) if z else None
        now = time.time()
        if temp is not None:
            self.hist.append((now, temp))
        rise = 0.0
        if temp is not None:
            old = [t for ts, t in self.hist if now - ts >= 55]
            rise = temp - old[-1] if old else 0.0
        load = (os.getloadavg()[0] / (os.cpu_count() or 1) * 100) if hasattr(os, "getloadavg") else 0.0
        return {"temp_c": temp, "rise_c": rise, "load_pct": load, "zones": len(z)}


class Plant:
    def __init__(self, decider, llm_url=None, interval=2.0, log_path=None, d1=None):
        self.decider, self.llm, self.interval = decider, llm_url, interval
        self.lock = threading.Lock()
        self.stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = log_path or os.path.join(HERE, "out", f"live_log_{self.stamp}.jsonl")
        self.orders_path = os.path.join(HERE, "out", f"live_orders_{self.stamp}.jsonl")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.buf = collections.deque(maxlen=3000)
        self.seq = 0
        self.tick = 0
        self.t0 = time.time()
        self.assets = {a: {"mode": DEFAULT_MODES.get(a, "healthy"), "age": 0, "last": None, "scene": None,
                           "changed_seq": 0, "llm_text": None} for a in ASSETS}
        self._stop = threading.Event()
        self.telem = BoardTelemetry()
        self.line = {a: extrusion.LineSim() for a in extrusion.LINE}
        self.d1 = d1

    # ---- loop ----
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        with open(self.log_path, "a", encoding="utf-8") as log:
            while not self._stop.is_set():
                t0 = time.time()
                for a in ASSETS:
                    self._step(a, log)
                self.tick += 1
                self._stop.wait(max(0.05, self.interval - (time.time() - t0)))

    def _step_board(self, asset, log):
        t0 = time.perf_counter()
        with self.lock:
            st = self.assets[asset]
            st["age"] += 1
            mode, age, prev = st["mode"], st["age"], st["last"]
        sim = mode == "hot_sim"
        o = self.telem.read(min(30.0, 1.5 * age) if sim else 0.0)
        t1 = time.perf_counter()
        temp, rise, load = o["temp_c"], o["rise_c"], o["load_pct"]
        if temp is None:
            label, sev, p, why = "INCONCLUSIVE", "none", 0.5, "no thermal zones on this host (they exist on the board)"
        elif temp >= THERMAL_LIMIT_C or rise >= THERMAL_RISE_C:
            label, sev, p = "FAULT", "critical" if temp >= THERMAL_LIMIT_C else "probable", 0.95
            why = f"{'temperature at or above ' + str(THERMAL_LIMIT_C) + ' C' if temp >= THERMAL_LIMIT_C else 'rise of ' + format(rise, '.1f') + ' C in a minute'}"
        else:
            label, sev, p, why = "OK", "none", 0.9, "within limits"
        src = "simulated offset" if sim else ("board" if temp is not None else "none")
        action_name = {"FAULT": "flag_for_repair", "OK": "no_op", "INCONCLUSIVE": "no_op"}[label]
        text = (f"{label}. SoC {temp:.1f} C ({rise:+.1f} C in 60 s), CPU load {load:.0f}%: {why}." if temp is not None
                else f"{label}. {why}. CPU load {load:.0f}%.") + (" Temperature includes a simulated offset." if sim else "")
        prev_label = prev["decision"]["label"] if prev and prev.get("decision") else None
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "i": self.seq, "error": None, "kind": "board",
               "measure": {"load_pct": load, "ambient_c": None, "worst_lug": "SoC", "dt_c": max(0.0, rise), "tier": "none",
                           "acoustic_detected": False, "impulsive": False, "coherence": 0.0, "target": "-", "colocated": False,
                           "temp_c": temp, "source": src, "zones": o["zones"]},
               "decision": {"label": label, "p": p, "severity": sev, "decider": "rule (board thermal)"},
               "action": {"name": action_name, "status": "executed"}, "report": text, "report_source": "template", "llm": None}
        st["okrun"] = st.get("okrun", 0) + 1 if label != "FAULT" else 0
        if st["okrun"] >= 3:
            st["order_open"] = False
        if label == "FAULT":
            if not st.get("order_open"):
                rec["action"] = agent.run_action(action_name, {"asset": asset, "label": label, "temp_c": temp}, self.orders_path)
                st["order_open"] = True
            else:
                rec["action"] = {"name": action_name, "status": "already_open"}
        rec["ms"] = {"observe": round((t1 - t0) * 1e3, 1), "decide": 0.0, "act": 0.0, "explain": 0.0}
        rec["ms_total"] = round((time.perf_counter() - t0) * 1e3, 1)
        rec.update({"asset": asset, "mode": mode, "age": age, "tick": self.tick})
        with self.lock:
            self.seq += 1
            rec["seq"] = self.seq
            st["last"], st["scene"] = rec, None
            if label != prev_label:
                st["changed_seq"] = self.seq
            self.buf.append(rec)
        log.write(json.dumps(rec) + "\n")
        log.flush()

    def _step_line(self, asset, log):
        t0 = time.perf_counter()
        with self.lock:
            st = self.assets[asset]
            st["age"] += 1
            mode, age, prev = st["mode"], st["age"], st["last"]
        sim = self.line[asset]
        s = sim.sample(asset, mode, age)
        t1 = time.perf_counter()
        fmode, headline, evidence = sim.detect(asset, s)
        label = "FAULT" if fmode else "OK"
        kb = extrusion.KB.get(fmode) if fmode else None
        text = extrusion.report_text(asset, fmode, headline, evidence) if fmode else f"OK. {extrusion.LINE[asset]['zone']}: all signals within normal range."
        prev_label = prev["decision"]["label"] if prev and prev.get("decision") else None
        action_name = "flag_for_repair" if fmode else "no_op"
        dev = {"z1": 18.0 - s.get("heater_a", 18), "z3": 85.0 - s.get("screen_dp_bar", 85), "z6": 100.0 - s.get("lane_gauge_pct", 100)
               + (s.get("d5_out_pct", 55) - 55) / 10, "z7": max(0.0, (max(sim.torque) - min(sim.torque)) if sim.torque else 0.0)}[asset]
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "i": self.seq, "error": None, "kind": "line", "fault": fmode,
               "measure": {"load_pct": 100.0, "ambient_c": None, "worst_lug": extrusion.LINE[asset]["zone"], "dt_c": max(0.0, dev), "tier": "none",
                           "acoustic_detected": False, "impulsive": False, "coherence": 0.0, "target": "-", "colocated": False,
                           "signals": {k: round(v, 2) for k, v in s.items()}, "headline": headline, "evidence": evidence},
               "decision": {"label": label, "p": 0.95 if fmode else 0.9, "severity": "critical" if fmode else "none", "decider": "rule (line signals)"},
               "action": {"name": action_name, "status": "executed"}, "report": text, "report_source": "template", "llm": None}
        st["okrun"] = st.get("okrun", 0) + 1 if label == "OK" else 0
        if st["okrun"] >= 3:
            st["order_open"] = False
            st["d1_done"] = False
        if fmode:
            if not st.get("order_open"):
                rec["action"] = agent.run_action(action_name, {"asset": asset, "label": label, "fault": fmode, "part": kb["part"], "zone": kb["zone"],
                                                                "resume_min": kb["resume_min"]}, self.orders_path)
                st["order_open"] = True
            else:
                rec["action"] = {"name": action_name, "status": "already_open"}
            if self.d1 and not st.get("d1_done"):
                st["d1_done"] = True
                body = "\n".join(f"{k}: {v}" for k, v in rec["measure"]["signals"].items())
                hist = [r["measure"]["signals"] for r in self.buf if r["asset"] == asset][-40:] + [rec["measure"]["signals"]]
                hist = [{**h, "d5_a5": h.get("d5_a", 0) * 5} for h in hist]
                self.d1.submit((asset, self.seq + 1), {"text": f"PC sheet extrusion line, {extrusion.LINE[asset]['zone']}\n{extrusion.NORMAL[asset]}\n{body}\nrule evidence: {headline}",
                                                       "history": hist, "panels": extrusion.PANELS[asset]},
                               lambda key, res, a=asset: self._d1_done(a, key, res))
        rec["ms"] = {"observe": round((t1 - t0) * 1e3, 1), "decide": round((time.perf_counter() - t1) * 1e3, 1), "act": 0.0, "explain": 0.0}
        rec["ms_total"] = round((time.perf_counter() - t0) * 1e3, 1)
        rec.update({"asset": asset, "mode": mode, "age": age, "tick": self.tick})
        with self.lock:
            self.seq += 1
            rec["seq"] = self.seq
            st["last"], st["scene"] = rec, None
            if label != prev_label:
                st["changed_seq"] = self.seq
            self.buf.append(rec)
        log.write(json.dumps(rec) + "\n")
        log.flush()

    def _step(self, asset, log):
        if ASSETS[asset]["kind"] == "board":
            return self._step_board(asset, log)
        if ASSETS[asset]["kind"] == "line":
            return self._step_line(asset, log)
        with self.lock:
            st = self.assets[asset]
            st["age"] += 1
            mode, age, prev = st["mode"], st["age"], st["last"]
        scene = scene_for(asset, mode, age)
        prev_label = prev["decision"]["label"] if prev and prev.get("decision") else None
        ns = type("A", (), {"seed": 1, "llm": self.llm,
                            "llm_when": staticmethod(lambda lab: lab != "OK" and lab != prev_label)})()
        rec = agent.iteration(self.seq, ns, self.decider, os.devnull, scene=scene)
        label = (rec.get("decision") or {}).get("label")
        if rec["error"] is None:
            if label == prev_label and prev and prev.get("report_source", "").startswith("llm") and prev.get("report"):
                rec["report"], rec["report_source"] = prev["report"], "llm (kept)"
            st["okrun"] = st.get("okrun", 0) + 1 if label == "OK" else 0
            if st["okrun"] >= 3:
                st["order_open"] = False  # three clean loops close the order
                st["d1_done"] = False
            if self.d1 and label != "OK" and not st.get("d1_done"):  # one d1 second opinion per fault episode, async
                st["d1_done"] = True
                self.d1.submit((asset, self.seq + 1), scene, lambda key, res, a=asset: self._d1_done(a, key, res))
            if label != "OK" and rec["action"]["name"] != "no_op":
                if not st.get("order_open"):  # one work order until the asset is clean again
                    rec["action"] = agent.run_action(rec["action"]["name"],
                                                     {"asset": asset, "label": label, "worst": rec["measure"]["worst_lug"],
                                                      "dt_c": rec["measure"]["dt_c"]}, self.orders_path)
                    st["order_open"] = True
                else:
                    rec["action"] = {"name": rec["action"]["name"], "status": "already_open"}
        rec.update({"asset": asset, "mode": mode, "age": age, "tick": self.tick})
        with self.lock:
            self.seq += 1
            rec["seq"] = self.seq
            st["last"], st["scene"] = rec, scene
            if label != prev_label:
                st["changed_seq"] = self.seq
            self.buf.append(rec)
        log.write(json.dumps(rec) + "\n")
        log.flush()

    # ---- queries ----
    def _d1_done(self, asset, key, res):
        with self.lock:
            self.assets[asset]["d1"] = {**res, "for_seq": key[1]}

    def d1_run(self, asset):
        """On-demand d1 assessment of one asset's current scene (blocks for about 3 s on the CPU)."""
        if asset not in ASSETS or ASSETS[asset]["kind"] == "board":
            raise KeyError("d1 needs a scene asset")
        if not self.d1:
            return {"error": "d1 not enabled (start the server with --d1)"}
        with self.lock:
            st = self.assets[asset]
            if ASSETS[asset]["kind"] == "line":
                m = (st["last"] or {}).get("measure") or {}
                scene = {"text": f"PC sheet extrusion line, {extrusion.LINE[asset]['zone']}\n{extrusion.NORMAL[asset]}\n" + "\n".join(f"{k}: {v}" for k, v in (m.get("signals") or {}).items())
                         + f"\nrule evidence: {m.get('headline') or 'none'}",
                         "history": [{**r["measure"]["signals"], "d5_a5": r["measure"]["signals"].get("d5_a", 0) * 5} for r in self.buf if r["asset"] == asset][-40:],
                         "panels": extrusion.PANELS[asset]}
            else:
                scene = st["scene"] or scene_for(asset, st["mode"], 0)
        res = self.d1.assess(scene)
        res["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        if "error" not in res:
            with self.lock:
                self.assets[asset]["d1"] = {**res, "for_seq": self.seq}
        return res

    def state(self):
        with self.lock:
            out = []
            for a, meta in ASSETS.items():
                st = self.assets[a]
                r = st["last"] or {}
                d, m = r.get("decision") or {}, r.get("measure") or {}
                out.append({"id": a, **meta, "mode": st["mode"], "age": st["age"], "label": d.get("label", "OK"),
                            "severity": d.get("severity", "none"), "p": d.get("p"), "worst": m.get("worst_lug"),
                            "dt_c": m.get("dt_c"), "coherence": m.get("coherence"), "acoustic": m.get("acoustic_detected"),
                            "impulsive": m.get("impulsive"), "load_pct": m.get("load_pct"), "tier": m.get("tier"),
                            "action": r.get("action"), "report": r.get("report"), "seq": r.get("seq"),
                            "changed_seq": st["changed_seq"], "kind": meta["kind"],
                            "temp_c": m.get("temp_c"), "source": m.get("source"), "d1": st.get("d1"), "headline": m.get("headline"), "fault": r.get("fault"),
                            "part": (extrusion.KB.get(r.get("fault")) or {}).get("part")})
        return {"tick": self.tick, "interval": self.interval, "seq": self.seq, "assets": out,
                "decider": self.decider.name, "llm": bool(self.llm)}

    def log(self, after=0, asset=None, n=80):
        with self.lock:
            rows = [r for r in self.buf if r["seq"] > after and (not asset or r["asset"] == asset)]
        return {"seq": self.seq, "rows": rows[-n:]}

    def inject(self, asset, mode):
        if asset not in ASSETS or mode not in (BOARD_MODES if ASSETS[asset]["kind"] == "board" else extrusion.LINE_MODES[asset] if ASSETS[asset]["kind"] == "line" else MODES):
            raise KeyError("bad asset or mode")
        with self.lock:
            self.assets[asset].update({"mode": mode, "age": 0})

    def request_order(self, asset, reason, severity):
        """Write action behind the ask tool. Policy lives here in code: only a currently FAULT asset without an open order."""
        if asset not in ASSETS:
            return {"error": f"unknown asset '{asset}'. Known: {sorted(ASSETS)}"}, False
        with self.lock:
            st = self.assets[asset]
            label = ((st["last"] or {}).get("decision") or {}).get("label", "OK")
            if label != "FAULT":
                return {"error": f"refused by policy: {ASSETS[asset]['name']} is {label}, work orders need a current FAULT"}, False
            if st.get("order_open"):
                return {"error": f"refused by policy: a work order is already open for {ASSETS[asset]['name']}"}, False
            st["order_open"] = True
        with open(self.orders_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"asset": asset, "label": label, "reason": reason[:200], "severity": severity, "source": "ask"}) + "\n")
            f.flush()
        return {"ok": True, "asset": asset, "status": "work order written", "severity": severity}, True

    def asset_run(self, asset):
        with self.lock:
            st = self.assets[asset]
            scene, last = st["scene"], st["last"]
            hist = [{"ts": r["ts"], "temp_c": r["measure"].get("temp_c"), "load_pct": r["measure"]["load_pct"]}
                    for r in self.buf if r["asset"] == asset][-90:] if ASSETS[asset]["kind"] == "board" else None
        if ASSETS[asset]["kind"] == "line":
            with self.lock:
                rows = [r for r in self.buf if r["asset"] == asset][-90:]
            hist = [{**r["measure"]["signals"], "ts": r["ts"], "d5_a5": r["measure"]["signals"].get("d5_a", 0) * 5} for r in rows]
            fm = (last or {}).get("fault")
            return {"asset": {"id": asset, **ASSETS[asset], "mode": st["mode"], "age": st["age"], "modes": list(extrusion.LINE_MODES[asset])},
                    "line": {"history": hist, "panels": extrusion.PANELS[asset], "kb": extrusion.KB.get(fm), "titles": extrusion.LINE_TITLES},
                    "decision": (last or {}).get("decision"), "measure": (last or {}).get("measure"), "report": (last or {}).get("report", ""),
                    "report_source": "template", "d1": st.get("d1")}
        if hist is not None:
            return {"asset": {"id": asset, **ASSETS[asset], "mode": st["mode"], "age": st["age"]}, "board": {"history": hist},
                    "decision": (last or {}).get("decision"), "measure": (last or {}).get("measure"),
                    "report": (last or {}).get("report", ""), "report_source": "template"}
        if scene is None:
            scene = scene_for(asset, st["mode"], 0)
        out = engine.run_scene(scene, self.decider, None)
        out["asset"] = {"id": asset, **ASSETS[asset], "mode": st["mode"], "age": st["age"]}
        out["d1"] = st.get("d1")
        if last and last.get("report"):
            out["report"], out["report_source"] = last["report"], last.get("report_source", "template")
        return out

    def _series(self, asset):
        with self.lock:
            return [r for r in self.buf if r["asset"] == asset and r["error"] is None]

    def incidents(self):
        res = []
        for asset in ASSETS:
            rows, cur, okrun = self._series(asset), None, 0
            for k, r in enumerate(rows):
                lab = r["decision"]["label"]
                if lab == "FAULT" and cur is None:
                    cur = {"asset": asset, "name": ASSETS[asset]["name"], "start_seq": r["seq"], "ts": r["ts"], "k0": k,
                           "worst": r["measure"]["worst_lug"], "peak_dt_c": 0.0, "open": True}
                if cur is not None:
                    cur["peak_dt_c"] = max(cur["peak_dt_c"], r["measure"]["dt_c"])
                    cur["end_seq"] = r["seq"]
                    okrun = okrun + 1 if lab == "OK" else 0
                    if okrun >= 3:  # three clean loops in a row close it (no flapping at the threshold)
                        cur["open"] = False
                        res.append(cur)
                        cur, okrun = None, 0
            if cur is not None:
                res.append(cur)
        for c in res:
            c["id"] = f"{c['asset']}-{c['start_seq']}"
            c.pop("k0", None)
        return sorted(res, key=lambda c: -c["start_seq"])

    def incident(self, inc_id):
        for c in self.incidents():
            if c["id"] == inc_id:
                rows = self._series(c["asset"])
                first = next(k for k, r in enumerate(rows) if r["seq"] == c["start_seq"])
                lo = max(0, first - 25)
                sel = [r for r in rows[lo:] if r["seq"] <= c.get("end_seq", 1 << 60) + 3]
                return {"incident": c, "start_index": first - lo,
                        "series": [{"seq": r["seq"], "ts": r["ts"], "dt_c": r["measure"]["dt_c"], "coherence": r["measure"]["coherence"],
                                    "load_pct": r["measure"]["load_pct"], "label": r["decision"]["label"], "p": r["decision"]["p"],
                                    "action": r["action"], "report": r["report"], "report_source": r["report_source"],
                                    "worst": r["measure"]["worst_lug"], "tier": r["measure"]["tier"],
                                    "ms_total": r["ms_total"], "target": r["measure"]["target"]} for r in sel]}
        raise KeyError(inc_id)

    def system(self):
        with self.lock:
            rows = [r for r in list(self.buf)[-300:] if r["error"] is None]
        med = lambda xs: round(statistics.median(xs), 2) if xs else None  # noqa: E731
        osr = ""
        try:
            with open("/etc/os-release") as f:
                osr = dict(x.strip().split("=", 1) for x in f if "=" in x).get("PRETTY_NAME", "").strip('"')
        except OSError:
            pass
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)
        return {"host": {"machine": platform.machine(), "system": platform.system(), "os": osr or platform.platform(),
                         "python": platform.python_version(), "load": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
                         "peak_rss_mib": round(rss, 1), "uptime_s": round(time.time() - self.t0)},
                "loop": {"records": len(rows), "median_ms": {k: med([r["ms"][k] for r in rows]) for k in ("observe", "decide", "explain")},
                         "median_total_ms": med([r["ms_total"] for r in rows]), "errors": sum(1 for r in self.buf if r["error"]),
                         "tick": self.tick, "interval_s": self.interval},
                "decider": self.decider.name, "llm": self.llm or None, "d1": self.d1.status() if self.d1 else None, "log_path": self.log_path, "orders_path": self.orders_path}
