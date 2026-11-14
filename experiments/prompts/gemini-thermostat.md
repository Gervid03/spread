Idea #19 of experiments/IDEAS.md, "The thermostat: one load number per pool sets the price and the opening
fee". Read points 8 and 12 and the principles there. Implement in src/spread_lab/policy.py:
- State: the minute of each order's first post (`self.first_post`), and the quotes in flight: request id ->
  pickup place for every quote decided "quote" or "floor" whose outcome has not come (remove on `order_won`
  and `order_lost`). Rebuild both in `rejoin()` (gigs' `postedAt` in the snapshot; `openRequests`).
- `load(pickup)` in 0..1 = (won orders picked up within `supply_radius_km` of the pickup that are unstaffed
  and whose first post is more than `load_stale_min` (default 20) minutes old + `price_target_win` x quotes in
  flight within that radius) / max(`backlog_min`, `backlog_ratio` x gate supply), capped at 1. The backlog
  gate itself stays as it is.
- `load_tilt: float = 0.0` (0 = the champion) and `load_mid: float = 0.25`: every option's price is multiplied
  by exp(`load_tilt` x (load - `load_mid`)) before the floor.
- `load_fee_tilt: float = 0.0`: the opening fee of a new gig is multiplied by (1 + `load_fee_tilt` x load at
  the post); the rest of the schedule climbs from there to `fee_warn` as today.
- `load_learn: bool = True`: when False, a quote whose tilt differs from 1 by more than 2% is decided as
  "tilt" and does not move the tracker.
- Counters: `load_sum_x100` and `load_n` at each quote; wins and late orders by the load at the quote (0, up
  to 0.5, above: `w_l0`, `w_l1`, `w_l2`, `late_l0`, ...).
Smoke: `load_tilt` 0.2 and 0.4; `load_fee_tilt` 0.3; `load_learn` False with the better tilt. Dev: the best
price tilt, then with the fee tilt. This idea is about the weakest worlds as much as the mean: report the
worst on-time share and the three lowest worlds of the run next to the champion's.
