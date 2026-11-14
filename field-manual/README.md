# Dead-Zone Field Manual
Point the camera at the IQ-9075 EVK, ask aloud, and receive one sourced step.
Eleven local numbered cards come from the IQ-9075 board documentation.
Python standard library only; uses the existing NPU Omni server at localhost:18080.
On the board:
```bash
cd ~/ondev/field-manual
export LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
python3 field_manual.py                  # Enter to capture; Ctrl-C to exit
python3 field_manual.py --once           # one live camera + Calisto question
python3 field_manual.py --once --text 'where do I plug in power?'
python3 field_manual.py --once --image runs/example/frame.jpg --audio question.wav
```
Default recording: 4 seconds; change with `--seconds 6`.
Webcam: /dev/video0 through ~/ondev/scripts/board_capture.sh and tools/ffmpeg.
Calisto: pw-record source 56; spoken answers: pw-play sink 55.
`--no-speak` disables TTS/playback for quiet use.

Why on-device: frames, voice, cards, ASR, reasoning and TTS stay on the board.
The client uses only a fixed loopback endpoint and bypasses proxy settings.
The demo needs no cloud service; SSH is only for deployment and operation.

RMS below -45 dBFS or duration below 0.3 s rejects audio before ASR or Omni.
ASR is displayed; Omni receives both the saved frame and the accepted audio.
Invalid JSON, unknown/null cards and empty steps produce an abstention.
Valid selections always speak the exact local card step, preventing added advice.
`seen` is model-generated and may be wrong; no physical port is visually certified.
Each turn saves media in runs/ and appends timings/results to logs/field-manual.jsonl.
`npu: true` records the supplied server placement, not client-side hardware telemetry.

Verified on board: typed console/power questions and saved speech select sourced cards.
Digital silence is gated; acoustic playback/mic transcription failed (see turn logs).
## Display
Judge-facing page: latest frame, question, step, card, timings, NPU badge, last 10 turns.
Standard library only; works with Wi-Fi off. On the board run:
`python3 display.py --root ~/ondev/field-manual` (serves 127.0.0.1:8765, `--port` to change).
From the laptop: `ssh -N -L 8765:127.0.0.1:8765 iq9`, then open http://localhost:8765
"Wi-Fi is off now" stamps the clock time in the page only; "edit" changes the label.
It re-reads the log every second, so it can start before the first turn.
