# Arduino Project Hub post

## Title

Dead-Zone Field Manual: camera, voice, one grounded step, fully offline

## Short description (under 140 characters)

Point a camera at equipment, ask aloud, hear one step from a manual that never leaves the board. Runs offline on a Qualcomm NPU.

## Hardware

- Qualcomm Dragonwing IQ-9075 EVK (Hexagon v73 NPU), Ubuntu 24.04
- USB webcam
- Plantronics Calisto 3200 USB speakerphone (microphone and speaker)
- 12 V power adapter; micro-USB cable for the debug UART console

## Software

- Liquid AI LFM3-Omni-2B (Q4_0 GGUF, image + audio + text in, text + audio out)
- llama.cpp b12323 with the ggml-hexagon backend (NPU), projector on a second NPU session
- Patched Hexagon v73 HTP library (fp16 fix in the HVX activation quantizer)
- Python 3 standard library only for the app (field_manual.py)
- PipeWire (pw-record, pw-play) and ffmpeg for audio and webcam capture

## Story

### Problem

Technicians work where networks do not: basements, plant rooms, aircraft, remote sites.
Their manuals are PDFs they cannot search with gloves on, and a cloud assistant is useless
with no signal, risky when the documentation or the camera view is confidential, and
billed per call. They need one correct next step, hands free, from the manual they are
allowed to use.

### What it does

You point a webcam at the equipment and ask a question aloud. The app answers with ONE
step, spoken through the speakerphone and shown on screen, taken from a local manual.
Unrelated questions get "I can't match that to the manual". Silence gets "I didn't hear a
question". Nothing leaves the board.

For the hackathon the equipment is the IQ-9075 board itself. The manual is 11 numbered
cards built from Qualcomm's "Set up the device" page for the IQ-9075 EVK (offline copy):
power, debug console, USB ports, DisplayPort, Ethernet, camera switches, speaker, microphone,
fan, and Wi-Fi hardware. At the demo, the judge watches us turn the board's Wi-Fi off, then
ask a question out loud and hear the answer.

### How it works

1. A silence gate checks the recording first (below -45 dBFS RMS or under 0.3 s is rejected).
   Without it the model transcribes silence as "thank you."
2. One request goes to LFM3-Omni-2B on the NPU: the camera frame, the spoken question,
   and the manual cards.
3. The model must return JSON `{"card": ..., "step": ..., "seen": ...}`. A validator
   rejects invalid JSON, unknown cards, and empty steps, in which case the app abstains.
4. For a valid card the app speaks the card's exact step from the local manual, so the
   model cannot add advice of its own. The field `seen` (what the model thinks the camera
   shows) is logged but never trusted as proof.
5. Speech comes from the same model server (/v1/audio/speech) and plays on the speakerphone.
   Every turn is appended to a JSONL log with the transcript, card, timings, and validation.

The runtime is llama.cpp's Hexagon backend. We patched the v73 HTP library to fix an fp16
precision bug in the HVX activation quantizer; before the fix LFM3 misread fine print.

### Results (measured on the board)

| Measurement | NPU | CPU |
|---|---|---|
| Image + spoken question, first text | 0.8 s | 3.5 s |
| Decode | ~37 tok/s | ~39-41 tok/s |
| Text answer, first text | 0.15 s | n/a |
| Test clip transcription | exact, 0.35 s to first text | n/a |
| Speech output per sentence (on board) | ~2.2-3.6 s | n/a |

Laptop CPU check: LFM3-Omni speech judged by faster-whisper had 0 word errors in 108 words
(ten sentences). Honest limits: peak memory and long-run endurance were not measured; the
`seen` description can be wrong; card-selection accuracy is not measured as a rate.

Why not a cloud API call: the network is the thing that is missing, the camera view and
manual can be sensitive, the first answer arrives in under a second, and there is no
per-call cost.

### What's next

- Swap in a real maintenance manual by editing one JSON file of cards.
- Measure card-selection accuracy over a question set, and peak memory and endurance.
- Multi-step procedures with "next step" and "repeat" voice commands.
- Ground the visual check: confirm the part in view matches the card before speaking.

## Code files to attach

Attach the full source, not only a link:

- field-manual/field_manual.py (the app, about 250 lines)
- field-manual/manual.json (the 11 cards)
- field-manual/manual-setup.json (serial-console setup cards)
- field-manual/README.md (usage and options)
- README.md (project write-up)
- Link to the public GitHub repository alongside the attached files.

## Credits

Liquid AI (LFM3-Omni), Qualcomm (IQ-9075 EVK and its setup documentation), llama.cpp.
