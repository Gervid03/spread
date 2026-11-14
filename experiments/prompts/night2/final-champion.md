The lead's study for the final. You build one branch that holds every candidate mechanism, measure four arms on
96 worlds each, and promote one arm only if it beats v3 without a worse tail. You may evaluate holdout seeds, and you
may run `scripts/promote.sh` once, as step 4 says. Never push main yourself, and never run `lab board`, `lab final`,
`lab promote` or `lab reap --force` by hand.

Why: the final is ONE secret level-8 world, and a world under 90% on time means unranked, which means out. The
validation on 48 fresh worlds (`exp/gemini-n14-05161-validate-top`, `experiments/20261114-0612-gemini-validate-top.md`)
promoted v3 = D on the highest mean (€10,960). But D had 2 worlds under 92% (night-11 90.73%, night-15 91.12%), and A
had none (worst 92.00%) at €10,778. v7 was the best on dev and went unranked on night-15 (89.3%). Since then, idea 15
(triage, `exp/gemini-n14-05163-triage`, on A) made +€264 ± 64 (t 4.1) on dev with slightly more late orders.

## 1. The branch
From your worktree (on main = v3): `git fetch -q origin`, then
`git merge --no-edit origin/exp/gemini-n14-04394-stack-v8-feedrop-extring-leadcar-feewarn` (A's code merged with D's),
then `git merge --no-edit origin/exp/gemini-n14-05163-triage` (triage on A). Resolve conflicts by keeping every
flag of both sides at its default. `uv sync -q`. **Noop check:** `uv run lab eval --seeds-from smoke --name fc-noop`,
with no flags, must show +0.00 on every seed against the champion (v3). If it doesn't, find the default that moved, fix
it, and check again. Commit and push the branch.

## 2. Four arms, flags on top of v3's champion params
- **v3**: no flags.
- **E** (A's safety): `-s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180`
- **T** (triage): `-s late_fee_open=1.0`
- **ET**: E's and T's flags together.

Seeds: `dev` (paired with the champion's stored results), `--seeds-from holdout` (the same), `night-01 … night-32`
(v3 already has them: `/home/lab/spread-wt/val-D/runs/20261114-060206-night32`; find it with
`uv run lab runs | grep night32`), and `night-33 … night-64` (new: run v3 there too, `--vs none --name n64-v3`). Paired
deltas between arms on the night seeds: `uv run lab compare <arm's run folder> <v3's run folder>`.

## 3. The table
One row per arm, over the 80 fresh worlds (holdout 16 + night 64), plus the dev columns: dev mean and Δ vs v3 ± SE (t),
80-world mean and Δ vs v3 ± SE (t), worst on-time share, and the worlds under 92%, under 91% and under 90%. Under the
table, list the five lowest worlds of each arm with their on-time shares.

## 4. The decision
Eligible arms: every one of the 96 worlds ranked, no more of the 80 fresh worlds under 92% than v3 has, and a worst
on-time share no more than 0.5 points below v3's. Among the eligible arms other than v3, take the one with the
highest 80-world mean, provided it beats v3's 80-world mean and its dev Δ vs v3 has t ≥ 2. If one qualifies, run
`bash scripts/promote.sh <your branch> <that arm's flags>`, and copy its last ten lines into your note. **After
PROMOTED, and only then,** reset the root checkout as before:
`git -C $HOME/spread fetch -q origin && git -C $HOME/spread reset -q --hard origin/main && git -C $HOME/spread log --oneline -1`.
If no arm qualifies, don't promote. Say which arm you would play in the final and why, in terms of expected margin
and the chance of a world under 90%.

Write `experiments/<YYYYMMDD-HHMM>-gemini-final-champion.md`, commit, and push your branch. Your last three lines:
the arm you chose (or none) and why; its 80-world mean and worst on-time; promote.sh's verdict.
