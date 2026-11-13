Idea #6 of experiments/IDEAS.md, "Find the fee floor: the same tracker on the drivers' side".
Start with the simple form: `fee_open_dense` (default = `fee_open`, i.e. off) for pickups with at least
`dense_supply` (200) drivers within `supply_radius_km`, ramping up to 1.0x the typical fee within
`open_ramp_min` (45 for same_day, 120 otherwise), then the champion's schedule; and `night_hold` (off): a gig
posted after 17:00 for a later day keeps its opening fee until 08:00. Then, if time allows, the learned form
the section describes (one opening multiple per town, down a step when a gig books within 5 minutes, up
when it waits 30 daytime minutes, within 0.7-1.1), behind its own flag.
Add `stats`: booked fee / typical fee (sum and count, so a mean can be computed), minutes to book, drops,
deadline warnings. Watch the on-time share closely: cheaper fees must not cost safety.
