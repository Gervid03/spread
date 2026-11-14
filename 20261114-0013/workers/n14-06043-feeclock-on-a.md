# n14-06043-feeclock-on-a
tool calls 86; result {"total_tokens": 8404995, "input_tokens": 8337874, "output_tokens": 34683, "cached": 7795817, "input": 542057, "duration_ms": 2777080, "tool_calls": 86, "models": {"gemini-4-argon": {"total_tokens": 8349014, "input_tokens": 8283516, "output_tokens": 34358, "cached": 7795817, "input": 487699}, "gemini-3-flash-preview": {"total_tokens": 55981, "input_tokens": 54358, "output_tokens": 325, "cached": 0, "input": 54358}}}

## Its last words

Best flags (on top of A): `-s ramp_hours=6 -s ramp_skip_closed=True -s fee_open_near=1.0` (highest margin, NOT SAFE) or `-s fee_open_near=1.0` (best SAFE).
Dev paired Δmargin: combo `€+119.37 ± 186.64` vs A (`€+167.87 ± 164.78` vs v3 champion), worst on-time `91.25%` (`deadline_close` 20.6, `gig_dropped` 28.9, NOT SAFE); `fee_open_near=1.0` `€-40.65 ± 36.38` vs A (`€+7.85 ± 156.95` vs v3 champion), worst on-time `95.67%` (`deadline_close` 13.8, `gig_dropped` 36.1, SAFE).
Run folders: `runs/20261114-064653-feeclock-dev-ramp6`, `runs/20261114-064816-feeclock-dev-skipclosed`, `runs/20261114-064946-feeclock-dev-near100`, `runs/20261114-065055-feeclock-dev-combo` (smoke: `runs/20261114-063621-feeclock-noop`, `runs/20261114-063723-feeclock-smoke-ramp4`, `runs/20261114-063820-feeclock-smoke-ramp6`, `runs/20261114-064100-feeclock-smoke-skipclosed`, `runs/20261114-064218-feeclock-smoke-near100`, `runs/20261114-064449-feeclock-smoke-ramp8`, `runs/20261114-064545-feeclock-smoke-combo`).
