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

Your idea: the volume gap. **The leaders win 410–460 orders a week at 96–98% on time, at the same ~€40 margin an
order as ours; we win ~270.** (Public level-8 board, round "Saturday 00:00": we are 35th of 63 ranked teams with
€54.2k for 5 worlds; the top 10 need ~€75.5k.) So the gap is volume, not price. The margin x-ray
(`origin/exp/gemini-n14-01392-margin-xray-v2`, `experiments/20261114-0200-gemini-research-margin-xray.md`) shows
where it goes. The thin class (pickup with fewer than 30 drivers within 55 km) is 287 requests a week, about 500
options, and we decline 100% of it. same_day from mid towns (30–99 drivers) and from the ring is also 100% declined
(110 + 140 options a week). Read ideas 24 and 25 in experiments/IDEAS.md. Implement both in
src/spread_lab/policy.py, with flags that default to A's behaviour:
- **25, "Price what we decline":** `thin_fee_mult: float = 0.0` (0 = decline, as A does). A pickup that fails the
  supply gate is quoted for its slow options only (next_day, within_3_days), at max(the tracker's price ×
  `thin_markup` (1.25), `thin_fee_mult` × the typical fee ÷ (1 − `min_margin_frac`)): the price that pays a driver
  from far away. Try `thin_fee_mult` 1.8. Its gig opens at `thin_fee_open` (1.3) × the typical fee and climbs as
  usual. At most `thin_cap_day` such wins a day, counting today's thin wins + `price_target_win` × thin quotes in
  flight. These quotes don't move the tracker.
- **24, "Inbound":** `inbound_min_supply: int = 0` (0 = off). A pickup that fails the supply gate passes for slow
  options when at least this many drivers (try 200) live within 30 km of the DELIVERY and the drive is under
  `inbound_max_drive` (240 minutes). Price × (1 + `inbound_markup` (0.05)); the gig opens at `fee_open_inbound` (1.0).
  The driver goes out for the car and comes home with it. If a request qualifies for both, inbound comes first.
- Rebuild in `rejoin()` whatever the caps count (today's thin and inbound wins), from the snapshot's orders.
- Counters, so a failure teaches us too: per class (`thin`, `inbound`): quoted, won, late, margin (cents, from the
  ledger lines of their orders), booked fee ÷ typical fee (sum ×1000 and count), minutes from post to booking (sum
  and count), gigs that expired unbooked.

Smoke, in order: inbound alone (`inbound_min_supply` 200); thin alone with `thin_cap_day` 4; then thin with
`thin_cap_day` 12; then both. Dev: the best SAFE setting, then the next bigger cap. The hard rule is that
**every dev world stays ≥ 92% on time**. Report the worst world first, then the volume (won orders a week) and
the margin, against A. If the class makes money but costs on-time share, say at which cap it starts to hurt.
That number is what the lead needs.
