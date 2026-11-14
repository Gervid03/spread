# n14-02111-overnight-fee-hold
tool calls 16; result {}

## Its last words

I will run `uv run lab eval --seeds-from smoke --name fee-hold-noop` to verify that our default parameters reproduce the champion v2 baseline with zero delta across the smoke seeds (writes evaluation outputs to `runs/`).I will run `uv run lab eval --seeds-from smoke -s fee_ramp_power=2.0 -s fee_hold_multiday_only=True --name fee-hold-s1-pow2` to evaluate the multiday quadratic convex fee ramp on the 4 smoke seeds (writes results to `runs/`).I will run `uv run lab eval --seeds-from smoke -s fee_hold_frac=0.35 -s fee_ramp_power=1.5 -s fee_hold_multiday_only=True --name fee-hold-s2-hold35-pow15` to evaluate the multiday delayed-start hold + mild convex ramp on smoke seeds (writes results to `runs/`).
