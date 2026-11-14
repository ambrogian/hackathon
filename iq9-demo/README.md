# IQ-9075 inspection demo (self-contained)

Offline inspection console for the Dragonwing IQ-9075, anchored on this repo's PC sheet extrusion line: Z1 dryer regeneration heater, Z3 screen pack, Z6 die-zone D5 heater circuit, Z7 roll 2 drive coupling (the four scenarios in `scenarios/`). It also monitors switchgear, a compressor and the edge board. Observe, decide (rule gate, d1-2B second opinion with text, image and fused fault / severity probabilities), act (allowlist), explain (LFM3, only when needed), log (flushed JSONL). Signals are simulated; the edge board asset reads the host's real SoC thermal zones when they exist.

Everything is new files in this folder. It does not import anything from the rest of the repo, so it plugs in by copying or running from here.

## Run
```bash
cd iq9-demo
python3 -I server.py --port 8088                                     # rules only, template text, stdlib + numpy
python3 -I server.py --port 8088 --llm http://127.0.0.1:18181        # LFM3-1.7B explanations + ask-the-plant tool calling
~/.venvs/d1/bin/python -I server.py --port 8088 --d1 [path] --llm http://127.0.0.1:18181   # plus d1-2B probabilities
python3 -I agent.py --iterations 8 --interval 0                       # headless loop, writes out/agent_log_*.jsonl
python3 -I -W ignore -m unittest discover -s tests                    # 24 tests
```
Open http://127.0.0.1:8088. Views: architecture (clickable building), asset console with fault injection, live log, incidents with replay, ask the plant, edge stack. Every request stays on 127.0.0.1; no CDN, no installs at runtime.

## Needs
- Python 3 and numpy for the base demo.
- d1 (optional): torch, torchvision, pillow, numpy and `transformers==5.19.0` (5.23.0 fails to load d1) in a venv, plus the d1-2B weights (3.57 GiB, not in git): put `model.safetensors` into `models/d1-2B/` (code and license are there) or keep a snapshot at `~/models/d1-2B`. See `D1_NOTES.md`.
- LLM (optional): any OpenAI-compatible server on loopback; GenieX on the board (`LiquidAI/LFM3-1.7B-GGUF:Q4_0`), llama.cpp works on a laptop (`llama-server --jinja`).

## Layout
`server.py` HTTP + UI, `plant.py` live plant loop, `agent.py` observe-decide-act-explain-log, `ask.py` tool calling with allowlist and policy, `extrusion.py` line scenarios and knowledge lookup, `iq9sim/` simulators, rules, LFM client and d1 service, `ui/` console (local fonts), `tests/`, `tools/d1_probe.py`, `logs/` d1 evidence. Mocks are in `../iq9-mocks/`.

(c) Aavinos LLC, Mind Theory AI, and Christian Camacho-Martinez. All rights reserved.
