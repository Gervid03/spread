Idea #21 of experiments/IDEAS.md, "Friday has two days of drivers, and by Thursday we know what we can
afford". Read the principles in IDEAS.md first: safety is to be spent on gates, not on the price.
Implement in src/spread_lab/policy.py; (a)+(b) and (c) are measured apart.
- (a) `fri_gate_min_supply: int = -1` (-1 = `min_supply`, the champion): on Friday (world day 4), for an option
  whose deadline is on the last Monday, the supply gate passes from this many drivers in the gate radius;
  a pickup that passes only because of it is quoted for next_day and within_3_days only.
- (b) `fri_slow_discount: float = 0.0`: those Monday-deadline options, quoted on Friday, are priced x (1 - d);
  such a quote is decided as "tilt" and does not move the tracker.
- (c) `surplus_min: int = 0` (0 = off) and `surplus_relax: str = ""`, a comma list of classes. From Thursday
  12:00: late = orders known late (as `self.late`) + undelivered orders past their deadline + unstaffed
  orders past their deadline warning; surplus = floor(0.06 x orders won) - late: the late orders we could
  still take and end at 94%. While surplus >= `surplus_min` the named classes are open, and they close when
  it falls under half of `surplus_min`: "slack" = `min_slack_min` counts as 120; "midtown" = same_day is
  quoted from 60 drivers within 30 km instead of `same_day_min_supply`; "ring" = same_day is quoted for ring
  pickups when the request arrives before 11:00.
- Counters: Friday wins by option; `won_surplus`, `late_surplus` and `margin_surplus_cents` for orders that
  were won through an opened class (remember the class at the quote); minutes with the surplus gates open.
Smoke: (a) 10 with (b) 0 and 0.05; (c) `surplus_min` 6 with each class alone. Dev: (a)+(b) best; (c) best.
Report the worst on-time share of each run first. Skip the win-target run of protocol step 4.
