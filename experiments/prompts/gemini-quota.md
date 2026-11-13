Idea #20 of experiments/IDEAS.md, "A same-day quota per pool instead of a threshold". Read points 7 and 14.
Implement in src/spread_lab/policy.py:
- `same_day_quota: float = 0.0` (0 = off: the champion's `same_day_min_supply` rule) and
  `same_day_quota_min_supply: int = 40`. With a quota above 0, the rule for the same_day option becomes: the
  pickup has at least `same_day_quota_min_supply` drivers within `supply_radius_km`, and the same_day orders
  won today with a pickup within `supply_radius_km` of this one, plus `price_target_win` x the same_day
  quotes in flight there, are fewer than max(1, `same_day_quota` x that supply). "Today" is the day of the
  option's deadline. `far_options` "slow" still keeps ring pickups to the slow options.
- Quotes in flight: every quote that offered same_day and whose outcome has not come; forget them on
  `order_won` and `order_lost`. Rebuild the day's count in `rejoin()` from the snapshot's orders.
- Counters: `dropped_same_day_quota`; same_day wins and late orders by pool size at the pickup (>= 200,
  100-199, 40-99: `sd_won_big`, `sd_late_big`, ...).
Smoke: quota 0.04 and 0.06. Dev: the better one; and once with `same_day_quota_min_supply` 100, which is the
champion plus a cap on the capital only (it tells the two effects apart). Report dev-02, dev-10 and dev-15
apart: in those worlds the champion drops same_day from over 200 requests.
