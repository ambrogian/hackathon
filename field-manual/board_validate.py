#!/usr/bin/env python3
"""Repeatable board-only acoustic test; no service or audio configuration changes."""
import os
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import subprocess
import sys
import threading
import time
from pathlib import Path
import field_manual as fm

root = Path(__file__).resolve().parent
fixture = root / 'runs' / 'fixtures'
fixture.mkdir(parents=True, exist_ok=True)
question = fixture / 'spoken-question.wav'
start = time.monotonic()
question.write_bytes(fm.request('/v1/audio/speech',
    {'input': 'Where do I plug in power?', 'response_format': 'wav'}, binary=True))
print('Question TTS seconds:', round(time.monotonic()-start, 3), flush=True)
players = []
def play():
    time.sleep(0.8)
    result = subprocess.run(['pw-play', '--target', '55', str(question)], capture_output=True, text=True, timeout=30)
    print('Acoustic question playback exit:', result.returncode, flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
proc = subprocess.Popen([sys.executable, str(root / 'field_manual.py'), '--once', '--seconds', '6'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
for line in proc.stdout:
    print(line, end='', flush=True)
    if line.startswith('Recording question...'):
        player = threading.Thread(target=play)
        players.append(player)
        player.start()
code = proc.wait()
for player in players:
    player.join()
sys.exit(code)
