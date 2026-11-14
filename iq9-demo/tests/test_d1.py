"""d1 second opinion wiring with a fake service (no torch needed): async trigger on a new fault, on-demand run, ask tool."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ask  # noqa: E402
import plant  # noqa: E402
from validate import make_decider  # noqa: E402

RES = {"p_fault": 0.9, "severity_level": 2.0, "severity": "Critical", "category": "thermal", "category_confidence": 0.8,
       "p_hotspot_image": 0.7, "ms": {"state": 10, "image": 9}, "output_tokens": 0, "input_tokens": {"state": 1, "image": 1}}


class Fake:
    def __init__(self):
        self.submitted = []

    def submit(self, key, scene, done):
        self.submitted.append(key)
        done(key, dict(RES, ts="t"))
        return True

    def assess(self, scene):
        return dict(RES)

    def status(self):
        return {"state": "ready"}


class D1(unittest.TestCase):
    def test_second_opinion_once_per_state_change_and_ask_tool(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fake()
            p = plant.Plant(make_decider("rules"), None, 0.0, log_path=os.path.join(d, "l.jsonl"), d1=f)
            p.orders_path = os.path.join(d, "o.jsonl")
            with open(p.log_path, "a") as log:
                for _ in range(30):
                    for a in plant.ASSETS:
                        p._step(a, log)
            assets = sorted(k[0] for k in f.submitted)
            self.assertEqual(assets, ["c1", "sg2", "z6", "z7"])  # once per new fault, not every loop, never for healthy assets or the board
            s = {a["id"]: a for a in p.state()["assets"]}
            self.assertEqual(s["sg2"]["d1"]["severity"], "Critical")
            res, ok = ask.run_tool(p, "d1_assess", '{"asset":"sg2"}')
            self.assertTrue(ok)
            self.assertEqual(res["p_fault"], 0.9)
            self.assertFalse(ask.run_tool(p, "d1_assess", '{"asset":"edge"}')[1])  # board has no frame
            r = ask.ask(p, "Confirm SG-2 with d1")
            self.assertIn("d1 second opinion, SG-2: fault 0.90", r["answer"])

    def test_without_d1_everything_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            p = plant.Plant(make_decider("rules"), None, 0.0, log_path=os.path.join(d, "l.jsonl"))
            self.assertIn("error", p.d1_run("sg2"))
            res, ok = ask.run_tool(p, "d1_assess", '{"asset":"sg2"}')
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
