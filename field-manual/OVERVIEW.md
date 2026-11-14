# Dead-Zone Field Manual

Event: "Cleared for Takeoff", Qualcomm x Liquid AI on-device hackathon, San Francisco, 2026-11-13.
Board: Qualcomm Dragonwing IQ-9075 EVK (Hexagon v73 NPU, Ubuntu 24.04).

## Pitch

Point a camera at a piece of equipment, ask a question out loud, and get ONE grounded
step read back to you from a manual that never leaves the device. The model is
LiquidAI's LFM3-Omni-2B running on the board's NPU. It sees the camera frame and hears
the question in a single request, picks the one relevant card from a local manual, and
the app speaks that card's exact step. No network is used at any point, so it still works
in a basement, a cockpit, a plant room, or with the Wi-Fi switched off in front of a judge.

In the demo the equipment is the IQ-9075 board itself, and the manual is built from
Qualcomm's "Set up the device" page for the IQ-9075 EVK (offline copy).

## Demo flow (what the judge sees)

1. The board runs the app with a USB webcam and a Plantronics Calisto 3200 speakerphone attached.
2. From the micro-USB UART console (not SSH over Wi-Fi) we run `sudo nmcli radio wifi off`
   and `nmcli -p device` so the judge sees Wi-Fi is disconnected. Ethernet is unplugged.
3. Aim the camera at the board and ask, for example, "Where do I plug in power?"
4. The app prints the transcript, the chosen card number and its source, then speaks one step.
5. Ask something unrelated: the app says it cannot match the question to the manual
   instead of inventing an answer. Stay silent: it says it did not hear a question.
6. Open `logs/field-manual.jsonl` to show the local record: transcript, card, step,
   per-stage timings, validation result.

## Architecture

```
USB webcam --+
             +--> silence gate --> LFM3-Omni-2B on NPU --> JSON {card, step} --> validator
Calisto mic -+    (RMS/duration)    (frame + audio +                              |
                                     manual cards)                                v
                                                          spoken step (/v1/audio/speech)
                                                          + JSONL log + saved media
```

- Capture: one frame from the webcam, a few seconds of audio from the speakerphone.
- Silence gate: audio below -45 dBFS RMS or shorter than 0.3 s is rejected before any
  model call. This matters because the model transcribes silence as "thank you."
- Model: LFM3-Omni-2B Q4_0 via llama.cpp b12323 with the ggml-hexagon backend on the NPU;
  the vision/audio projector runs in a second NPU session. The client sends the saved
  frame, the accepted audio, and the manual cards in one request.
- Output contract: the model must return JSON `{"card": int or null, "step": "...", "seen": "..."}`.
  The validator rejects invalid JSON, unknown or null cards, and empty steps (the app abstains).
  For a valid card the app speaks the exact step text from the local manual, so the model
  cannot add advice. `seen` is the model's description of the frame, logged for review only.
- Speech: the same Omni server's `/v1/audio/speech`, played on the speakerphone.
- Log: every turn appends timings and results to `logs/field-manual.jsonl`.

The client talks only to a fixed loopback address (127.0.0.1:18080) and bypasses proxy settings.

## Why on-device (and not a cloud API call)

- Dead zones: the use case is equipment in places with no signal. The core workflow
  must work when the network is gone, and the demo proves it by switching Wi-Fi off.
- Privacy: camera frames, voice, and the manual (often proprietary maintenance
  documentation) stay on the board.
- Latency: first text 0.8 s from a frame plus a spoken question, with no network round trip.
- Flat cost: no per-token or per-image API bill, however often a technician asks.
- Grounding: the answer is a card from a local manual, not whatever a remote model recalls.

## Measured numbers (IQ-9075 board, 2026-11-13)

| Measurement | NPU | CPU |
|---|---|---|
| Image + spoken question in one request, time to first text | 0.8 s | 3.5 s |
| Decode speed | ~37 tok/s | ~39-41 tok/s |
| Text-only answer, time to first text | 0.15 s | not measured |
| Transcription of a test clip | exact, 0.35 s to first text | not measured |
| Speech output, per sentence | ~2.2-3.6 s (on board) | not measured |

Other checks:
- Independent laptop CPU check: LFM3-Omni speech output transcribed by faster-whisper
  had 0 word errors out of 108 words over ten sentences.
- The NPU's win is prefill (reading the image and audio); decode speed is about the same as CPU.
- Our patched v73 HTP library fixes an fp16 precision bug in the HVX activation
  quantizer that made LFM3 misread fine print. Source for the patch lives in the team's
  Hexagon bring-up work, not in this folder.

## Run it on the board

The model server (llama.cpp with ggml-hexagon, Omni on the NPU) must already be listening on
127.0.0.1:18080. Then:

```bash
cd ~/ondev/field-manual
python3 field_manual.py                       # Enter to capture; Ctrl-C to exit
python3 field_manual.py --once --text 'where do I plug in power?'
```

Full options, devices, and the manual card format: [field-manual/README.md](field-manual/README.md).
The code is Python standard library only.

## Verified vs not verified

Verified (measured on the board, see the numbers above): NPU timings for image + audio
requests, text answers, transcription of a test clip, on-board speech output, the laptop
speech check, and the silence-gate need.

Not verified or only partly verified:
- A long endurance run; peak process memory (not measured).
- Whether the model's `seen` field is accurate; it can be wrong, and no physical port
  is visually certified by the app. The spoken step always comes from the card.
- Accuracy of card selection across many questions and lighting conditions: not measured
  as a rate.
- The final end-to-end live turn (camera + speakerphone + speech) in the finished app
  was still being validated at the time of writing; see logs/reports/field-manual.md.
- A full Wi-Fi-off rehearsal of the finished app should be confirmed by the demo run.

## Credits

- Liquid AI: LFM3-Omni-2B model.
- Qualcomm: Dragonwing IQ-9075 EVK, Hexagon NPU, and the "Set up the device" documentation
  the manual cards are drawn from.
- llama.cpp (b12323, ggml-hexagon backend) for the runtime.
- Hackathon organizers for the reference kit and board setup guide.
