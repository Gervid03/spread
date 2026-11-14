#!/usr/bin/env bash
# One chat turn with a Carbon agent, as lab: echo "message" | chat-turn.sh <name>
# The turn runs detached (a dropped SSH connection doesn't stop it); this script streams its output until it ends.
# chat-turn.sh <name> --last   prints the last turn's output again (e.g. after a disconnect).
n=${1:?name}; wt=$HOME/spread-wt/$n; dir=$HOME/chat-logs/$n; mkdir -p "$dir"
if [ "${2:-}" = "--last" ]; then f=$(ls -t "$dir"/*.log 2>/dev/null | head -1); [ -n "$f" ] && cat "$f"; exit 0; fi
MSG=$(cat); [ -n "$MSG" ] || exit 0
exec 9>"$dir/.lock"
if ! flock -n 9; then echo "($n is still working on the previous message; wait for it, or type /last)"; exit 0; fi
log="$dir/$(date +%m%d-%H%M%S).log"; : > "$log"
export MSG log wt
setsid nohup bash -c '
  set -a; . "$HOME/spread/.env"; set +a
  export PATH="$HOME/.local/bin:$PATH" TAS_LANES=2
  cd "$wt" && gemini -m gemini-4-carbon --yolo --skip-trust -o text --resume latest -p "$MSG" >> "$log" 2>&1
  echo "[[turn done]]" >> "$log"' 9>&- > /dev/null 2>&1 < /dev/null &
tail -n +1 -f "$log" | sed -u -e '/YOLO mode is enabled/d' -e '/^\[\[turn done\]\]$/q'
