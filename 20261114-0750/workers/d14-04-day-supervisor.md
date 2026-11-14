# d14-04-day-supervisor
tool calls 107; result {"total_tokens": 530982, "input_tokens": 526129, "output_tokens": 2172, "cached": 452034, "input": 74095, "duration_ms": 120319, "tool_calls": 17, "models": {"gemini-4-carbon": {"total_tokens": 530982, "input_tokens": 526129, "output_tokens": 2172, "cached": 452034, "input": 74095}}}

## Its last words

Staging and committing the experiment note and analysis script on `exp/gemini-d14-04-day-supervisor`, then pushing the branch to `origin`.Pushing `exp/gemini-d14-04-day-supervisor` (including the experiment note and analysis script) to `origin` over SSH and verifying the remote branch state.Best flags: `-s supervisor=llm` (neutral default `supervisor=""`; formula arm `-s supervisor=rule -s sup_low_backlog=8 -s sup_high_backlog=18`)
Dev paired delta: 16-dev `llm` €-93.05 ± 116.71 (t = -0.80), worst on-time 94.24% (0/16 < 92%, SAFE; worst margin €7,862.58 vs €7,487.67); 8-dev `llm` €+34.85 ± 100.42 (worst on-time 95.09%, SAFE) vs 8-dev `rule` €-35.51 ± 67.96 (worst on-time 94.03%, SAFE)
Run folders: `runs/20261114-084634-day-supervisor-noop`, `runs/20261114-084806-day-supervisor-rule-8dev`, `runs/20261114-085119-day-supervisor-rule-v2-8dev`, `runs/20261114-085341-day-supervisor-llm-8dev`, `runs/20261114-085603-day-supervisor-llm-dev`
