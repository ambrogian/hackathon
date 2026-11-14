"""Live plant: fault progression, one work order per state change, incidents with hysteresis, inject allowlist."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import plant  # noqa: E402
from validate import make_decider  # noqa: E402


def make(ticks, tmp):
    p = plant.Plant(make_decider("rules"), None, 0.0, log_path=os.path.join(tmp, "l.jsonl"))
    p.orders_path = os.path.join(tmp, "o.jsonl")
    with open(p.log_path, "a") as log:
        for _ in range(ticks):
            for a in plant.ASSETS:
                p._step(a, log)
            p.tick += 1
    return p


class Plant(unittest.TestCase):
    def test_progression_and_orders(self):
        with tempfile.TemporaryDirectory() as d:
            p = make(40, d)
            s = {a["id"]: a for a in p.state()["assets"]}
            self.assertEqual(s["sg2"]["label"], "FAULT")
            self.assertEqual(s["c1"]["label"], "FAULT")
            self.assertTrue(all(s[k]["label"] == "OK" for k in ("sg1", "sg3", "sg4")))  # no false alarm on healthy assets
            orders = [json.loads(x) for x in open(p.orders_path)]
            self.assertEqual(sorted(o["asset"] for o in orders), ["c1", "sg2", "z6", "z7"])  # one work order per state change
            self.assertEqual(len(open(p.log_path).readlines()), 40 * len(plant.ASSETS))  # every loop logged

    def test_incident_and_inject(self):
        with tempfile.TemporaryDirectory() as d:
            p = make(30, d)
            inc = p.incidents()
            self.assertTrue(any(i["asset"] == "sg2" and i["open"] for i in inc))
            det = p.incident([i for i in inc if i["asset"] == "sg2"][0]["id"])
            self.assertEqual(det["series"][det["start_index"]]["label"], "FAULT")
            with self.assertRaises(KeyError):
                p.inject("sg2", "open_breaker")
            with self.assertRaises(KeyError):
                p.inject("../etc", "healthy")
            p.inject("sg2", "healthy")
            self.assertEqual(p.assets["sg2"]["mode"], "healthy")


class Line(unittest.TestCase):
    def test_extrusion_faults_detected_from_signals_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = make(30, d)
            s = {a["id"]: a for a in p.state()["assets"]}
            self.assertEqual((s["z1"]["label"], s["z3"]["label"]), ("OK", "OK"))  # healthy zones: no false alarm
            self.assertEqual(s["z6"]["fault"], "die_heater_open")
            self.assertIn("D5", s["z6"]["headline"])
            self.assertEqual(s["z7"]["fault"], "coupling_wear")
            self.assertIn("coupling", s["z7"]["part"])
            p.inject("z3", "screen_torn")
            p.inject("z1", "heater_failed")
            with open(p.log_path, "a") as log:
                for _ in range(8):
                    for a in ("z1", "z3"):
                        p._step(a, log)
            s = {a["id"]: a for a in p.state()["assets"]}
            self.assertEqual(s["z3"]["fault"], "screen_torn")
            self.assertEqual(s["z1"]["fault"], "heater_failed")
            with self.assertRaises(KeyError):
                p.inject("z3", "loose_lug")  # modes are per kind
            orders = [json.loads(x) for x in open(p.orders_path)]
            self.assertTrue(any(o.get("part", "").startswith("Screen pack") for o in orders))


class Board(unittest.TestCase):
    def test_board_asset_alert_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = make(2, d)
            self.assertIn(p.assets["edge"]["last"]["decision"]["label"], ("OK", "INCONCLUSIVE", "FAULT"))
            p.inject("edge", "hot_sim")
            with open(p.log_path, "a") as log:
                for _ in range(25):
                    p._step("edge", log)
            e = p.assets["edge"]["last"]
            self.assertEqual(e["decision"]["label"], "FAULT")
            self.assertEqual(e["measure"]["source"], "simulated offset")  # never presented as real
            self.assertIn("simulated", e["report"])
            with self.assertRaises(KeyError):
                p.inject("edge", "loose_lug")  # plant modes are not valid for the board


if __name__ == "__main__":
    unittest.main()
