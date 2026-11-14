#!/usr/bin/env bash
# Starts one headless Gemini CLI agent on one idea, in its own git worktree and branch.
#   scripts/swarm.sh <slug> <model> <prompt file: absolute, or relative to the repo root>
# Env: TURNS (default 120) caps the agent's model turns.
# The agent's output goes to runs/swarm/<slug>.jsonl (stream-json) and <slug>.err.
set -euo pipefail
slug=$1; model=$2; prompt=$3
root=$(git rev-parse --show-toplevel)
case "$prompt" in /*) ;; *) prompt="$root/$prompt" ;; esac
wt="$root/../spread-wt/$slug"
branch="exp/gemini-$slug"
git -C "$root" config extensions.worktreeConfig true
if [ ! -d "$wt" ]; then
  git -C "$root" fetch -q origin main
  git -C "$root" worktree add -q "$wt" -b "$branch" origin/main
fi
cd "$wt"
git config --worktree user.name "Gemini agent ($slug)"
git config --worktree user.email "swarm-dispatch-agents@users.noreply.github.com"
uv sync -q
mkdir -p .gemini "$root/runs/swarm"
cat > .gemini/settings.json <<JSON
{
  "model": { "maxSessionTurns": ${TURNS:-120} },
  "tools": { "shell": { "inactivityTimeout": 1500 } },
  "security": { "auth": { "selectedType": "gemini-api-key" } }
}
JSON
set -a; . "$root/.env"; set +a          # GEMINI_API_KEY and SPREAD_KEY; never committed
: "${GEMINI_API_KEY:?GEMINI_API_KEY is not in .env}"
text="$(cat "$root/experiments/prompts/_common.md")"$'\n'"$(cat "$prompt")"
exec gemini -m "$model" --yolo --skip-trust -o stream-json -p "$text" \
  > "$root/runs/swarm/$slug.jsonl" 2> "$root/runs/swarm/$slug.err"
