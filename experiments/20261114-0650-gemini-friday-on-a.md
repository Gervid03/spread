# friday-on-a: Friday 10-driver Monday-deadline gate, Friday slow discount, and Thursday+ surplus gate relaxation on Policy A

- **Agent / branch / commit:** gemini · `exp/gemini-n14-06044-friday-on-a` · `6440d18`
- **Date:** 2026-11-14 06:50 UTC
- **Idea from:** IDEAS.md #21 ("Friday has two days of drivers, and by Thursday we know what we can afford"), built on Policy A (`exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`)

## Why we tried it
1. **Friday has three days of weekend driver capacity (`(a)` + `(b)`):** In the rules and handbook, an option quoted on Friday (`day == 4`) whose deadline is on the last Monday (`deadline // DAY == 7`, i.e., `next_day` and `within_3_days` on Friday) has Friday afternoon, Saturday, Sunday, and Monday (~3,000+ minutes of clock time and three days of driver wakes) to be picked up and delivered. Under Policy A, the 55 km supply gate (`min_supply=22`) rejects Friday pickups with 10–21 drivers within 55 km even though those orders have the entire weekend to be staffed.
2. **Spending Thursday+ on-time surplus on intake gates rather than price (`(c)`):** Earlier experiments showed that spending safety headroom via `price_target_win=0.45` fails (unsafe 3/3 times) because lower prices attract a worse mix across the board. By Thursday 12:00 (`3 * DAY + 12 * HOUR`), we know our accumulated on-time cushion (`surplus = floor(0.06 * len(orders)) - late`, where `late` unions known late orders in `self.late`, undelivered orders past deadline, and unstaffed orders past `deadline_close`). While `surplus >= surplus_min` (closing with hysteresis when `surplus < surplus_min / 2`), we can selectively open specific borderline gate classes (`"slack"`, `"midtown"`, `"ring"`).

## What changed
Implemented in `src/spread_lab/policy.py` on top of Policy A:
- `fri_gate_min_supply: int = -1` (default `-1` = use `min_supply`, Policy A's behaviour): on Friday (`self.now // DAY == 4`), if a pickup fails `gate_supply >= gate_min` but has `gate_supply >= fri_gate_min_supply` (scaled by `tight`) and a `next_day` or `within_3_days` option with `deadline // DAY == 7`, it passes the supply gate (`pass_fri_gate`) and is quoted only for `next_day` and `within_3_days` options whose effective deadline is on the last Monday (`day == 7`).
- `fri_slow_discount: float = 0.0` (default `0.0`): on Friday, options with `deadline // DAY == 7` have their multiplier multiplied by `1 - fri_slow_discount`; such a quote is decided as `"tilt"` (counted in `backlog_near` in-flight quotes, and skipped by `learn()` so it does not move the price tracker).
- `surplus_min: int = 0` (default `0` = off) and `surplus_relax: str = ""` (comma-separated class list): from Thursday 12:00 (`self.now >= 3 * DAY + 12 * HOUR`), computes `surplus = floor(0.06 * len(self.orders)) - late`. Opens the named classes when `surplus >= surplus_min` and closes them when `surplus < surplus_min / 2`:
  - `"slack"`: `min_slack_min` relaxes to `120` (down from Policy A's `150`).
  - `"midtown"`: `same_day` is quoted from `30` drivers within 30 km (down from Policy A's `same_day_min_supply=50`).
  - `"ring"`: `same_day` is quoted for ring pickups (`is_ring`) when the request arrives before 11:00 (`request["arrivedAt"] % DAY < 11 * HOUR`), bypassing both `far_options == "slow"` and `same_day_min_supply`.
- Added desk counters: `won_fri`, `won_fri_{option}`, `quoted_fri_gate`, `won_fri_gate`, `late_fri_gate`, `margin_fri_gate_cents`, `quote_tilt`, `surplus_open_min`, `quoted_surplus`, `won_surplus`, `late_surplus`, `margin_surplus_cents` (and per-class breakdowns).

Base Policy A flags used on all runs (evaluated with v3-only champion params reset to defaults `dealer_lr=0.02`, `ext_ring_min_supply=0`, `return_hub_min_supply=0`, `ext_ring_neutral_learn=False`, `lead_car=False` so noop matches Policy A's reference runs exactly):
```
-s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s max_next_day_drive_min=480 -s fri_same_day_max_drive=100 -s thin_long_next_day_supply=50 -s ring_to_hub_same_day_min=60 -s same_day_min_supply=50 -s min_slack_min=150 -s slack_per_drive=0.75 -s backlog_multiday_weight=0.25 -s backlog_in_flight_weight=0.35 -s price_target_win=0.40 -s min_supply=22 -s drop_urgent_margin_min=180 -s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90
```

## Results (level 8)

### Worst on-time share first (all runs SAFE, ranked 100%)
- **noop (`20261114-063514-friday-on-a-noop`, smoke 4):** worst on-time **96.3%** (SAFE), Δmargin vs A **€+0.00 ± 0.00**
- **s1 (`fri_gate_min_supply=10, fri_slow_discount=0.0`, smoke 4):** worst on-time **96.3%** (SAFE), Δmargin vs A **€+87.84 ± 110.47** (t=0.80), vs champion (v3) **€+191.67 ± 235.01** (t=0.82)
- **s2 (`fri_gate_min_supply=10, fri_slow_discount=0.05`, smoke 4):** worst on-time **95.4%** (SAFE), Δmargin vs A **€+84.97 ± 189.14** (t=0.45), vs champion (v3) **€+188.80 ± 396.63** (t=0.48)
- **s3 (`surplus_min=6, surplus_relax=slack`, smoke 4):** worst on-time **96.3%** (SAFE), Δmargin vs A **€+18.22 ± 42.92** (t=0.42), vs champion (v3) **€+122.05 ± 260.72** (t=0.47)
- **s4 (`surplus_min=6, surplus_relax=midtown`, smoke 4):** worst on-time **96.2%** (SAFE), Δmargin vs A **€-100.42 ± 82.64** (t=-1.22), vs champion (v3) **€+3.41 ± 272.18** (t=0.01)
- **s5 (`surplus_min=6, surplus_relax=ring`, smoke 4):** worst on-time **96.3%** (SAFE), Δmargin vs A **€-3.31 ± 3.31** (t=-1.00), vs champion (v3) **€+100.52 ± 231.78** (t=0.43)
- **dev1 (`fri_gate_min_supply=10, fri_slow_discount=0.0`, dev 16):** worst on-time **94.1%** (SAFE), Δmargin vs A **€+22.26 ± 99.73** (t=0.22, **better on 10, worse on 4, tied on 2**), vs champion (v3) **€+70.76 ± 118.53** (t=0.60, better on 8, worse on 8)
- **dev2 (`surplus_min=6, surplus_relax=slack`, dev 16):** worst on-time **95.6%** (SAFE), Δmargin vs A **€-14.82 ± 34.14** (t=-0.43, better on 4, worse on 5, tied on 7), vs champion (v3) **€+33.68 ± 142.80** (t=0.24, better on 7, worse on 9)

### Summary table (vs Policy A, then vs Champion v3)

| Set | Run / Flags | Mean margin | Min margin | On-time min / mean | SAFE | Δmargin ± SE vs Policy A (t, W/L) | Δon-time vs A | Δmargin ± SE vs Champion v3 (t) | Run folder |
|---|---|---:|---:|---:|---|---:|---:|---:|---|
| smoke (4) | `noop` (Policy A) | €10,996.27 | €7,521.37 | 96.3% / 97.2% | yes | €+0.00 ± 0.00 (0/0) | +0.00% | €+103.83 ± 230.91 (t=0.45) | `runs/20261114-063514-friday-on-a-noop` |
| smoke (4) | `(a)+(b)` `fg=10, d=0.0` | €11,084.11 | €7,937.45 | 96.3% / 97.2% | yes | €+87.84 ± 110.47 (t=0.80, 1/1) | +0.03% | €+191.67 ± 235.01 (t=0.82) | `runs/20261114-063653-friday-on-a-s1-fg10-d0` |
| smoke (4) | `(a)+(b)` `fg=10, d=0.05` | €11,081.24 | €7,631.40 | 95.4% / 96.9% | yes | €+84.97 ± 189.14 (t=0.45, 3/1) | -0.30% | €+188.80 ± 396.63 (t=0.48) | `runs/20261114-063823-friday-on-a-s2-fg10-d05` |
| smoke (4) | `(c)` `sur=6, slack` | €11,014.49 | €7,508.13 | 96.3% / 96.8% | yes | €+18.22 ± 42.92 (t=0.42, 2/2) | -0.34% | €+122.05 ± 260.72 (t=0.47) | `runs/20261114-064111-friday-on-a-s3-sur6-slack` |
| smoke (4) | `(c)` `sur=6, midtown` | €10,895.85 | €7,506.92 | 96.2% / 97.0% | yes | €-100.42 ± 82.64 (t=-1.22, 0/3) | -0.16% | €+3.41 ± 272.18 (t=0.01) | `runs/20261114-064217-friday-on-a-s4-sur6-midtown` |
| smoke (4) | `(c)` `sur=6, ring` | €10,992.96 | €7,521.37 | 96.3% / 97.2% | yes | €-3.31 ± 3.31 (t=-1.00, 0/1) | -0.00% | €+100.52 ± 231.78 (t=0.43) | `runs/20261114-064328-friday-on-a-s5-sur6-ring` |
| **dev (16)** | **`(a)+(b)` `fg=10, d=0.0`** | **€10,600.18** | **€7,937.45** | **94.1% / 97.4%** | **yes** | **€+22.26 ± 99.73 (t=0.22, 10/4)** | **-0.25%** | **€+70.76 ± 118.53 (t=0.60)** | `runs/20261114-064554-friday-on-a-fg10-d0-dev` |
| **dev (16)** | **`(c)` `sur=6, slack`** | **€10,563.10** | **€7,508.13** | **95.6% / 97.6%** | **yes** | **€-14.82 ± 34.14 (t=-0.43, 4/5)** | **-0.13%** | **€+33.68 ± 142.80 (t=0.24)** | `runs/20261114-064735-friday-on-a-sur6-slack-dev` |

### Counter & diagnostic findings
1. **Why `(a)` `fri_gate_min_supply=10` won on 10 of 16 dev seeds (+€156/world direct margin) but had high variance (`± €99.73`):**
   - On the 16-seed dev set (`20261114-064554-friday-on-a-fg10-d0-dev`), `fri_gate_min_supply=10` quoted **15.38 requests/world**, won **4.13 orders/world** (lifting Friday `next_day` wins from 36.88 to **41.38/world**), had **0.31 late orders/world** (92.4% on-time on thin Friday pickups), and generated **+€156.00/world** in direct `margin_fri_gate_cents` (`+15,599.56` cents/world). It also lifted worst-seed margin from €7,521.37 to **€7,937.45** (+€416 on `dev-01`).
   - Why was the net paired delta only `+€22.26 ± 99.73` despite winning on 10 of 16 seeds? Two reasons: (i) unlike v3's `ext_ring` (`ext_ring_max_drive_min=220`, `ext_ring_neutral_learn=True`), `fri_gate_min_supply=10` admitted long-drive thin Friday pickups up to 480 min and allowed thin-pickup quotes to step `self.mult` down in `learn()` on losses; on `dev-07` alone, winning 324 orders caused an outlier `-€1,213.43` swing (excluding `dev-07`, the other 15 dev seeds averaged **+€104.64/seed**). Moreover, v3 (`champion`, promoted while this run was in flight) already captures the 70 km extended-ring slow orders all week with `ext_ring_max_drive_min=220` and `ext_ring_neutral_learn=True`.
2. **Why `(b)` `fri_slow_discount=0.05` (`quote_tilt`) hurt relative to `d=0.0`:**
   - Because almost all Friday requests include a Monday-deadline option, `fri_slow_discount=0.05` marked **130.75 quotes/world** on Friday as `"tilt"`, freezing `learn()` for the entire Friday business day and dropping Friday wins from 51.25 (`d=0.0`) to 48.25 (`d=0.05`).
3. **Why `(c)` surplus gate relaxation (`surplus_min=6`) had almost no signal:**
   - From Thursday 12:00 onward, Policy A almost always had `surplus >= 6` (`surplus_open_min = 9,140.9 min/world`), but the three candidate classes were either very thin or negative-EV:
     - `"slack"` (`min_slack_min` 150 → 120): quoted only **1.88 orders/world** and won **0.69 orders/world** on dev (+€20.20/world direct `margin_surplus_cents`, 0.125 late/world = 81.8% on-time), resulting in `-€14.82 ± 34.14` net after price-tracker perturbation.
     - `"midtown"` (`same_day_min_supply` 50 → 30): won 1.50 orders/world on smoke (`+€23.98` direct margin, 83.3% on-time), but crowded local driver supply and reduced overall margin by `-€100.42 ± 82.64`.
     - `"ring"` (ring `same_day` before 11:00): almost never triggered (`0.50 quoted/world`, `0.25 won/world` on smoke) because ring-to-hub short drives (`<= 60 min`) are already open all week under `ring_to_hub_same_day_min=60`, and longer ring `same_day` drives on Friday are blocked by `fri_same_day_max_drive=100`.

## Verdict
reject (do not promote over v3) — `fri_gate_min_supply=10, fri_slow_discount=0.0` is SAFE (94.1% min on-time) and improves 10/16 dev seeds (+€156/world direct margin on Friday thin-gate wins), but without drive-time caps and neutral learning its 16-seed net delta on Policy A is noisy (+€22.26 ± 99.73, t=0.22), and v3 (`ext_ring_min_supply=30, ext_ring_max_drive_min=220, ext_ring_neutral_learn=True`) already captures this mechanism cleanly across all five weekdays; `(c)` surplus relaxation (`surplus_min=6, surplus_relax=slack`) is noise (-€14.82 ± 34.14, t=-0.43).
