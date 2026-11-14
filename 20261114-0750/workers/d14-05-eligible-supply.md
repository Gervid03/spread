# d14-05-eligible-supply
tool calls 72; result {"total_tokens": 6039230, "input_tokens": 5974060, "output_tokens": 26574, "cached": 5592720, "input": 381340, "duration_ms": 1595903, "tool_calls": 72, "models": {"gemini-4-carbon": {"total_tokens": 5993619, "input_tokens": 5929481, "output_tokens": 26364, "cached": 5592720, "input": 336761}, "gemini-3-flash-preview": {"total_tokens": 45611, "input_tokens": 44579, "output_tokens": 210, "cached": 0, "input": 44579}}}

## Its last words

Best flags: `-s eligible_supply=True -s eligible_min_supply_mult=0.75 -s eligible_backlog=True -s day_start=360 -s fee_warn=1.45 -s fee_step_min=25 -s steep_open=1.50 -s min_slack_min=135 -s price_lr=0.065 -s dealer_lr=0.009`
Dev paired delta: `Δmargin €+173.72 ± 149.32` (`t=1.16`, `10/16` better, mean `€11,058.61`, `136` total late, `prem_late=9/128`; `prem_late=1/75` without `eligible_backlog`), worst on-time share `93.57%` (`0/16` under `92%`, SAFE; keeping `fee_warn=1.60, steep_open=1.80` gives `Δmargin €+7.40 ± 158.57`, `121` total late, worst on-time `94.93%` SAFE)
Run folders: `20261114-090042-elig075-eb-ds360-s135-plr065-dev`, `20261114-085803-elig075-ds360-dev`, `20261114-085903-elig075-ds360-s135-plr065-dev`, `20261114-090321-elig075-eb-ds360-keeprescue-s135-plr065-dev`
