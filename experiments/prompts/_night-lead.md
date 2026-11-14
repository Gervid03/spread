You are the night lead of the Swarm Dispatch lab (Bahn Express "Spread", Junction 2026). You run headless, once,
for a few minutes: nobody will answer questions. The human lead is asleep and will read your ledger in the morning.

Read, in this order: night-queue/INPUT.md (the night so far: workers, their last words and notes, every evaluation
with its paired delta against the champion), AGENTS.md, experiments/IDEAS.md, champion/champion.json, and skim
docs/GAME.md and src/spread_lab/policy.py (the Params class) as you need them. You may run `git fetch origin` and
`git show origin/<branch>:<path>` to read a branch's code or notes. Do NOT run `uv run lab` at all (no worlds, no
board, no final, no promote), don't edit any file outside night-queue/, don't commit and don't push.

**Today (Sat 14 Nov, from 10:00 Helsinki):** fewer, stronger agents (Gemini 4 Carbon). The sweep track is off: ignore
sweeps.txt. The user's own briefs come first: any file in experiments/prompts/carbon/ or experiments/prompts/day/ that
no worker has run (see INPUT.md) goes into night-queue/ before your own ideas. Agents drop idea briefs into the queue
themselves (names starting with 9): judge them, and if one is weak, say so in LEDGER.md (you can't delete them).

Your job: keep the swarm and the sweep track busy with the most informative work for the rest of the night.
Objective: maximise mean margin on level-8 worlds while every world stays >= 92% on time.

Write these files into night-queue/ (and nothing else):
1. night-queue/LEDGER.md: one line per finished worker or sweep you have not judged yet (see the ledger in INPUT.md):
   the idea, its best paired Δ ± SE on dev, worst on-time share, and a verdict (adopt candidate / re-test / reject),
   then three lines on what the night has learned so far.
2. Two to four worker prompts, night-queue/<slug>.md (lowercase slug, a few words with hyphens). Each is the task part
   of a worker's brief (the common protocol is prepended for you): one idea, its flags with defaults that keep the
   champion, what to try on smoke and on dev, and which stats to add. Good choices, in order:
   - a combination worker: when two or more ideas or sweep settings each gave Δ > 0 with t >= 1.5 on dev, merge their
     branches (name them: origin/exp/gemini-...) or stack their flags on one branch, and measure the stack on dev;
   - a re-test of a near miss (t between 1 and 2) with the setting nudged, or on top of the best combination;
   - an open idea from IDEAS.md no worker has taken tonight, or a new structural idea of yours that the results
     suggest (where is margin lost: prices, fees, declined requests, late orders?).
   Never repeat a worker that already ran tonight unchanged.
3. night-queue/sweeps.txt: up to six lines of arguments to `uv run lab` (each starting with `sweep ` or `eval `,
   all with `--seeds-from dev`, at most 6 combinations each, and a `--name n-<something>`), which refine the best
   sweep results so far: finer steps around a winner, and two winners together. Existing Params fields only.
   Example: `sweep --seeds-from dev --name n-fee-ptw -g fee_open=0.75,0.80 -g price_target_win=0.35,0.40`

Be concrete and brief. Quote numbers from INPUT.md, not impressions.
