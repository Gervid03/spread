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

Your idea: #16 in experiments/IDEAS.md, "The fee clock runs only when it can matter". Read points 4 and 10
there. `Desk.rising()` spreads the climb from the opening fee to `fee_warn` evenly over every daytime half-hour from
the post to the warning point. So a next_day gig is at about 1.2× the next morning, and a Friday gig due on Monday
is at 1.48× on Monday 07:00. A's opening-fee overrides (`hub_multiday_fee_open` 0.80, `thin_sameday_fee_open` 0.90)
pass through `rising(..., fee_open_override=...)`, so keep that argument working. Three flags, measured apart:
- `ramp_hours: float = 0.0` (0 = A's climb from the post): the climb takes only the last `ramp_hours` daytime hours
  before the warning point; until then the schedule holds one step at the opening fee. A gig with less time than
  that climbs from the post, as today.
- `ramp_skip_closed: bool = False`: Sunday never counts as daytime for a schedule. Saturday counts only when every
  site of the gig has Saturday hours (`leg["pickup"]["hours"]["saturday"]` and the delivery's are not null). A
  private address has no hours: treat it as open.
- `fee_open_near: float = 0.0` (0 = the opening fee) and `near_slack_min: int = 240`: a gig posted with less than
  `near_slack_min` minutes to `lastPickupAt` opens at `fee_open_near` instead.
`repost`, `raise_fees` and `rejoin` all go through `fees_for`: keep them working.
Counters: booked fee ÷ typical fee per booking (sum ×1000 and count) by option and by whether it was booked on the
day of the first post or later (`feex_<option>_<same|later>_sum`, `_n`); drops by near/far posting (`drops_near`,
`drops_far`).
Smoke: `ramp_hours` 4 and 6; `ramp_skip_closed`; `fee_open_near` 1.0. Dev: the best of each, then together.
Report `deadline_close` and `gig_dropped` next to the margin: a fee that holds must not cost on-time orders.
