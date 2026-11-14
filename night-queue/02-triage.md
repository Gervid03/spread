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

Your idea: #15 in experiments/IDEAS.md, "Late-order triage: a car that cannot be on time is a cost to cut,
not a rescue to pay for". Read point 9 in IDEAS.md and experiments/20261114-0130-fable-research-v2-results.md
first. A already reprices a gig dropped within 180 minutes of `lastPickupAt` (`drop_urgent_margin_min`), and it
does so before `lastPickupAt`. Triage is the other side: after `lastPickupAt` the car is late whatever we pay.
Implement in src/spread_lab/policy.py:
- `late_fee_open: float = 0.0` (0 = off: A's behaviour) and `late_fee_max: float = 1.3`. Keep `self.lost`, the
  orders that can no longer be on time: an order whose gig expired, or an unstaffed order with
  `self.now > order["lastPickupAt"]`. While `late_fee_open > 0`, `fees_for` gives a lost order a schedule that opens
  at `late_fee_open` × the typical fee and climbs in daytime half-hour steps to `late_fee_max`, reached at the next
  refund-tier boundary minus the drive (deadline + 24 h, then deadline + 2 business days). The refund tiers are
  10% up to 2 h late, 25% up to 24 h, 50% up to two business days. In the world's last 36 hours the schedule goes to
  `steep_max`, because an undelivered car costs twice its price. The world ends at minute 14,280 (the second
  Wednesday, 22:00); `rejoin` gets `endsAt` in the snapshot.
- `late_repost: bool = False`: in `tick()`, an order that has just become lost and still has an open, unbooked gig
  is withdrawn and posted again at once without stop windows, as `repost` does, instead of standing unbookable
  until `gig_expired`. Do it once per order. Don't assume a step size: `tick()` runs after every event in the final.
- `rejoin()` rebuilds `self.lost` from the snapshot and the history's `gig_expired` events.
- Counters: `late_reposts`; the fees paid on lost orders and on warned orders that were saved (`fee_lost_cents`,
  `fee_lost_n`, `fee_warned_cents`, `fee_warned_n`, from `gig_booked.feeCents`); late orders by tier
  (`late_le_2h`, `late_le_24h`, `late_more`).
Add the counters first (they change no behaviour) and read on A's smoke worlds how much A pays on lost orders.
Smoke: `late_fee_open` 1.0 alone, then with `late_repost`, then `late_fee_max` 1.1. Dev: the best two settings.
The on-time share should hardly move; report driver fees, late refunds and the tiers next to the margin.
