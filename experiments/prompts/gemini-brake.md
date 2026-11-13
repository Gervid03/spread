Idea #10 of experiments/IDEAS.md in its cheap form, "The brake". One world of 32 ends at 91.8% on time, and under
90% the team is not ranked: this is insurance for the final, not a margin idea.
Implement in src/spread_lab/policy.py:
- `brake_at: float = 0.0` (0 = off) and `brake_discount: float = 0.08`. `braking()` is true when
  `brake_at` > 0 and the projected on-time share is under `brake_at`, and stays true until it is back above
  `brake_at` + 0.01. Use `projected_on_time()` with a weight of 0.7 for unstaffed orders past their warning
  (a new `brake_risk_weight`, so the champion's `guard_risk_weight` is untouched) and the `guard_min_orders`
  floor. Rebuild nothing special in `rejoin()`: the projection comes from the orders and `self.late`; make
  sure `self.late` is rebuilt from the ledger events of the history (today it is not).
- While braking, `price` quotes only ballast: the pickup has at least 200 drivers within 30 km or is a ring
  pickup; the option is next_day or within_3_days; the drive is under 120 minutes; the note has no clock time
  and no weekday; one leg; no premium car. Ballast is priced at the tracker's price x (1 - `brake_discount`)
  and does not move the tracker. Everything else is declined.
- Counters: `brake_minutes` (sum of the steps or event gaps spent braking), `brake_quotes`, `brake_won`,
  `brake_late`.
Measure in two steps. First that it works: `-s brake_at=0.96` on `--seeds dev-07,dev-10,dev-14,dev-01`; it
must wake there, and the on-time share of those worlds should rise. Then the cost: `-s brake_at=0.935` on
dev; it should almost never wake and the paired delta should be near zero. Report, for each run, the worst
on-time share, the minutes braked per world and the ballast orders won and late. Do not run holdout seeds.
