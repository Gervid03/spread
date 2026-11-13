Research item R7 and idea #22 of experiments/IDEAS.md, "Snow: read the forecast". Research first, code only
if the research says so.
- R7. Reveal dev-07 and two ordinary dev worlds (say dev-05 and dev-06) from champion/results/dev-L8.jsonl
  (`uv run lab reveal <world id>`, outside the repo). From events.csv: every `forecast` event (from, to,
  placeIds, text); `gig_dropped` and `visit_failed` events by hour, and how many fall inside a forecast's
  hours at a forecast place (the gig's first pickup place, from gigs.csv and legs.csv); the late orders of the
  world and how many had a pickup or delivery in a forecast place during the snow. Is dev-07's spike of 58
  drops (the median world has 30) snow? If it is not, find what it is: drops by hour, by pickup town, by
  hours held, by booked fee over typical fee. Write that down: it decides the next idea.
- If snow explains at least a third of dev-07's drops or late orders, implement `snow_guard: bool = False` in
  src/spread_lab/policy.py: keep the forecasts from the `forecast` events (and from the history in
  `rejoin()`). In `price`: when the pickup or the delivery place is in a forecast and the time between the
  ready time and the option's deadline overlaps it, drop same_day and require `snow_slack_min` (default 120)
  more slack for the other options. In `post`: a car whose note has the summer-tyres flag gets a pickup
  window that starts when the snow at its pickup and delivery places has ended, if the order's deadline
  still allows the drive. Counters: `forecasts`, `dropped_snow`, `drops_in_snow`.
- Measure on smoke and dev, and report dev-07 apart. No tax-back run.
The note is useful either way: experiments/<YYYYMMDD-HHMM>-gemini-snow.md with the tables and the script
(experiments/scripts/scout_snow.py, standard library only).
