# d1 files behind the mocks

Code and logs used to produce the d1 numbers shown in mocks D and E. Added files only.

| File | Role |
|---|---|
| `d1svc.py` | d1-2B service: loaded once, CPU fp32, serial worker. State questions (fault `noul`, severity `score`, category `choice`) and an image question (hotspot `noul`) on the thermal frame; text-only variant for the extrusion signals. Returns probabilities and latency, logs JSONL. d1 never executes actions |
| `d1.py` | d1 as the decision gate (`noul` fault / unreliable) following the d1-2B model card |
| `extrusion.py` | The four extrusion failure scenarios, detection rules, knowledge lookup, and the text block (`NORMAL`) given to d1 |
| `d1_probe.py` | Probe over named and random simulated scenes: latency and fault/healthy separation |
| `logs/d1_probe_20261113_193523.log` | Probe output: 16 simulated scenes, mean p_fault 0.31 (OK, n=8) vs 0.79 (FAULT, n=7); image hotspot 0.22 vs 0.61; state about 1.45 s, image about 1.32 s on a laptop CPU |
| `logs/d1_log_20261113_195550.jsonl` | d1 verdicts logged by the live console, including the extrusion zones |

Run notes: `transformers==5.19.0` with torch, torchvision, pillow and numpy; 5.23.0 fails to load d1 (`can_use_lfm3_conv`). Local snapshot, offline. Small sample on simulated data: not an accuracy claim. Laptop timings, not board timings.
These files import the demo's own `iq9sim` package (analyze, report, scenes), which is not part of this PR; they are included for review.
The d1-2B weights and Liquid AI's model code are not included.

(c) Aavinos LLC, Mind Theory AI, and Christian Camacho-Martinez. All rights reserved.
