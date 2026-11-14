#!/usr/bin/env bash
# The only road to main for a new champion. Merges a candidate branch onto origin/main in a fresh worktree,
# measures it against the current champion, and pushes main (fast-forward only) when every gate passes.
#   scripts/promote.sh <branch> [-s key=value ...]       the flags are the candidate's full set of overrides
# Run it on the swarm host as `lab` (it needs .env). It takes ~4-8 minutes of practice slots (16 dev worlds,
# 16 holdout worlds, one restarted world), and waits out the quiet hours like every eval.
# Gates (the numbers are checked by scripts/promote_gate.py):
#   - before the freeze: Sun 15 Nov 06:00 Helsinki (04:00 UTC);
#   - the merge is clean and touches only src/spread_lab/{policy,notes}.py, src/spread_lab/policies/,
#     experiments/, night-queue/ or README.md (never the instrument, seeds/, champion/ or scripts/);
#   - the code imports;
#   - dev: SAFE, and paired Δ vs the champion > 0 with t >= 2;
#   - holdout: every world ranked, Δ >= 0, no more worlds under 92% than the champion, on-time minimum no more
#     than 0.5 points below the champion's;
#   - a restart at Wednesday 12:00 (dev-01) finishes ranked.
# Then: `lab promote` dev and holdout, a line in experiments/PROMOTIONS.md, one commit, `git push origin HEAD:main`.
# If main moved meanwhile the push is refused: run it again. DRY=1 runs every gate but doesn't commit or push.
# REBASE=1: a neutral instrument change (e.g. the practice step, scripts/promote_gate.py --rebase): it may also touch
# src/spread_lab/runner.py, and dev needs |Δ| <= max(€200, 2 SE) instead of a gain; the tail gates stay.
# Exit codes: 0 promoted (or DRY passed) · 2 frozen · 3 merge · 4 files · 5 import · 6 restart · 7 gates · 8 push.
set -euo pipefail
branch=${1:?usage: scripts/promote.sh <branch> [-s key=value ...]}; shift
branch=${branch#origin/}
flags=("$@")
root=$(git rev-parse --show-toplevel)
export PATH="$HOME/.local/bin:$PATH" PYTHONUNBUFFERED=1
say() { echo "promote: $*"; }

[ "$(date -u +%s)" -lt "$(date -u -d 2026-11-15T04:00:00Z +%s)" ] || { say "refused: past the freeze (Sun 06:00 Helsinki)"; exit 2; }

ts=$(date -u +%Y%m%d-%H%M%S); wt="$root/../spread-wt/promote-$ts-$$"
git -C "$root" fetch -q origin
git -C "$root" worktree add -q --detach "$wt" origin/main
cd "$wt"
base=$(git rev-parse HEAD)
id=(-c user.name="Swarm Dispatch lab (promote)" -c user.email=swarm-dispatch-agents@users.noreply.github.com)
git "${id[@]}" merge -q --no-ff --no-edit "origin/$branch" || { say "refused: origin/$branch does not merge cleanly onto main"; exit 3; }
allow='^(src/spread_lab/(policy|notes)\.py|src/spread_lab/policies/|experiments/|night-queue/|README\.md$)'
[ "${REBASE:-0}" = 1 ] && allow='^(src/spread_lab/(policy|notes|runner)\.py|src/spread_lab/policies/|experiments/|night-queue/|README\.md$)'
bad=$(git diff --name-only "$base" HEAD | grep -vE "$allow" || true)
[ -z "$bad" ] || { say "refused: the merge touches files outside the policy:"; echo "$bad"; exit 4; }

uv sync -q
uv run python -c "import spread_lab.policy, spread_lab.notes" || { say "refused: the merged code does not import"; exit 5; }

say "dev (16 worlds) with ${flags[*]:-the champion params}"
uv run lab eval "${flags[@]}" --name dev
dev=$(ls -td runs/*-dev | head -1)
say "holdout (16 worlds)"
uv run lab eval --seeds-from holdout "${flags[@]}" --name holdout
hold=$(ls -td runs/*-holdout | head -1)
say "restart at minute 3600 (Wednesday 12:00) on dev-01"
uv run lab play --seed dev-01 "${flags[@]}" --restart-at 3600 2>&1 | tee runs/restart.txt || true
grep -q 'ranked True' runs/restart.txt || { say "refused: the restarted world did not finish ranked"; exit 6; }

gateopt=(); [ "${REBASE:-0}" = 1 ] && gateopt=(--rebase)
set +e; uv run python "$root/scripts/promote_gate.py" "${gateopt[@]}" "$dev" "$hold" runs/restart.txt | tee runs/gate.txt; rc=${PIPESTATUS[0]}; set -e
[ "$rc" = 0 ] || { say "refused: a gate failed (runs/gate.txt in $wt)"; exit 7; }
line=$(grep '^ALL GATES PASSED' runs/gate.txt | sed 's/^ALL GATES PASSED[^:]*: //')
note="$branch with ${flags[*]:-no overrides}: $line"
if [ "${DRY:-0}" = 1 ]; then say "DRY=1: every gate passed; not committing or pushing. $note"; exit 0; fi

uv run lab promote "$dev" --note "$note"
uv run lab promote "$hold" --note "$note"
[ -f experiments/PROMOTIONS.md ] || printf '# Promotions\n\nOne line per champion that scripts/promote.sh pushed to main.\n\n' > experiments/PROMOTIONS.md
echo "- $(date -u +%FT%H:%MZ) \`$branch\` (dev \`$(basename "$dev")\`, holdout \`$(basename "$hold")\`): $line. Flags: \`${flags[*]:-}\`" >> experiments/PROMOTIONS.md
git add champion experiments/PROMOTIONS.md
kind=Champion; [ "${REBASE:-0}" = 1 ] && kind="Re-baseline"
git "${id[@]}" commit -qm "$kind: $branch ($line)"
if git push -q origin HEAD:refs/heads/main; then
  say "PROMOTED: main is $(git rev-parse --short HEAD). The final runner picks it up within ~5 minutes (unless .freeze)."
else
  say "refused by the remote: main moved since the fetch (or the push failed). Run scripts/promote.sh again."; exit 8
fi
