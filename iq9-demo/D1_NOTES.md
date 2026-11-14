# d1-2B on the PC sheet extrusion line

d1 is the second opinion on the line's rule gate. The four failures follow `scenarios/README.md` in this repo (dryer regeneration heater, screen pack, die-zone D5 heater circuit, roll 2 drive coupling). The signals, detection rules and d1 inputs here are written for the demo and are illustrative; use the real line's tags and setpoints.

## What d1 sees per zone
Built in `plant.py` and `extrusion.py`, sent through `iq9sim/d1svc.py`:
- **text**: the zone's live signals plus its normal and failure ranges, for example Z6: `d5_out_pct: 100.0`, `d5_a: 0.03`, `lane_gauge_pct: 97.2`.
- **image**: a chart of the zone's last 40 samples with the dashed limit line (rendered by `chart_image`), no text.
- **image + text (fused)**: both in one call, `system_one(state, questions, media=[chart])`.

Questions, each returned as probabilities with no output tokens: fault (`noul`), severity (`score`: Low, Moderate, Critical), failure family (`choice`: heating, pressure, mechanical, normal). Code decides the action from the rule gate; d1 never executes.

| Zone | Failure | Rule fires when | Part named | Family d1 should pick |
|---|---|---|---|---|
| Z1 Drying | Regeneration heater failed | heater current under 1 A while demanded | heater element or contactor | heating |
| Z3 Filtration | Screen pack torn | screen dP under 50 bar at steady screw speed | screen pack | pressure |
| Z6 Die | Zone D5 heater circuit open | output 95 percent or more, current under 1 A | D5 cartridge or contactor | heating |
| Z7 Roll stack | Roll 2 coupling wear | torque swing repeating once per revolution, bearing vibration normal | roll 2 drive coupling | mechanical |

## Measured on simulated signals (laptop CPU, `tools/d1_line_probe.py`, `logs/d1_line_probe_20261113.log`)
One healthy and one failing run per zone, sample at the 30th reading. About 1.4 s text, 1.6 s image, 1.7 s fused per zone.

| Zone | Scenario | Rule | Fault: text / image / image+text | Severity: text / image / image+text | Family |
|---|---|---|---|---|---|
| Z1 | healthy | OK | 0.99 / 0.21 / 0.16 | Critical / Low / Low | heating |
| Z1 | heater failed | FAULT | 1.00 / 0.40 / 1.00 | Critical / Low / Critical | heating (0.98) |
| Z3 | healthy | OK | 0.26 / 0.16 / 0.04 | Critical / Low / Low | pressure |
| Z3 | screen torn | FAULT | 1.00 / 0.44 / 0.99 | Critical / Low / Critical | pressure (0.96) |
| Z6 | healthy | OK | 0.89 / 0.20 / 0.22 | Critical / Low / Low | mechanical |
| Z6 | die D5 heater open | FAULT | 0.98 / 0.75 / 0.98 | Critical / Moderate / Critical | mechanical (0.49), expected heating |
| Z7 | healthy | OK | 0.44 / 0.13 / 0.18 | Moderate / Low / Low | mechanical |
| Z7 | roll 2 coupling | FAULT | 0.74 / 0.14 / 0.44 | Moderate / Low / Moderate | mechanical (0.86) |

Reading it honestly:
- **Image + text is the usable fault and severity signal.** It stays low on all four healthy runs (0.04 to 0.22) and high on three failures (0.98 to 1.00). Text alone fires on healthy Z1 (0.99) and Z6 (0.89), so it is not used on its own.
- **Image alone** under-reads: it separates on Z6 only. It is a cross-check, not a gate.
- **Z7 roll coupling is weak** (fused 0.44, Moderate). A once-per-revolution ripple is hard to see in a short chart; the rule (autocorrelation at one revolution with normal bearing vibration) is what catches it.
- **Failure family is wrong for Z6** (mechanical 0.49 instead of heating). Do not use the family label for the work order; the knowledge lookup names the part from the rule.
- Four zones and one run each on simulated data: this is a smoke test, not accuracy. Calibrate thresholds on labelled line data before use. Laptop timings, not board timings.

## Run
`~/.venvs/d1/bin/python -I tools/d1_line_probe.py` (needs the weights, see `models/d1-2B/WEIGHTS_NOT_INCLUDED.md`). The live console runs it once per fault: `python3 -I server.py --d1 --llm http://127.0.0.1:18181`, open an extrusion zone and press "Run d1 on this frame".
Needs `transformers==5.19.0` (5.23.0 fails to load d1 with `can_use_lfm3_conv`), torch, torchvision, pillow, numpy.
Liquid AI's d1-2B model code and LICENSE (LFM Open License v1.0) are in `models/d1-2B/`; the 3.57 GiB weights are not.

## Switchgear and compressor (the other assets)
Same three paths with the thermal frame as the picture. Probe on 16 simulated scenes (`logs/d1_probe_20261113_200324_vision.log`): fault text 0.31 (OK, n=8) vs 0.80 (FAULT, n=11); image only 0.24 vs 0.48; image + text 0.34 vs 0.76.
Earlier logs: `logs/d1_probe_20261113_193523.log` (text and image hotspot), `logs/d1_log_*.jsonl` (verdicts from the live console).
