The quote side of the Tier 0 sweeps of round 2 in experiments/IDEAS.md: S10 to S15. They need no code: run
commands and write up results. Skip protocol steps 1-2 (there is no code to check) and any tax-back run.
This brief allows more smoke runs than the usual 6, but run one sweep at a time, never two at once.
- Run S10 to S15 on smoke exactly as the table writes them, adding `--name s<N>`. In S14 the cell
  `price_target_win=0.35, min_supply=30` is the champion: it must show a paired delta of +0.00; if it does
  not, stop and say so in the first line of your note.
- For each sweep whose best combination is SAFE and beats the champion on smoke, run that one combination on
  dev: `uv run lab eval -s key=value ... --name s<N>-dev`. At most 4 dev runs: pick by promise. Then one dev
  run with every setting that helped on dev together; if it is not SAFE, drop the least useful setting.
- For S10 report the wins by option (`won_same_day`, `won_next_day`, `won_within_3_days`) next to the margin;
  for S11 `quote_floor` and driver fees over revenue; for S13 `won_ring` and `late_ring`; for S15 the three
  `dropped_*` counters. S15 is an ablation for the jury as much as a search: report every cell.
- Write one note, experiments/<YYYYMMDD-HHMM>-gemini-sweeps3.md: per sweep a table (setting, smoke mean
  margin, paired delta, worst on-time, SAFE), the dev confirmations, and a one-line verdict. Commit, push.
