Re-test on champion v2: idea #4 (trust) was built on v1 in branch `origin/exp/gemini-trust`; there `trust_invest=0.1` gave
+215 ± 157 (t 1.4) on dev vs v1, and `trust_gain` lost. Merge that branch onto your branch (`git fetch origin
exp/gemini-trust && git merge --no-edit FETCH_HEAD`; resolve conflicts keeping v2's defaults in Params), check the no-op
(Δ = 0.00 on smoke), then on dev: `trust_invest` = 0.05, 0.10, 0.15 (one sweep: `uv run lab sweep --seeds-from dev -g trust_invest=0.05,0.1,0.15 --name trustv2`).
If the best is SAFE with t >= 1.5, also run it with `-s price_target_win=0.40` on dev. You may use up to 5 dev evaluations.
