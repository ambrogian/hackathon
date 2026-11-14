import glob
import os
import re
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from iq9sim import acoustic, decide, engine, report, rules, scenes  # noqa: E402
from validate import run_validation  # noqa: E402


class Core(unittest.TestCase):
    def test_named_scenes(self):
        want = {"panel_fault": "FAULT", "air_leak": "FAULT", "healthy": "OK", "conflict": "INCONCLUSIVE"}
        for n, label in want.items():
            r = engine.run_scene(scenes.named_scene(n), decide.RuleDecider(), arrays=False)
            self.assertEqual(r["truth"]["label"], label, n)
            self.assertEqual(r["decision"]["label"], label, n)

    def test_noise_only_never_detects(self):
        for s in range(60):
            a = acoustic.analyze(acoustic.simulate_mics([], np.random.default_rng(s)))
            self.assertLess(a["coherence"], rules.COH_DETECT)

    def test_localization(self):
        rng = np.random.default_rng(7)
        hits = 0
        for i in range(30):
            x, y = int(rng.integers(2, 30)), int(rng.integers(2, 22))
            a = acoustic.analyze(acoustic.simulate_mics([scenes.Source("hiss", x, y, 0.0)], np.random.default_rng(i)))
            hits += abs(a["px"][0] - x) <= 2 and abs(a["px"][1] - y) <= 2
        self.assertGreaterEqual(hits, 27)

    def test_tiers(self):
        for dt, key in [(0.9, "none"), (1.0, "possible"), (3.9, "possible"), (4.0, "probable"), (15.0, "critical")]:
            self.assertEqual(rules.tier(dt)[0], key, dt)

    def test_number_check(self):
        m = engine.run_scene(scenes.named_scene("panel_fault"), decide.RuleDecider(), arrays=False)["measure"]
        self.assertEqual(report.check_numbers(f"{m['worst_lug']} is {m['dt_c']:.1f} C hot", m), [])
        self.assertEqual(report.check_numbers("It is 99.7 C hot", m), ["99.7"])

    def test_deterministic(self):
        d = decide.RuleDecider()
        a = engine.run_scene(scenes.random_scene(5), d)
        b = engine.run_scene(scenes.random_scene(5), d)
        self.assertEqual(a, b)

    def test_ui_has_no_external_urls(self):
        for f in glob.glob(os.path.join(ROOT, "ui", "*")):
            if os.path.isdir(f):
                continue
            with open(f, encoding="utf-8") as fh:
                self.assertIsNone(re.search(r"https?://|//cdn|@import", fh.read()), f)
        for f in glob.glob(os.path.join(ROOT, "ui", "fonts", "*")):
            with open(f, "rb") as fh:
                self.assertEqual(fh.read(4), b"wOF2", f)  # local font files, not an HTML error page

    def test_validation_accuracy(self):
        res = run_validation(80, 5000, decide.RuleDecider())
        self.assertGreaterEqual(res["accuracy"], 0.85)


if __name__ == "__main__":
    unittest.main()
