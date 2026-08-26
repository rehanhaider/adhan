#!/usr/bin/env bash
# Play an adhan (or any audio file) through VLC, running any before/after hooks.
#
# USAGE: playAzaan.sh <audio-path> [<volume-millibels>]
#
# Volume is given in millibels for backwards compatibility with the original
# omxplayer setup: 0 is nominal, 1500 is loud, -30000 is effectively silent.

set -u

if [ $# -lt 1 ]; then
  echo "USAGE: $0 <azaan-audio-path> [<volume-millibels>]"
  exit 1
fi

audio_path="$1"
vol_mb="${2:-0}"
root_dir="$(cd "$(dirname "$0")" && pwd)"

if [ ! -r "$audio_path" ]; then
  echo "Audio file not found or not readable: $audio_path"
  exit 1
fi

# VLC takes a linear gain (0 - 8, where 1 is nominal) rather than millibels
gain=$(awk -v mb="$vol_mb" 'BEGIN {
  g = 10 ^ (mb / 2000)
  if (g > 8) g = 8
  printf "%.4f", g
}')

run_hooks() {
  hook_dir="$1"
  label="$2"
  for hook in "$hook_dir"/*; do
    # Skip the glob itself when the directory is empty, and any file that has
    # not been made executable with chmod u+x
    [ -x "$hook" ] || continue
    echo "Running $label hook: $hook"
    "$hook" || echo "$label hook exited $?: $hook"
  done
}

# Cron gives us no session, so point at the user's PulseAudio/PipeWire socket
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

run_hooks "$root_dir/before-hooks.d" before

# --play-and-exit is essential. Without it cvlc stays resident after playback
# and holds the audio sink open, leaking one process per adhan.
cvlc --play-and-exit --gain "$gain" "$audio_path" vlc://quit > /dev/null 2>&1
status=$?

run_hooks "$root_dir/after-hooks.d" after

exit "$status"
