#!/usr/bin/env bash
# Starts a round of Carbon agents from the briefs in $DIR (default experiments/prompts/r4): _<dir>.md + <slug>.md.
#   bash scripts/tas-swarm.sh               all four: tas-price tas-fees tas-routes tas-state
#   bash scripts/tas-swarm.sh tas-price     one of them (start tas-price first if you start them one by one)
#   bash scripts/tas-swarm.sh --restart     stop the running ones and start them again with the briefs as they are
#                                           now on $SRC (their worktrees, commits and notes stay)
# The briefs ($DIR/) and the instrument (scripts/tas.py) live on the branch $SRC. It need not
# be merged into main: each agent's worktree and branch (exp/gemini-<slug>) start from it.
# Env: SRC (default main), MODEL (gemini-4-carbon), TURNS (300), RESUMES (3).
# Slots: fork-heavy TAS runs take turns, two at a time (TAS_LANES in the agents' environment), so the track
# holds at most 4 of the team's 8 practice slots and the other agents keep the rest.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
SRC=${SRC:-main}
DIR=${DIR:-experiments/prompts/r4}
MODEL=${MODEL:-gemini-4-carbon}
restart=0
if [ "${1:-}" = "--restart" ]; then restart=1; shift; fi
git -C "$root" fetch -q origin "$SRC"
ref="origin/$SRC"
[ $# -gt 0 ] || set -- $(git -C "$root" ls-tree --name-only "$ref:$DIR" | grep -v "^_" | sed "s/.md$//")
mkdir -p "$root/runs/swarm"
for slug in "$@"; do
  pidfile="$root/runs/swarm/$slug.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    if [ "$restart" = 0 ]; then echo "$slug: already running (pid $(cat "$pidfile")); --restart starts it again"; continue; fi
    pid=$(cat "$pidfile")
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true    # the agent's own process group, by its pid file
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -KILL -- "-$pid" 2>/dev/null || true
    echo "$slug: stopped (pid $pid)"
  fi
  if ! git -C "$root" cat-file -e "$ref:$DIR/$slug.md" 2>/dev/null; then
    echo "$slug: no brief $DIR/$slug.md on $ref"; continue
  fi
  wt="$root/../spread-wt/$slug"
  branch="exp/gemini-$slug"
  if [ -d "$wt" ]; then      # a second start: bring the tools and briefs of $SRC into the agent's branch
    git -C "$wt" merge -q --no-edit "$ref" > /dev/null 2>&1 || { git -C "$wt" merge --abort 2>/dev/null; echo "$slug: could not merge $ref into its worktree (the agent can: git merge $ref)"; }
  fi
  if [ ! -d "$wt" ]; then
    if git -C "$root" rev-parse -q --verify "refs/heads/$branch" > /dev/null; then
      git -C "$root" worktree add -q "$wt" "$branch"          # a second start: keep the agent's work
    else
      git -C "$root" worktree add -q "$wt" -b "$branch" "$ref"
    fi
  fi
  prompt="$root/runs/swarm/$slug.prompt.md"
  { git -C "$root" show "$ref:$DIR/_$(basename "$DIR").md"; echo; git -C "$root" show "$ref:$DIR/$slug.md"; } > "$prompt"
  ( cd "$root"
    BASE="$ref" TURNS="${TURNS:-300}" RESUMES="${RESUMES:-3}" setsid nohup bash "$wt/scripts/swarm.sh" "$slug" "$MODEL" "$prompt" > /dev/null 2>&1 < /dev/null &
    echo $! > "$pidfile" )
  echo "$slug: started ($MODEL, ${TURNS:-300} turns, branch $branch from $ref, log runs/swarm/$slug.jsonl)"
done
echo "Watch: tail -f runs/swarm/<slug>.err · cat experiments/LEDGER.md"
