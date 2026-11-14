Combination test on champion v2 of two near-misses from wave 2: `origin/exp/gemini-clocks` (two price clocks: +46 ± 204 on
v1) and `origin/exp/gemini-feefloor` (fee floor: +104 ± 196 on v1). Merge both onto your branch (resolve conflicts keeping
v2's defaults), check the no-op on smoke (Δ = 0.00), then on dev: each branch's best flags alone, and both together.
You may use up to 4 dev evaluations. Report which, if any, adds to v2.
