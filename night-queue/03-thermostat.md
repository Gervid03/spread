**Build on A, not on the champion** (the lead's directive at the top of experiments/IDEAS.md). First:
`git fetch -q origin && git merge --no-edit origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`, then `uv sync -q`.
A's flags, to pass on every eval of yours: `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90`.
Compare with A's runs instead of the champion. In protocol step 2, "noop" means A's flags with your new flags at
their defaults, and it must show +0.00 on every seed:
- smoke: `--vs /home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034543-fee-drop-smoke5-all180`
- dev: `--vs /home/lab/spread-wt/n14-03324-supply-adaptive-fee-open-and-drop-rescue/runs/20261114-034812-fee-drop-all180-dev`

Check the paths with `uv run lab runs | grep fee-drop`. If one is gone, run A once on that set (`--name a-smoke` /
`--name a-dev`) and compare with that. Skip protocol step 4's `price_target_win=0.45` run. Report every result
against A, then against the champion (the plain `uv run lab compare <run> champion`).

Your idea: #19 in experiments/IDEAS.md, "The thermostat: one load number per pool sets the price and the
opening fee". Read points 8 and 12 and the principles there. A already has a load-aware backlog gate
(`backlog_multiday_weight`, `backlog_in_flight_weight` from n14-02462); reuse its notion of load, and don't
build a second one. Implement in src/spread_lab/policy.py:
- `load(pickup)` in 0..1 = A's backlog quantity near the pickup ÷ the backlog gate's limit, capped at 1 (the gate
  itself stays as it is: at 1 it declines).
- `load_tilt: float = 0.0` (0 = A) and `load_mid: float = 0.25`: every option's price × exp(`load_tilt` × (load −
  `load_mid`)) before the floor: cheaper on a clear board, dearer just under the gate.
- `load_fee_tilt: float = 0.0`: the opening fee of a new gig × (1 + `load_fee_tilt` × load at the post). The rest of
  the schedule climbs from there as today, and A's `hub_multiday_fee_open` / `thin_sameday_fee_open` overrides are
  multiplied the same way.
- `load_learn: bool = True`: when False, a quote whose tilt differs from 1 by more than 2% doesn't move the tracker.
- Keep `rejoin()` right: the load comes from orders and quotes the desk rebuilds already. If it doesn't, rebuild it.
- Counters: `load_sum_x100`, `load_n` at each quote; wins and late orders by the load at the quote (0, up to 0.5,
  above: `w_l0`, `w_l1`, `w_l2`, `late_l0`, `late_l1`, `late_l2`).
Smoke: `load_tilt` 0.2 and 0.4; `load_fee_tilt` 0.3; `load_learn` False with the better tilt. Dev: the best price
tilt, then with the fee tilt. This idea is as much about the weakest worlds as the mean, so report the worst on-time
share and the three lowest worlds next to A's.
