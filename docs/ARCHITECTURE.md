# Architecture

Everything runs on one Qualcomm device next to the line. No cloud, no network.

## Photo diagnosis

```
Phone or webcam photo of the sheet
        │
        ▼
Browser page (showcase/), served from the device at http://localhost:8000
        │  POST /api/diagnose  {photo}
        ▼
Bridge (small Python server on the device)
  1. Builds the prompt: kb/system_prompt.md + kb/context.txt + the photo
  2. Sends it to the local model runtime (Ollama, localhost:11434)
  3. The model returns only:
       { "defect_id": one of the 16 ids, or "none" / "unclear",
         "confidence": "high" | "medium" | "low",
         "why": one sentence about what it sees }
     The runtime enforces this JSON shape, so the answer always parses.
  4. Looks the id up in kb/defects.json: zone, fix steps, fixed-when,
     escalate-if, safety rule
        │
        ▼
Page shows the diagnosis: highlights the zone on the line diagram,
the model's reason, and the steps from the knowledge base
```

**Design choice: the model picks, the knowledge base instructs.** A small on-device model is good at recognising a pattern in a photo and unreliable at writing procedures. The model therefore only chooses a defect from a fixed list. Every step the operator sees is copied from the knowledge base, which a process engineer reviews.

The knowledge base helps the model choose by first sorting defects by visual pattern (lines along the sheet, lines across, random spots, whole surface, shape, edges, film). A small model picks more reliably from two or three candidates than from sixteen.

## Sensor alerts

```
Line signals (temperatures, pressures, currents, torque, thickness gauge)
        │
        ▼
Detection rules (scenarios/diagnose.py), one per failure mode
        │
        ▼
Same knowledge base lookup: zone, part, safety rule, repair playbook
```

Sensors catch some failures before any defect reaches the sheet. For example, a dryer heater failure is visible in the heater current about 2.5 hours before wet resin causes bubbles.

## Model and runtime

| Item | Choice |
|---|---|
| Runtime | Ollama (has a Windows on ARM build for Snapdragon devices) |
| Model | `qwen3.5:2b`, a 2B-parameter model that accepts images |
| Prompt size | About 4,000 tokens of knowledge base, plus the image |
| Setup | `ollama pull qwen3.5:2b` while online. After that, no network needed |

## Status

| Part | Status |
|---|---|
| Knowledge base | Built; `kb/build.py` checks every cross-reference |
| Sensor rules | Built; tested on simulated data for four failure modes |
| Assistant page | Built; diagnoses are scripted from the knowledge base |
| Model runtime | Answers image questions locally with the model above, about 1 s per photo on a laptop. Not yet measured on the Qualcomm device, and not yet tested on real defect photos |
| Bridge (photo → model → page) | Next step |

## Open risks

- **Accuracy:** a 2B model may confuse similar defects, such as die lines and roll scratches. It needs testing on real defect photos.
- **Speed:** time per photo on the target device still has to be measured.
- **Knowledge base:** based on general polycarbonate practice. It needs review against the real line's manual and setpoints.
