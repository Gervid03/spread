# n14-06264-triage-and-feedrop-on-v3
tool calls 50; result {"total_tokens": 3501028, "input_tokens": 3467990, "output_tokens": 18123, "cached": 3184475, "input": 283515, "duration_ms": 1452296, "tool_calls": 50, "models": {"gemini-4-argon": {"total_tokens": 3480521, "input_tokens": 3448073, "output_tokens": 18008, "cached": 3184475, "input": 263598}, "gemini-3-flash-preview": {"total_tokens": 20507, "input_tokens": 19917, "output_tokens": 115, "cached": 0, "input": 19917}}}

## Its last words

Best flags (on Champion v3): `-s late_fee_open=1.0 -s late_fee_max=1.3 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90` (Triage + A fee/drop) and `-s late_fee_open=1.0 -s late_fee_max=1.3` (Triage alone)
Dev paired delta ± SE and worst on-time share: `Δmargin €+407.79 ± 204.23 (t = 2.00, 11/5, mean €10,937.21, min €7,821.09, driver_fee -€331.69/w, revenue +€101.91/w, fee_lost €1,032.52/w [8.31/w], fee_warned €553.99/w [6.31/w], late tiers 2.25/2.81/1.62)` with worst on-time `94.66%` (`mean 97.25%, Δon-time +0.09%, SAFE`); Triage alone: `Δmargin €+355.47 ± 168.66 (t = 2.11, 11/4, mean €10,884.88, driver_fee -€409.18/w, fee_lost €1,096.22/w [8.56/w], fee_warned €434.10/w [5.44/w], late tiers 2.50/2.88/2.00)` with worst on-time `94.33%` (`mean 96.96%, Δon-time -0.20%, SAFE`)
Run folders: `runs/20261114-070357-v3-triage-feedrop-dev1`, `runs/20261114-070533-v3-triage-only-dev2`, `runs/20261114-070716-v3-triage-drop-dev3`, `runs/20261114-070038-v3-triage-feedrop-s3`, `runs/20261114-065829-v3-triage-s1`, `runs/20261114-065732-v3-triage-noop`
