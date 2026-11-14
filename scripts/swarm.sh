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
# An agent sometimes ends its turn mid-task ("I will now ...") and the headless session ends with it. So the
# agent is resumed (up to RESUMES times) until its branch is pushed with a note in experiments/.
log=$root/runs/swarm/$slug.jsonl; err=$root/runs/swarm/$slug.err
base=$text
for attempt in $(seq 1 $((${RESUMES:-3} + 1))); do
  gemini -m "$model" --yolo --skip-trust -o stream-json -p "$text" >> "$log" 2>> "$err"
  git fetch -q origin 2>/dev/null
  if git rev-parse -q --verify "origin/$branch" > /dev/null      && [ -n "$(git diff --name-only --diff-filter=AM "origin/main...origin/$branch" -- 'experiments/*.md')" ]      && [ -z "$(git log --oneline "origin/$branch..HEAD")" ]; then
    break
  fi
  echo "swarm.sh: $slug ended without a pushed note (attempt $attempt); resuming" >> "$err"
  text="## Resume (attempt $((attempt + 1))): your previous session in this worktree ended before your note was pushed on \`$branch\`. Your code, commits and runs/ are still here: check \`git status\`, \`git log\` and runs/, and carry on from where you stopped. Don't end your turn by announcing a step: do it. Finish with your note committed and pushed."$'

'"$base"
done
