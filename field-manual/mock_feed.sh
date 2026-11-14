#!/usr/bin/env bash
# Mock camera for the monitoring demo: writes live/latest.jpg (atomic) from the demo stills, one per second.
#   ./mock_feed.sh [seconds_good=12]   good stills for N s, then failure stills forever (background)
#   ./mock_feed.sh stop
# Stop camd.sh first (./camd.sh stop): both write live/latest.jpg.
set -u
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"; mkdir -p live
if [[ ${1:-} == stop ]]; then [[ -f live/mock.pid ]] && kill -TERM "$(cat live/mock.pid)" 2>/dev/null; rm -f live/mock.pid; exit 0; fi
N=${1:-12}
[[ -f live/mock.pid ]] && kill -0 "$(cat live/mock.pid)" 2>/dev/null && { echo "mock_feed already running"; exit 0; }
(
  i=0; start=$SECONDS
  while true; do
    if (( SECONDS - start < N )); then set=(working_machine_25 working_machine_50 working_machine_75 working_machine_50)
    else set=(failure_25 failure_50 failure_75 failure_50); fi
    cp "demo-images/${set[i % 4]}.jpg" live/.latest.tmp && mv -f live/.latest.tmp live/latest.jpg
    i=$((i+1)); sleep 1
  done
) > live/mock.log 2>&1 &
echo $! > live/mock.pid; echo "mock feed started (pid $!), good for ${N}s then failure"
