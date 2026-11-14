The lead's tail study for the final, no new mechanism: protocol steps 1–4 don't apply. You may evaluate holdout
seeds. **Don't run `scripts/promote.sh`**: this result feeds a human decision. Never run `lab board`, `lab final`,
`lab promote` or `lab reap --force`.

Why: the final is ONE secret level-8 world, and a world under 90% on time means unranked, which means out. The
validation on 48 fresh worlds (`exp/gemini-n14-05161-validate-top`, `experiments/20261114-0612-gemini-validate-top.md`)
promoted v3 = D on the highest mean (€10,960). But D had 2 worlds under 92% (night-11 90.73%, night-15 91.12%), while
A had none (worst 92.00%) at €10,778. v7 was the best on dev and went unranked on night-15 (89.3%). So the tail is
the open question, and 48 worlds are too few to settle it.

Three arms, each on 32 NEW worlds, `night-33` … `night-64` (comma-separated in `--seeds`):
- **v3**: the champion on main, no flags (`uv run lab eval --seeds <night-33..64> --vs none --name tail-v3`).
- **A**: in a worktree of `origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, with A's full flags
  from the validation note (`--vs none --name tail-a`). Flags passed with `-s` sit on top of main's champion params
  when you run from that worktree's own champion/, so check `champion/champion.json` there: it is v2's. Pass A's
  full flag list exactly as the note gives it.
- **E = v3 + A's safety flags**: in a worktree of `origin/exp/gemini-n14-04394-stack-v8-feedrop-extring-leadcar-feewarn`
  (that branch already merges A's code with D's). First copy main's `champion/champion.json` and `champion/results/`
  into that worktree (so the champion is v3), then the noop check: `uv run lab eval --seeds-from smoke --name e-noop`
  must show +0.00 on every seed against v3. If it doesn't, stop and report the deltas. Then run
  `-s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180` (no `fee_warn`/`fee_step`
  changes) on holdout, on `night-01 … night-32`, and on `night-33 … night-64`.

Report one table over all 80 fresh worlds (holdout 16 + night 64; for v3 and A, take holdout and night-01..32 from
the validation note's run folders): mean margin, the paired Δ against v3 ± SE (`uv run lab compare <arm's run folder> <v3's run folder>` on each seed
set), worst on-time share, and the number of
worlds under 92%, under 91% and under 90%, plus the five lowest worlds of each arm with their on-time shares. Then one
paragraph: which arm you would play in the final, and why, in terms of expected margin and the chance of a world
under 90%. Write `experiments/<YYYYMMDD-HHMM>-gemini-tail-v3-vs-a.md`, commit, and push your branch. Your last
three lines: the arm you'd play; its 80-world mean and worst on-time; its worlds under 92% against the other arms'.
