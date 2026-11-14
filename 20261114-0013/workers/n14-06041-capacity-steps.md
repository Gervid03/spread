# n14-06041-capacity-steps
tool calls 71; result {"total_tokens": 2861836, "input_tokens": 2845393, "output_tokens": 15672, "cached": 2645057, "input": 200336, "duration_ms": 1262102, "tool_calls": 71, "models": {"gemini-4-argon": {"total_tokens": 2837108, "input_tokens": 2821675, "output_tokens": 15433, "cached": 2645057, "input": 176618}, "gemini-3-flash-preview": {"total_tokens": 24728, "input_tokens": 23718, "output_tokens": 239, "cached": 0, "input": 23718}}}

## Its last words

I will run the smoke evaluation with `step_min=3` against base A's smoke run using `uv run lab eval`. This creates temporary practice worlds via the lab harness and writes evaluation results to `runs/`. Please consider enabling sandboxing if running critical system-modifying commands outside a sandbox.-s step_min=14 -s busy_start_min=480 -s busy_end_min=1080
480.3 requests/world and 10.21 s/world vs base 645.1 requests/world and 16.49 s/world (dev Δmargin +€26.08 ± 148.85, t=0.18, Δon-time +0.09%, worst world on-time 95.31% vs base 94.38%, SAFE; max single-seed trajectory dip −1.45 pp on dev-11: 98.91% → 97.45%)
1,747 worlds/hour before → 2,820 worlds/hour after (+1,073 worlds/hour, +61.4% at 8 slots; runs: 20261114-061709-capacity-steps-noop, 20261114-061758-capacity-steps-smoke-step3, 20261114-061912-capacity-steps-dev-step14, 20261114-062042-capacity-steps-dev-busy480-1080, 20261114-062221-capacity-steps-dev-both)
