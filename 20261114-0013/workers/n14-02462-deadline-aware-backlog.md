# n14-02462-deadline-aware-backlog
tool calls 38; result {"total_tokens": 1467002, "input_tokens": 1450997, "output_tokens": 16005, "cached": 1333021, "input": 117976, "duration_ms": 955956, "tool_calls": 38, "models": {"gemini-4-argon": {"total_tokens": 1467002, "input_tokens": 1450997, "output_tokens": 16005, "cached": 1333021, "input": 117976}}}

## Its last words

`-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35` (and at `price_target_win=0.38 -s min_supply=25`: `-s backlog_multiday_weight=0.25`)
dev paired Δmargin €+1,491.27 ± 252.93 (t=5.90, 15/16 better vs champion v2; €+452.00 ± 124.81, t=3.62, 13/16 better vs `stack-gtn-ptw38-dev`), mean margin €10,481.58, worst on-time 95.35% (SAFE, 113 late of 4,370 won, `declined_backlog=62`, `in_flight_blocked=49`); at `ptw=0.38, ms=25, mw=0.25`: Δmargin €+1,135.57 ± 203.93 (t=5.57, 15/16 better vs champion v2; €+96.29 ± 73.47 vs `stack-gtn-ptw38-dev`), mean margin €10,125.87, worst on-time 94.03% (SAFE)
`runs/20261114-030237-backlog-aware-gtn-ptw40-dev`, `runs/20261114-025739-backlog-aware-gtn-dev`, `runs/20261114-030038-backlog-aware-gtn-v2-dev`
