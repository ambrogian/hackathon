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
Recommended for the demo: `python3 field_manual.py --loop` (hands-free; use the Calisto mute button as push-to-talk: unmute, speak, mute. Digital silence is treated as muted and never triggers a turn).
Recording is endpointed by voice level (starts above the noise floor, stops after 0.8 s of silence or re-mute); `--seconds N` is the max utterance length (default 8). Without `--loop`, Enter starts a turn and 5 s without speech reports "I didn't hear a question".
`--asr-late` runs ASR after the answer instead of before (about 0.3 s faster, less reliable in testing).
Speech is streamed to the speaker as it is synthesized.
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

## Inspection mode

`inspect_mode.py` compares the live camera (or `--image file`) with a "good" reference and says GOOD / BAD / UNSURE.
The ZETIC d1 model gives P(same as reference) with the reference and current frame as two images
(>0.8 GOOD, <0.2 BAD, otherwise UNSURE). On BAD/UNSURE, LFM3-Omni describes the difference in one
sentence and gives an approximate bounding box (x is good, y can drift), drawn in red with ffmpeg.

```
python3 inspect_mode.py ref good            # save current camera frame as refs/good.jpg
python3 inspect_mode.py ref bad             # optional example of a defect (refs/bad.jpg)
python3 inspect_mode.py ref good --image f.png
echo "a blue circle on the left, white background" > refs/notes.txt   # optional: what "good" means
python3 inspect_mode.py check [--loop] [--image f] [--no-speak]
```
Each check writes runs/<id>/annotated.jpg, speaks the verdict, and appends to logs/field-manual.jsonl
(`step` = verdict + sentence, `gate` = probabilities, plus `verdict`, `bbox`), so display.py shows it.

## Monitoring demo

Stage view at http://localhost:8765/monitor (control image + live input, status line, box, LLM sentence,
timings, Audio placeholder). Buttons on the page: **Monitor** (start/stop mock feed + loop), **Analyze**
(one full pass on the current input), **Reset**. Or from the command line on the board
(stop `camd.sh` first: both write `live/latest.jpg`; the Monitor button does this itself):

```
./camd.sh stop; ./mock_feed.sh 12            # good stills for 12 s, then failure stills (./mock_feed.sh stop)
python3 inspect_mode.py check --loop --no-speak   # input -> monitoring -> inference -> box -> text -> done, then holds
python3 display.py --root ~/ondev/field-manual --port 8765
```
Laptop: `ssh -N -L 8765:127.0.0.1:8765 iq9`, open http://localhost:8765/monitor.
The loop publishes `live/stage.json` (atomic); the page polls `/api/stage` every 0.5 s. After a BAD result the
loop holds it until a GOOD frame returns. The sentence is typed out in the page (not streamed from the model).
Audio: `runs/<id>/answer.wav` is linked if `--no-speak` is omitted.
