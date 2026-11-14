# n14-02114-stack-gates-trust-notes
tool calls 37; result {"total_tokens": 2055783, "input_tokens": 2037575, "output_tokens": 18208, "cached": 1899491, "input": 138084, "duration_ms": 1171882, "tool_calls": 37, "models": {"gemini-4-argon": {"total_tokens": 2055783, "input_tokens": 2037575, "output_tokens": 18208, "cached": 1899491, "input": 138084}}}

## Its last words

Best flags: `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.38 -s min_supply=25` (or without `-s price_target_win=0.38 -s min_supply=25` for maximum on-time safety)
Dev paired delta: `Δmargin €+1,039.28 ± 229.22 (SE) t=4.53` (14/16 better, worst on-time 94.3% SAFE, mean on-time 97.3%, mean margin €10,029.58); conservative slack/sdsup stack: `Δmargin €+823.72 ± 224.56 (SE) t=3.67` (13/16 better, worst on-time 94.6% SAFE, mean on-time 98.3%, mean margin €9,814.02); base stack: `Δmargin €+673.72 ± 181.49 (SE) t=3.71` (13/16 better, worst on-time 93.8% SAFE, mean on-time 98.2%, mean margin €9,664.03)
Run folders: `runs/20261114-022434-stack-gtn-ptw38-dev`, `runs/20261114-022233-stack-gtn-slack-sdsup-dev`, `runs/20261114-022057-stack-gtn-dev` (smoke: `runs/20261114-021628-stack-gtn-noop`, `runs/20261114-021708-stack-gtn-smoke1`, `runs/20261114-021821-stack-gtn-smoke2`, `runs/20261114-021947-stack-gtn-smoke3`)
