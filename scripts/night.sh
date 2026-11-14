#!/usr/bin/env bash
# The overnight lab: runs for HOURS on the swarm host (as `lab`, in ~/spread), unattended:
#   1. a pool of Gemini workers, one idea each (scripts/swarm.sh), from a queue of prompt files;
#   2. when the queue runs dry, a Gemini lead tick reads the night's results and writes new prompts
#      and new sweep lines;
#   3. a sweep track: `lab sweep` / `lab eval` lines, one after another (experiments/night/sweeps.txt,
#      then whatever the lead adds);
#   4. the ranking round's runs with the champion (`lab board --auto --yes`), every 30 minutes;
#   5. every 20 minutes, the night's results (run summaries, sweep tables, worker reports, status) are
#      committed to a worktree and force-pushed to the branch night/<date>, for the morning's analysis.
# Start (detached; it outlives the SSH session):
#   cd ~/spread && HOURS=8 setsid nohup bash scripts/night.sh > runs/night.out 2>&1 < /dev/null &
# Stop it: touch runs/night/stop (running workers and the current sweep finish on their own).
# Add work while it runs: drop a prompt file into runs/night/queue/ (name it NN-slug.md), or append a
# line to runs/night/sweeps-extra.txt (arguments to `uv run lab`, e.g. `sweep --seeds-from dev -g fee_open=0.8,0.9`).
# Env: HOURS (8), MODEL (gemini-4-argon), FALLBACK_MODEL (gemini-3.1-pro-preview: used once MODEL fails 3 times
#      in a row), LEAD_MODEL (= MODEL), MAX_WORKERS (3), TURNS (150),
#      NIGHT_BOARD (1: play the ranking rounds), PUBLISH_BRANCH (night/<UTC date of the start>).
set -uo pipefail
root=$(git rev-parse --show-toplevel)
cd "$root"
export PATH="$HOME/.local/bin:$PATH" PYTHONUNBUFFERED=1
HOURS=${HOURS:-8}; MODEL=${MODEL:-gemini-4-argon}; LEAD_MODEL=${LEAD_MODEL:-$MODEL}
FALLBACK_MODEL=${FALLBACK_MODEL:-gemini-3.1-pro-preview}
MAX_WORKERS=${MAX_WORKERS:-3}; TURNS=${TURNS:-150}; NIGHT_BOARD=${NIGHT_BOARD:-1}
start=$(date +%s); deadline=$((start + $(awk "BEGIN{print int($HOURS * 3600)}")))
night=$root/runs/night; mkdir -p "$night/queue" "$night/started" "$night/logs" runs/swarm
PUBLISH_BRANCH=${PUBLISH_BRANCH:-night/$(date -u +%Y%m%d)}
tag=n$(date -u +%d)                               # slug prefix, so branch names don't clash with earlier nights

exec 9> "$night/night.lock"
flock -n 9 || { echo "night.sh is already running"; exit 1; }
log() { echo "$(date -u +%H:%M:%S) $*" | tee -a "$night/night.txt"; }
alive() { [ -n "${1:-}" ] && [ -e "/proc/$1" ] && ! grep -q '^State:.*Z' "/proc/$1/status" 2>/dev/null; }
echo "$start" > "$night/start"
date -u -d "@$deadline" +%FT%TZ > "$night/deadline"

# Seed the queue from the committed prompts (once per night: a copy already started is not repeated).
for f in experiments/prompts/night/*.md; do
  [ -e "$f" ] || continue
  b=$(basename "$f"); [ -e "$night/started/$b" ] || [ -e "$night/queue/$b" ] || cp "$f" "$night/queue/$b"
done
touch "$night/sweeps-extra.txt" "$night/sweeps.done"
log "night: $HOURS h until $(cat "$night/deadline"), model $MODEL, $MAX_WORKERS workers, publishing to $PUBLISH_BRANCH"

declare -A wpid=() wstart=() wfile=() retries=()
sweep_pid=""; lead_pid=""; board_pid=""; fails=0; hold_until=0
last_lead=0; last_board=0; last_publish=$start

start_worker() {                                  # $1 = prompt file in the queue
  local f=$1 b slug; b=$(basename "$f" .md); slug="$tag-$b"
  mv "$f" "$night/started/$b.md"
  TURNS=$TURNS bash scripts/swarm.sh "$slug" "$MODEL" "$night/started/$b.md" > "$night/logs/$slug.launch.txt" 2>&1 < /dev/null &
  wpid[$slug]=$!; wstart[$slug]=$(date +%s); wfile[$slug]=$b
  printf '%s\t%s\t%s\n' "$slug" "$(date -u +%H:%M)" "$b.md" >> "$night/workers.tsv"
  log "worker $slug started (pid ${wpid[$slug]})"
}

reap_workers() {
  local slug now; now=$(date +%s)
  for slug in "${!wpid[@]}"; do
    alive "${wpid[$slug]}" && continue
    local took=$(( now - wstart[$slug] ))
    log "worker $slug finished after $((took / 60)) min"
    printf '%s\t%s\tdone\t%s min\n' "$slug" "$(date -u +%H:%M)" "$((took / 60))" >> "$night/workers.tsv"
    if [ "$took" -lt 180 ]; then                  # died at once: the API, the key or the CLI; back off
      fails=$((fails + 1)); log "worker $slug died within 3 min ($fails in a row); see runs/swarm/$slug.err"
      local b=${wfile[$slug]}; retries[$b]=$(( ${retries[$b]:-0} + 1 ))
      if [ "${retries[$b]}" -le 2 ]; then mv "$night/started/$b.md" "$night/queue/$b.md" 2>/dev/null && log "$b back in the queue"; fi
      if [ "$fails" -ge 3 ]; then
        if [ "$MODEL" != "$FALLBACK_MODEL" ]; then log "switching workers and lead from $MODEL to $FALLBACK_MODEL"; MODEL=$FALLBACK_MODEL; LEAD_MODEL=$FALLBACK_MODEL; fails=0
        else hold_until=$((now + 900)); log "holding new workers for 15 min"; fi
      fi
    else fails=0; fi
    unset "wpid[$slug]" "wstart[$slug]" "wfile[$slug]"
  done
}

next_sweep() {                                    # prints the first sweep line not yet done
  local line
  cat experiments/night/sweeps.txt "$night/sweeps-extra.txt" 2>/dev/null | sed 's/#.*//; s/[[:space:]]*$//' | grep -E '^(sweep|eval) ' |
  while IFS= read -r line; do
    grep -qxF -- "$line" "$night/sweeps.done" || { printf '%s\n' "$line"; break; }
  done
}

start_sweep() {
  local line n; line=$(next_sweep); [ -n "$line" ] || return 1
  case " $line " in *" board "*|*" final "*|*" promote "*|*" reap "*|*--force*) echo "$line" >> "$night/sweeps.done"; log "refused sweep line: $line"; return 0 ;; esac
  printf '%s\n' "$line" >> "$night/sweeps.done"
  n=$(wc -l < "$night/sweeps.done")
  local -a args; read -ra args <<< "$line"
  ( echo "# uv run lab $line"; echo "# started $(date -u +%FT%TZ)"; uv run lab "${args[@]}"; echo "# exit $? at $(date -u +%FT%TZ)" ) \
    > "$night/logs/sweep-$(printf %02d "$n").txt" 2>&1 < /dev/null &
  sweep_pid=$!; log "sweep $n started: $line"
}

lead_tick() {                                     # a Gemini lead writes new prompts and sweep lines
  local wt=$root/../spread-wt/night-lead
  git fetch -q origin
  [ -d "$wt" ] || git worktree add -q --detach "$wt" origin/main
  git -C "$wt" reset -q --hard origin/main; git -C "$wt" clean -qfd
  mkdir -p "$wt/night-queue" "$wt/.gemini"
  printf '{ "model": { "maxSessionTurns": 60 }, "security": { "auth": { "selectedType": "gemini-api-key" } } }\n' > "$wt/.gemini/settings.json"
  python3 scripts/night_status.py --lead > "$wt/night-queue/INPUT.md" 2>&1
  local text; text="$(cat experiments/prompts/_night-lead.md)"
  ( cd "$wt" && set -a && . "$root/.env" && set +a &&
    timeout 40m gemini -m "$LEAD_MODEL" --yolo --skip-trust -o stream-json -p "$text" \
      > "$night/logs/lead-$(date -u +%H%M).jsonl" 2>> "$night/logs/lead.err"
    # take what it wrote
    k=0
    for f in night-queue/*.md; do
      case "$(basename "$f")" in INPUT.md) continue ;; LEDGER.md) { echo; echo "## lead tick $(date -u +%H:%M)"; cat "$f"; } >> "$night/LEDGER.md"; continue ;; esac
      k=$((k + 1)); [ "$k" -le 6 ] || break
      cp "$f" "$night/queue/$(date -u +%H%M)$k-$(basename "$f" | sed 's/^[0-9]*-//')"
    done
    [ -f night-queue/sweeps.txt ] && grep -E '^(sweep|eval) ' night-queue/sweeps.txt | head -12 >> "$night/sweeps-extra.txt"
    true ) < /dev/null &
  lead_pid=$!; last_lead=$(date +%s); log "lead tick started (pid $lead_pid)"
}

publish() {
  local wt=$root/../spread-wt/night-results dest
  if [ ! -d "$wt" ]; then
    git worktree add -q --detach "$wt" origin/main || return
    git -C "$wt" switch -q --orphan "night-results-$(date +%s)"
  fi
  dest=$wt/$(date -u -d "@$start" +%Y%m%d-%H%M); mkdir -p "$dest/runs" "$dest/workers" "$dest/logs"
  git fetch -q origin 2>/dev/null
  python3 scripts/night_status.py > "$dest/STATUS.md" 2>&1
  find runs -mindepth 1 -maxdepth 1 -type d -newer "$night/start" ! -name night ! -name swarm | while read -r d; do
    mkdir -p "$dest/runs/$(basename "$d")"
    cp "$d"/meta.json "$d"/summary.json "$d"/results.jsonl "$dest/runs/$(basename "$d")/" 2>/dev/null
  done
  cp "$night"/logs/sweep-*.txt "$dest/logs/" 2>/dev/null
  cp "$night/night.txt" "$night/workers.tsv" "$night/LEDGER.md" "$dest/" 2>/dev/null
  [ -f runs/board.log ] && cp runs/board.log "$dest/board.txt"
  python3 scripts/night_status.py --reports "$dest/workers" > /dev/null 2>&1
  git -C "$wt" add -fA . && git -C "$wt" commit -qm "Night results $(date -u +%FT%H:%MZ)" >/dev/null 2>&1
  for i in 1 2 3 4; do git -C "$wt" push -qf origin "HEAD:refs/heads/$PUBLISH_BRANCH" && break; sleep $((i * 15)); done
  last_publish=$(date +%s); log "published to $PUBLISH_BRANCH"
}

while :; do
  now=$(date +%s)
  stopping=0; { [ "$now" -ge "$deadline" ] || [ -e "$night/stop" ]; } && stopping=1
  reap_workers
  if [ "$stopping" = 0 ]; then
    # workers
    while [ "${#wpid[@]}" -lt "$MAX_WORKERS" ] && [ "$now" -ge "$hold_until" ]; do
      f=$(ls "$night/queue"/*.md 2>/dev/null | sort | head -1); [ -n "$f" ] || break
      start_worker "$f"; sleep 20
    done
    # an empty queue: ask the lead for more (at most every 20 minutes, never two at once)
    if [ -z "$(ls "$night/queue"/*.md 2>/dev/null)" ] && ! alive "$lead_pid" && [ $((now - last_lead)) -ge 1200 ] \
       && [ "$now" -lt $((deadline - 2700)) ]; then lead_tick; fi
    # sweeps
    alive "$sweep_pid" || start_sweep || true
    # ranking rounds
    if [ "$NIGHT_BOARD" = 1 ] && ! alive "$board_pid" && [ $((now - last_board)) -ge 1800 ]; then
      ( echo "# $(date -u +%FT%TZ)"; uv run lab board --auto --yes ) >> "$night/logs/board.txt" 2>&1 < /dev/null &
      board_pid=$!; last_board=$now
    fi
  fi
  [ $((now - last_publish)) -ge 1200 ] && publish
  if [ "$stopping" = 1 ] && [ "${#wpid[@]}" = 0 ] && ! alive "$sweep_pid" && ! alive "$lead_pid" && ! alive "$board_pid"; then
    publish; log "night over"; exit 0
  fi
  sleep "${TICK:-60}"
done
