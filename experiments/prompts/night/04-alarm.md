Idea #8 of experiments/IDEAS.md, "An early staffing alarm instead of the deadline warning". Implement
`alarm_after_min` (default 0 = off) and `alarm_fee` (1.4): a gig with no driver that many daytime minutes after its post
(same_day: the given minutes; other options: 10:00 on the deadline day) jumps to alarm_fee x typical and then climbs on the
rising schedule. Try alarm_after_min 30, 45, 90 on smoke; best on dev. Stats: alarms, late among alarmed, fees paid on
alarmed gigs. Compare against the 71% late after `deadline_close`.
