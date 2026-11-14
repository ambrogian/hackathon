#!/usr/bin/env bash
# Persistent camera feed: keeps the newest webcam frame in live/latest.jpg (written atomically, 4 per second),
# so a turn grabs a frame instantly instead of opening the camera each time.
#   ./camd.sh            start in the background (logs to live/camd.log)
#   ./camd.sh stop       stop it
set -u
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"; mkdir -p live
FF=${FFMPEG:-$HOME/ondev/tools/ffmpeg}; DEV=${CAM:-/dev/video0}
if [[ ${1:-} == stop ]]; then [[ -f live/camd.pid ]] && kill -TERM "$(cat live/camd.pid)" 2>/dev/null; rm -f live/camd.pid; exit 0; fi
if [[ -f live/camd.pid ]] && kill -0 "$(cat live/camd.pid)" 2>/dev/null; then echo "camd already running"; exit 0; fi
setsid nohup "$FF" -hide_banner -loglevel error -f v4l2 -input_format mjpeg -video_size 1280x720 -framerate 15 -i "$DEV" \
  -vf fps=4 -q:v 3 -f image2 -update 1 -atomic_writing 1 -y live/latest.jpg > live/camd.log 2>&1 &
echo $! > live/camd.pid; echo "camd started (pid $!)"
