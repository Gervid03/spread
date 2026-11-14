# n14-02241-exact-trust-and-floor-v2
tool calls 25; result {}

## Its last words

ding noop, so we have 2 smoke runs left: Smoke 4 and Smoke 5).
Let's test:
- Smoke 4: `trust_gain=0.20 -s dealer_lr=0.01 -s floor_all_only=True -s expected_fee_mult=1.10` (gentle `trust_gain=0.20` + floor relief `1.10`)
- Smoke 5: `trust_gain=0.0 -s dealer_lr=0.01 -s floor_all_only=True -s expected_fee_mult=1.08` (or `expected_fee_mult=1.15` to bracket `1.10` with `trust_gain=0.0`).
Let's run Smoke 4 first!I will run Smoke 4 (`trust_gain=0.20 -s dealer_lr=0.01 -s floor_all_only=True -s expected_fee_mult=1.10` on top of Run B).Look at that monotone curve across `trust_gain` when combined with `dealer_lr=0.01 + floor_all_only=True + expected_fee_mult=1.10`:
- `trust_gain=0.40` (Smoke 3): `€9,714.94` (`Δmargin €+52.69 ± 312.23`, `t=0.17`, 2/2)
- `trust_gain=0.20` (Smoke 4): `€10,140.83` (`Δmargin €+478.58 ± 75.51`, `t=6.34`, 4/0, min on-time `97.8%`)
- `trust_gain=0.00` (Smoke 2): `€10,334.10` (`Δmargin €+671.86 ± 136.12`, `t=4.94`, 4/0, min on-time `97.3%`)

Why does `trust_gain=0.00` beat `trust_gain=0.20` and `trust_gain=0.40`?
Because `Desk.learn()` adjusts `self.mult` on every won/lost quote: when `trust_gain > 0` artificially raises D01's price by `+5%` to `+10%`, it causes extra losses at D01 (especially after the competitor cuts its morning price for D01 where we won most!), and each extra loss at D01 steps `self.mult` DOWN by `-0.35 * 0.05 = -1.75%` globally!
Whereas with `trust_gain=0.0, dealer_lr=0.01, floor_all_only=True, expected_fee_mult=1.10`, unblinding `Desk.learn()` on `3_Others` and relieving the inflated `1.359x` floor allows `3_Others` losses and wins to balance `self.mult` naturally!
Let's check Smoke 5: what if we test `expected_fee_mult=1.06` or `1.14` (with `trust_gain=0.0, dealer_lr=0.01, floor_all_only=True`)? Let's test `expected_fee_mult=1.06` in Smoke 5!I will run Smoke 5 (`dealer_lr=0.01 -s floor_all_only=True -s expected_fee_mult=1.06` on top of Run B) to see if lowering `expected_fee_mult` further improves over `1.10`.`expected_fee_mult=1.10` (`€10,334.10`, `Δmargin €+671.86 ± 136.12`, `t=4.94`, 4/0, min on-time `97.3%`) is a sharp sweet spot!
Let's check why:
- At `expected_fee_mult=1.25` (Run B), the floor is `1.359x` typical fee, which floors 30.2% of quotes and blinds `learn()`.
- At `expected_fee_mult=1.06` (Smoke 5), the floor is `1.152x` typical fee, which lets through low-margin quotes on high-fee-ratio requests (`referenceFeeCents / listPriceCents` up to 1.18).
- At `expected_fee_mult=1.10` with `floor_all_only=True` and `dealer_lr=0.01` (Smoke 2), the floor is `1.196x` typical fee (just above the 95th percentile `referenceFeeCents / listPriceCents = 1.18`), AND `floor_all_only=True` unblinds `Desk.learn()` whenever only `within_3_days` (or a slower option) hits the floor while `same_day`/`next_day` is unfloored!

Now let's transition to the `dev` runs!
Let's check the instructions for `dev` runs:
"2. On dev (2 to 3 runs):
   - Run the best 2 configurations on the 16-seed `dev` set (`--name exact-trust-floor-dev` and `--name exact-trust-floor-taxback-dev`).
   - Compare against both Champion v2 and `runs/20261114-020214-stack-trust-notes-slack140-dev` (`+€488.08`). Report `quote_quote`, `quote_floor`, `quote_unblinded`, `top_dealer_trust_d0..d4`, `price_ratio_d0_pct..d4_pct`, paired Δmargin ± SE, and worst on-time share."
And also from the protocol:
"4. Run the best setting on dev (`uv run lab eval -s field=value --name <slug>-dev`), at most 2 dev runs. If it is SAFE and better than the champion, also run it with `-s price_target_win=0.45` on dev: the safety tax given back, as Fable suggests."
Wait: let's check what taxback settings we should test!
First, let's run the primary dev run (`--name exact-trust-floor-dev`) with our best smoke configuration (Smoke 2: `-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s dealer_lr=0.01 -s floor_all_only=True -s expected_fee_mult=1.10`).
Let's update topic and run `exact-trust-floor-dev` now!
