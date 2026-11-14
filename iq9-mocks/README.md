# IQ-9075 inspection demo: enhanced mocks

Added files only; nothing existing in this repo is changed.

| File | What it shows |
|---|---|
| `mock-d-extrusion-line.png` / `.html` | Z6 die zone D5 heater circuit open on the PC sheet line: traces, the rule that fired, d1 second-opinion probabilities (fault, severity, failure family), zone-to-part-to-repair lookup |
| `mock-e-ask-the-plant.png` / `.html` | Operator question answered with tool calls: model proposes, code validates, allowlists, applies the write policy, renders one fixed answer layout |
| `live/*.png` | Captures of the running console: building view with the extrusion line (Z1 dryer, Z3 screen pack, Z6 die, Z7 roll stack), die asset page with d1 probability bars, roll 2 coupling, incident replay |

Failure types follow `scenarios/failures.json` in idea only (dryer heater, screen pack, die-zone heater circuit, roll drive coupling). The detection rules, signals and repair texts in the demo are written separately and are illustrative.
Colour values come from the dark theme in `showcase/template.html`.
Mocks D and E: d1 fault 0.93 and Critical are measured from a live run on a laptop CPU; the other probability bars are illustrative. Signals are simulated. No board numbers yet.
The `.html` mocks use `mock.css` and `mock-pal.css`; fonts fall back to system fonts here.

(c) Aavinos LLC, Mind Theory AI, and Christian Camacho-Martinez. All rights reserved. Contributed for this hackathon showcase.
