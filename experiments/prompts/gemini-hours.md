Idea #17 of experiments/IDEAS.md, "Slack by opening hours: measure slack as the world does".
First a 10-minute check, before any code: reveal one finished champion world (`uv run lab reveal <world id>`
outside the repo; ids are in champion/results/dev-L8.jsonl) and tabulate, from legs.csv, the stated closing
minute of delivery sites and of pickup sites on weekdays and whether they have Saturday hours. If at least 9
in 10 dealer sites are open until 20:00, stop: write the note with that table and the verdict "reject: the
stated hours do not bind". Otherwise implement in src/spread_lab/policy.py:
- `slack_by_hours: bool = False`. A helper `open_at(place_stop, minute)` from the stop's `hours` (`opens`,
  `closes`, `weekdays`, `saturday`; minutes of the day; a private address has no hours: use its window).
  For each option: `earliest` = the first minute from max(now + 15, the note's ready time) at which the pickup
  site is open and inside its window; `last_pickup` = the last minute t such that the pickup site is open at
  t, the delivery site is open at t + drive, and t + drive <= the option's deadline. Search back from the
  deadline day by day (Saturday hours where given, Sunday closed). Slack = `last_pickup` - `earliest`, and the
  option is dropped when there is no such t. The slack rule (`min_slack_min` + `slack_per_drive` x drive) and
  the long-drive rule use this slack and this `earliest` when the flag is on.
- Prove the helper against the world: on `order_won`, for a one-leg order without a note and without a low
  battery, compare your `last_pickup` for the won option with `order["lastPickupAt"]`; count them and sum the
  absolute difference in minutes (`lastpickup_n`, `lastpickup_err`). It should be 0. Do this check with the
  flag off too (it changes no behaviour), and fix the helper until it is.
- Counters: `dropped_slack` as today, plus `dropped_hours` for options that pass the old rule and fail the new.
Smoke, then dev with the flag. If it is SAFE, the tax back of this idea is `-s min_slack_min=150` and then
`120` on top (instead of the win-target run of protocol step 4): the 180 minutes were paying for this.
