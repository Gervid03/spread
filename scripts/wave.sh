#!/usr/bin/env bash
# Starts a wave of agents, one per idea, 30 s apart (worktree creation takes git's lock), detached from
# the terminal so they outlive the SSH session.
#     TURNS=120 scripts/wave.sh <model> <slug> [<slug> ...]
# Each agent's brief is experiments/prompts/gemini-<slug>.md; see scripts/swarm.sh for the rest.
set -euo pipefail
model=$1; shift
root=$(git rev-parse --show-toplevel)
mkdir -p "$root/runs/swarm"
for slug in "$@"; do
  setsid nohup bash "$root/scripts/swarm.sh" "$slug" "$model" "experiments/prompts/gemini-$slug.md" \
    > "$root/runs/swarm/$slug.launch.log" 2>&1 < /dev/null &
  echo "started $slug"
  sleep 30
done
