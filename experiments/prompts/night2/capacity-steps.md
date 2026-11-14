Capacity, not margin: you measure whether practice worlds can run 20–40% faster without changing what they tell us.
The server caps the team at 8 unfinished worlds, and a level-8 week takes ~16 s and ~630 requests on this machine,
so worlds per hour = 8 × 3600 / seconds per world. Fewer requests per world means more experiments per hour for
everyone. You may change `src/spread_lab/runner.py` and add two `Params` fields on your own branch only (the lead
decides whether it reaches main). Never run `lab board`, `lab final`, `lab promote` or `lab reap --force`.

Base: the current champion on `origin/main` (if `champion/champion.json` still says v2, merge
`origin/exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue` and use A's flags from the directive at the
top of experiments/IDEAS.md).

Today `runner.play_practice` advances a fixed `step_min` (10) minutes at a time on weekdays 07:00–22:00
(`busy()`), and outside those hours it uses `advance(until=URGENT, max=+1 h)`. Requests only arrive Mon 08:00–Fri
18:00, and a quote must land within 15 minutes of arrival, so a step of up to 14 minutes keeps every quote in time.
The handbook's own advice is "advance only to the events that you act on".
1. Add `busy_start_min: int = 420` and `busy_end_min: int = 1320` to `Params`, and have `busy()` read them from
   the desk's params (defaults = today's 07:00–22:00 exactly). The noop check must show +0.00 on every smoke seed.
2. Measure on dev against the base's dev results (paired), one at a time: (a) `-s step_min=14`; (b)
   `-s busy_start_min=480 -s busy_end_min=1080` (events drive the evenings and mornings); (c) both together.
   Also once on smoke: `-s step_min=3` (closer to the final, which answers every event).
3. For every run, report: Δmargin ± SE, Δon-time and the worst world, mean requests per world, mean seconds per
   world (`results.jsonl` has both), and the implied worlds per hour at 8 slots.

Verdict rule: a setting is a free capacity gain if its Δmargin is within ±€150 of the base, no world's on-time
share falls by more than 1 point, and it is SAFE. Then state the gain in worlds per hour. Write
`experiments/<YYYYMMDD-HHMM>-gemini-capacity-steps.md`, commit the runner change with it, and push your branch.
Your last three lines: the best free setting; its requests and seconds per world against the base's; worlds per
hour before and after.
