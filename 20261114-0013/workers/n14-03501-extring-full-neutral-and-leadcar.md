# n14-03501-extring-full-neutral-and-leadcar
tool calls 24; result {}

## Its last words

I will merge `origin/exp/gemini-n14-03113-stack-gtn-extring-dlr01`, `origin/exp/gemini-n14-03112-same-corridor-lead-car-v2`, and `origin/exp/gemini-n14-02462-deadline-aware-backlog` into the current branch.I will run `uv run lab eval --seeds-from smoke --name extring-neutral-noop` to verify that default parameter values reproduce the champion with `Δ = +0.00` on all four smoke seeds.I will run a smoke evaluation of `<BASE>` with `dealer_lr=0.01`, `ext_ring_min_supply=30`, `ext_ring_max_drive_min=220`, `return_hub_min_supply=200`, `return_hub_max_drive_min=180`, and `ext_ring_neutral_learn=True`.I will run a smoke evaluation of S1 combined with `lead_car=True`, `lead_car_max_gap_km=0.0`, `lead_car_max_deliv_gap_km=25.0`, and `lead_car_fee_mult=1.00`.I will run a smoke evaluation of `<BASE>` with `dealer_lr=0.01` and `lead_car=True` (`backlog-leadcar-only-s3`).
