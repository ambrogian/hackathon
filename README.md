# hackathon

Offline troubleshooting assistant for a polycarbonate sheet extrusion line. An operator photographs a defect; a local vision model on a Qualcomm device names it and tells the operator where on the line to intervene.

## Knowledge base

| File | What it is |
|---|---|
| `kb/line.json` | Line layout (zones Z1-Z12), safety rules, triage by visual pattern |
| `kb/defects.json` | 16 defects: visual signature, origin zones, causes, operator steps, escalation |
| `kb/system_prompt.md` | Prompt template for the model; `{{CONTEXT}}` is replaced with `kb/context.txt` |
| `kb/build.py` | Validates the JSON and generates `KNOWLEDGE_BASE.md` and `kb/context.txt` |
| `KNOWLEDGE_BASE.md` | Readable version (generated, don't edit by hand) |

Edit the JSON, then run `python3 kb/build.py`.

Content is general PC sheet extrusion process knowledge, not a specific OEM manual. Typical values must be replaced with the real line's setpoints and reviewed by a process engineer before use on a real line.

Reference images (third-party, credited, not committed) live in `images/candidates/`.

## On the IQ-9075: camera, voice and NPU runtime (`field-manual/`)

The board-side app that runs the assistant on the Qualcomm Dragonwing IQ-9075, fully offline: live USB camera,
speakerphone push-to-talk, LFM3-Omni-2B on the Hexagon NPU (llama.cpp ggml-hexagon), answers grounded in a local
knowledge base with the cited entry, spoken replies, a JSONL log and a judge display. See
[`field-manual/README.md`](field-manual/README.md) and [`field-manual/OVERVIEW.md`](field-manual/OVERVIEW.md)
(architecture and measured numbers).
