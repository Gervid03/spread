Idea #16 of experiments/IDEAS.md, "The fee clock runs only when it can matter". Read points 4 and 10 there.
Today `Desk.rising()` spreads the climb from `fee_open` to `fee_warn` evenly over every daytime half-hour from
the post to the warning point, so a next_day gig is at about 1.2x the next morning and a Friday gig due on
Monday at 1.48x on Monday 07:00. Implement in src/spread_lab/policy.py, three flags to measure apart:
- `ramp_hours: float = 0.0` (0 = the champion's climb from the post): the climb takes only the last
  `ramp_hours` daytime hours before the warning point; until it starts, the schedule has one step at the
  opening fee. A gig with less time than that climbs from the post, as today.
- `ramp_skip_closed: bool = False`: Sunday never counts as daytime for a schedule; Saturday counts only when
  every site of the gig has Saturday hours (`leg["pickup"]["hours"]["saturday"]` and the delivery's are not
  null; a private address has no hours: treat it as open).
- `fee_open_near: float = 0.0` (0 = `fee_open`) and `near_slack_min: int = 240`: a gig posted with less than
  `near_slack_min` minutes to the order's `lastPickupAt` opens at `fee_open_near` instead of `fee_open`.
Keep `repost`, `raise_fees` and `rejoin` working: they all go through `fees_for`.
- Counters: for each booking the booked fee over the typical fee of its cars, as sum (x1000, integer) and
  count, split by the order's option and by "booked on the day of the first post" or later
  (`feex_<option>_<same|later>_sum`, `_n`); drops split by whether the gig was posted with less than
  `near_slack_min` (`drops_near`, `drops_far`).
Smoke: `ramp_hours` 4 and 6; `ramp_skip_closed`; `fee_open_near` 1.0. Dev: the best of each, then together.
Report `deadline_close` and `gig_dropped` next to the margin: a fee that holds must not cost on-time orders.
