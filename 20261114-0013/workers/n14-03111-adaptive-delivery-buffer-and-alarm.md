# n14-03111-adaptive-delivery-buffer-and-alarm
tool calls 37; result {"total_tokens": 1319074, "input_tokens": 1299721, "output_tokens": 19353, "cached": 1116035, "input": 183686, "duration_ms": 923122, "tool_calls": 37, "models": {"gemini-4-argon": {"total_tokens": 1319074, "input_tokens": 1299721, "output_tokens": 19353, "cached": 1116035, "input": 183686}}}

## Its last words

Best flags: `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s price_target_win=0.40 -s min_supply=22 -s delivery_buffer_min=30 -s buffer_min_slack_min=210 -s pre_warn_lead_min=60 -s pre_warn_fee=1.35` (and on `price_target_win=0.38 -s min_supply=25` for Dev 1)
Dev paired delta ± SE: Dev 2 (`ptw=0.40, min_supply=22`) `Δmargin €+1,517.77 ± 201.53` (t=7.53, 16/16 better vs champion v2; `Δmargin €+478.49 ± 134.12`, t=3.57, 13/16 better vs `stack-gtn-ptw38-dev`), mean margin `€10,508.07`, worst on-time share `95.8%` (mean `97.7%`, SAFE); Dev 1 (`ptw=0.38, min_supply=25`) `Δmargin €+1,097.73 ± 199.48` (t=5.50, 15/16 better vs champion v2), mean margin `€10,088.03`, worst on-time share `94.3%` (mean `97.9%`, SAFE)
Run folders: `runs/20261114-032059-gtn-ptw40-buf-alarm-dev`, `runs/20261114-031907-gtn-ptw38-buf-alarm-dev`
