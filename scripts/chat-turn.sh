#!/usr/bin/env bash
# One chat turn with a Carbon agent, as lab: echo "message" | chat-turn.sh <name>
# The turn runs detached (a dropped SSH connection doesn't stop it); this script streams its progress until it ends:
# each tool call as one "> tool: what" line, then the agent's answer.
# chat-turn.sh <name> --last   prints the last turn again (e.g. after a disconnect).
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
  render='"'"'if .type=="tool_use" then "\n  > " + .tool_name + ": " + ((.parameters.description // .parameters.title // .parameters.command // .parameters.file_path // .parameters.pattern // "") | tostring | gsub("\n"; " ") | .[0:170]) + "\n"
    elif .type=="tool_result" and .status != "success" then "  ! " + ((.output // .error // "") | tostring | gsub("\n"; " ") | .[0:170]) + "\n"
    elif .type=="message" and .role=="assistant" then (.content // "")
    else empty end'"'"'
  cd "$wt" && gemini -m gemini-4-carbon --yolo --skip-trust -o stream-json --resume latest -p "$MSG" 2>> "$log.err" | tee -a "$log.jsonl" | jq --unbuffered -rj "$render" >> "$log"
  printf "\n[[turn done]]\n" >> "$log"' 9>&- > /dev/null 2>&1 < /dev/null &
tail -n +1 -f "$log" | sed -u -e '/^\[\[turn done\]\]$/Q'
