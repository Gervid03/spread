Idea #2 of experiments/IDEAS.md, "Option steering: quote the speed we can staff".
Implement in `Desk.price` (src/spread_lab/policy.py):
- `same_day_min_supply: int = 0`: quote `same_day` only where at least this many drivers live within
  `supply_radius_km` of the pickup (0 = off).
- `slack_per_drive: float = 0.0`: an option needs slack of at least `min_slack_min` + `slack_per_drive` x the
  drive minutes.
- `long_drive_min: int = 0` (0 = off): when the drive is longer than this, quote only options whose deadline
  falls on a later day than the car's ready day, so a driver can start in the morning.
- Counters in `self.stats`: wins by option (`won_same_day`, `won_next_day`, `won_within_3_days`) and options
  dropped by each rule.
Measure on smoke, then dev: for example `same_day_min_supply` 100 and 200, `slack_per_drive` 0.5 and 1.0,
`long_drive_min` 300. Then give the tax back on dev: the best setting with `-s min_supply=20`, and with
`-s price_target_win=0.45`.
