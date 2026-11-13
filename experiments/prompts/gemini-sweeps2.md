The fee side of the Tier 0 sweeps of round 2 in experiments/IDEAS.md: S7, S8, S9, and the two checks S16 and
S17. They need no code: run commands and write up results. Skip protocol steps 1-2 (there is no code to
check) and any tax-back run. This brief allows more smoke runs than the usual 6, but run one sweep at a
time, never two at once.
- Run S7, S8 (both commands) and S9 on smoke exactly as the table writes them, adding `--name s<N>`.
- S16 (`step_min=3`) and S17 (the low guard on dev's six weakest worlds) are checks, not candidates: run each
  once and report the paired delta and the worst on-time share. If S16 moves the mean on-time share by more
  than 1 point either way, say so in the first line of your note: the final has no steps.
- For each of S7-S9 whose best setting is SAFE and beats the champion on smoke, run that setting on dev:
  `uv run lab eval -s key=value --name s<N>-dev`. Then one dev run with every setting that helped on dev
  together. Settings that were unsafe alone may be safe together (that happened with S1-S6); if the
  combination is not SAFE, drop the least useful setting and say which. At most 4 dev runs in all.
- For every run also report, from its results.jsonl: driver fees per won order, `gig_dropped`,
  `deadline_close` and `gig_expired`, next to the margin. A lower fee that buys drops is not a saving.
- Write one note, experiments/<YYYYMMDD-HHMM>-gemini-sweeps2.md: per sweep a table (setting, smoke mean
  margin, paired delta, worst on-time, SAFE), the dev confirmations, and a one-line verdict. Commit, push.
