Idea #1 of experiments/IDEAS.md, "The ring: gate on who can reach the car, not on who is notified".
Implement in src/spread_lab/policy.py:
- `gate_radius_km: float = 0.0`: the straight-line radius of the supply count that the decline gate in
  `Desk.price` uses; 0 means use `supply_radius_km` (the champion's behaviour). Build a second supply table
  from the roster with this radius at start (and in `rejoin`, which runs after `__init__`, so `__init__` is
  enough). The backlog gate should use the same supply number as the decline gate.
- `far_options: str = "all"`: with "slow", a pickup that passes the gate only thanks to the wider radius
  (its supply within `supply_radius_km` is under `min_supply`) is quoted for `next_day` and `within_3_days`
  only, never `same_day`.
- Counters in `self.stats`: `won_ring` (won orders that passed only on the wider radius) and `late_ring`
  (those that turned late: a `late_refund` or `undelivered_penalty` ledger line for their order id).
Measure on smoke, then dev: `gate_radius_km` 45 and 55, `far_options` slow and all. Report the ring orders
separately (won, late, margin share) from the counters.
