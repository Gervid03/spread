# d14-08431-combo-lane-inbound-hours
tool calls 76; result {"total_tokens": 6987951, "input_tokens": 6913252, "output_tokens": 40236, "cached": 6019762, "input": 893490, "duration_ms": 1928418, "tool_calls": 76, "models": {"gemini-4-carbon": {"total_tokens": 6934153, "input_tokens": 6860522, "output_tokens": 40007, "cached": 6019762, "input": 840760}, "gemini-3-flash-preview": {"total_tokens": 53798, "input_tokens": 52730, "output_tokens": 229, "cached": 0, "input": 52730}}}

## Its last words

`-s slack_by_hours=True -s min_slack_min=120 -s lane_prior_weight=0.70 -s lane_prior_only_neg=True -s lane_prior_comp_slope=1.6 -s lane_inbound_fee_mult=1.05 -s lane_min_proj=0.945`
dev (16): Δmargin €+319.02 ± 126.40 (t=2.52, 11W/5L, Δon-time +0.24%), worst on-time 95.31% (`dev-02`, 0/16 <92%, SAFE); night (32): Δmargin €+258.42 ± 100.53 (t=2.57, 19W/13L), worst on-time 91.27% (`night-15`, 1/32 <92%, 0/32 <91%, vs v3T 90.57%)
`runs/20261114-090524-combo-stack-dev`, `runs/20261114-090708-combo-lane-only-dev`, `runs/20261114-090837-combo-stack-night32`
