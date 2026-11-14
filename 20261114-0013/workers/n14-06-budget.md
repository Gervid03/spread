# n14-06-budget
tool calls 56; result {}

## Its last words

I will create a temporary directory in `/home/lab/.gemini/tmp/n14-06-budget/reveals`, download the reveal CSVs for four of the champion's dev worlds (`dev-01`, `dev-07`, `dev-10`, `dev-14`), and run `experiments/scripts/scout_classes.py` on them to measure the exact class late rates under the v2 champion policy.I will now run the no-op smoke evaluation (`uv run lab eval --seeds-from smoke --name budget-noop`) to verify that with default parameters (`budget_target=0.0`), the desk reproduces the champion's results with a paired delta of +0.00 on every seed.I will now run a 3-point smoke sweep (`budget_target=0,0.95,0.96`) on top of the looser settings (`-s price_target_win=0.42 -s min_supply=20`) to compare the looser desk with and without the on-time budget and ballast discount.I will now run a smoke evaluation with `-s budget_target=0.95` on top of the champion's default parameters to measure the isolated effect of the updated `budget_target` mechanism.
