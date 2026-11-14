# Machine-failure scenarios

Four examples of a part failing on the PC sheet line. In each one the AI catches the failure from line signals, looks it up in the knowledge base (`kb/line.json`, `kb/defects.json`) and names the part to repair, so the line can get running again quickly.

| # | Zone | What fails | How the AI spots it | Warning before scrap | Est. time to resume |
|---|---|---|---|---|---|
| F1 | Z1 Drying | Dryer regeneration heater | Heater current drops to 0 A while process air stays at 120 °C | ~2.5 h (before dew point rises and bubbles appear) | 45 min |
| F2 | Z3 Filtration | Screen pack torn | Pressure across the screen collapses 85 → 23 bar while screw speed holds | ~1 min | 5 min (index screen changer) |
| F3 | Z6 Die | Heater circuit in die zone D5 | Controller output at 100 % but 0 A, then a thin lane at 1172–1465 mm | ~6.5 min | 20 min |
| F4 | Z7 Roll stack | Roll 2 drive coupling | Torque repeats once per roll 2 revolution: 42.3 s × line speed = 1414 mm = π × 450 mm; bearings normal | marks visible ~2 min after onset | 60 min |

## Run

```bash
python3 scenarios/simulate.py          # regenerate telemetry/*.csv (fixed seed)
python3 scenarios/diagnose.py          # operator alert cards + self-check
python3 scenarios/diagnose.py --json   # same alerts as JSON, for a UI
```

`diagnose.py` runs every rule on every file and never reads the scenario labels, so a file only alerts if its data really shows the failure. Running the rules on the healthy part of each record produces no alerts.

## Files

- `failures.json`: the four scenarios: story, signals, how the AI detects it, what it rules out, the KB zone/part/defect links, and the repair-and-restart playbook
- `simulate.py`: makes synthetic telemetry that follows the physics of each failure
- `telemetry/`: generated CSVs
- `diagnose.py`: detection rules plus the KB lookup (zone, parts, defects, safety)

Tag names, roll diameters, setpoints and repair times are illustrative. Replace them with your line's real values before using this on a real line.
