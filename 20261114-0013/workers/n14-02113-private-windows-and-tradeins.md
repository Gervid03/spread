# n14-02113-private-windows-and-tradeins
tool calls 26; result {}

## Its last words

Running `uv run lab eval --seeds-from smoke --name priv-win-noop` to verify that default parameter values reproduce the champion's results with Δ = 0.00 on all 4 smoke seeds.Running `uv run lab eval --seeds-from smoke -s respect_stop_windows=True -s min_pickup_window_slack_min=180 --name priv-win-all` to evaluate `respect_stop_windows=True` with `trade_in_mode="all"` on the smoke set.Running `uv run lab eval --seeds-from smoke -s respect_stop_windows=True -s min_pickup_window_slack_min=180 -s trade_in_mode=same_day_only --name priv-win-sameday` to evaluate `trade_in_mode="same_day_only"` on smoke.
