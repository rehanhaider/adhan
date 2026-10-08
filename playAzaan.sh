#!/usr/bin/env bash
# Play an adhan (or any audio file), running any before/after hooks.
#
# USAGE: playAzaan.sh <audio-path> [<volume-millibels>] [<player>] [<leadin-seconds>]
#
# Player is vlc (the default) or paplay, as set in adhan.toml.
#
# Lead-in is the seconds of silence to play before the file (default 0), so
# that a speaker that is slow to wake up does not lose the start of it (#14).
#
# Volume is given in millibels for backwards compatibility with the original
# omxplayer setup: 0 is nominal, 1500 is loud, -30000 is effectively silent.

set -u

# Put the date and time before each line. printf %(...)T is a bash builtin, so
# this does not need date on PATH.
timestamp() {
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    printf '%(%Y-%m-%d %H:%M:%S)T %s\n' -1 "$line"
  done
}

# All output, from this script, the hooks and the player, goes through
# timestamp(), so each line in adhan.log starts with the date and time. This is
# not a pipe that the script waits for: a hook can start a process that keeps
# the output open, and the script must still exit after the after-hooks.
exec > >(timestamp) 2>&1

if [ $# -lt 1 ]; then
  echo "USAGE: $0 <azaan-audio-path> [<volume-millibels>] [vlc|paplay] [<leadin-seconds>]"
  exit 1
fi

audio_path="$1"
vol_mb="${2:-0}"
player="${3:-vlc}"
# No :- here, so that an empty lead-in is an error and not 0
leadin="${4-0}"
root_dir="$(cd "$(dirname "$0")" && pwd)"

if [ ! -r "$audio_path" ]; then
  echo "Audio file not found or not readable: $audio_path"
  exit 1
fi

# Fail before running any hooks if the configured player cannot run. There is
# deliberately no fallback to another player, see checkPlayer() in
# updateAzaanTimers.py.
case "$player" in
  vlc)    player_cmd=cvlc ;;
  paplay) player_cmd=paplay ;;
  *)
    echo "Unsupported player: $player (use vlc or paplay)"
    exit 1
    ;;
esac
if ! command -v "$player_cmd" > /dev/null 2>&1; then
  echo "Player '$player' is selected but $player_cmd was not found on PATH"
  exit 1
fi

case "$leadin" in
  '' | *[!0-9]*)
    echo "Invalid lead-in: '$leadin' (use a whole number of seconds)"
    exit 1
    ;;
esac
# 10#, so that a leading 0 is not read as octal
leadin=$((10#$leadin))

# The lead-in is real silence, not a pause: cvlc opens no audio stream for
# vlc://pause, so the speaker would not wake up. The file is played once for
# each second. There is a short gap between the files, but PipeWire and
# PulseAudio wait some seconds before they suspend a sink.
silence="$root_dir/media/silence-1s.wav"
if [ "$leadin" -gt 0 ] && [ ! -r "$silence" ]; then
  echo "Silent file not found or not readable: $silence, playing without the lead-in"
  leadin=0
fi
silence_files=()
for ((i = 0; i < leadin; i++)); do
  silence_files+=("$silence")
done

# Convert millibels to a linear gain (1 is nominal), capped at 8 (+18 dB)
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

if [ "$leadin" -gt 0 ]; then
  echo "Playing $leadin seconds of silence before the adhan"
fi
echo "Playing $audio_path with $player at gain $gain (volume $vol_mb)"
case "$player" in
  vlc)
    # --play-and-exit is essential. Without it cvlc stays resident after
    # playback and holds the audio sink open, leaking one process per adhan.
    # Its output goes to the log. Do not add -q: it also hides the errors.
    # The silence is in the same playlist, so one process plays all of it.
    cvlc --play-and-exit --gain "$gain" "${silence_files[@]}" "$audio_path" vlc://quit
    status=$?
    ;;
  paplay)
    # PulseAudio volumes are cubic: 65536 is nominal and the linear gain maps
    # to 65536 * cbrt(gain), the same as pa_sw_volume_from_linear()
    pa_volume=$(awk -v g="$gain" 'BEGIN { printf "%d", 65536 * g ^ (1 / 3) }')
    # A failure of the silence must not stop the adhan
    for file in "${silence_files[@]}"; do
      paplay "$file" || echo "paplay exited $? on the silent file"
    done
    paplay --volume="$pa_volume" "$audio_path"
    status=$?
    ;;
esac
echo "Finished $audio_path with $player, exit status $status"

run_hooks "$root_dir/after-hooks.d" after

exit "$status"
