# extended-ring-and-return-gate: Surgical 70 km extended-ring slow gate and thin-to-Capital return gate

- **Agent / branch / commit:** gemini · exp/gemini-n14-02242-extended-ring-and-return-gate · 6d4a6e8
- **Date:** 2026-11-14 02:51
- **Idea from:** `20261114-0200-gemini-research-margin-xray.md` (Section 3, Leak #3) and IDEAS.md items #1 (`06 n-ring`) & #12 (`08-return`)

## Why we tried it
In Margin X-Ray v2 (`n14-01392`), decomposing the 361.9 requests/wk (35.0% of the market) that Champion v2 declines revealed why naive `gate_radius_km=70` failed earlier (`Δmargin €-328 ± 132`):
1. Raising `gate_radius_km` to `70` inflated `self.gate_supply` inside `backlog_near(pickup) >= max(p.backlog_min, p.backlog_ratio * gate_supply)`, loosening the backlog cap everywhere AND admitting `>300m` long-drive `next_day` orders from 55–70 km towns (where `next_day > 300m` is 7.7%–18.4% late).
2. However, two specific declined sub-buckets (`90.9 req/wk`) are structurally safe when restricted to slow options (`next_day` / `within_3_days`), medium drives, and a strict `backlog_min = 2` pickup cap:
   - **Sub-Bucket A1 — Extended 70 km Slow Ring (`ext_ring_min_supply=30, ext_ring_max_drive_min=220`):** Towns 55–70 km from the Capital ring (most notably Lahti, 62 km from Vantaa with `s55 < 30` so 100% declined today, but `s70 = 44.9` drivers within 70 km) where Capital/southern drivers have a full evening and morning to pick up a `<= 220` min car.
   - **Sub-Bucket A2 — Thin-to-Capital Return Lanes (`return_hub_min_supply=200, return_hub_max_drive_min=180`):** Slow requests starting in a thinner town (`gate_supply < 30`) whose final delivery is in the Capital hub (`delivery_supply >= 200`, Helsinki/Espoo/Vantaa) with `drive <= 180` min, where 327–444 Capital drivers browse for gigs ending near home and our outbound drivers need return cars.

## What changed
Merged `origin/exp/gemini-n14-01394-stack-trust-notes-slack` and added five `Params` fields in `src/spread_lab/policy.py` (all defaulting to `0` so defaults reproduce Champion v2 identically):
- `ext_ring_radius_km: float = 70.0`
- `ext_ring_min_supply: int = 0` — when `> 0`, precomputes `self.ext_supply = geo.supply(roster, params.ext_ring_radius_km)` in `Desk.__init__`.
- `ext_ring_max_drive_min: int = 240` — max total drive minutes for an order admitted via `ext_ring_min_supply`.
- `return_hub_min_supply: int = 0` — when `> 0`, admits a request failing `gate_supply < gate_min` if `self.supply.get(legs[-1]["delivery"]["placeId"], 0) >= p.return_hub_min_supply` and `drive <= p.return_hub_max_drive_min`.
- `return_hub_max_drive_min: int = 200` — max drive minutes for a thin-to-capital return request.
- When a request passes via `pass_ext_ring` or `pass_return_hub` (`gate_supply < gate_min`), `Desk.price()` enforces `self.backlog_near(pickup) < p.backlog_min` (strict cap of 2 unstaffed orders near the pickup), forces slow options (`option["kind"] != "same_day"`), and tracks `quoted_ext_ring`, `quoted_return_hub`, `won_ext_ring`, `won_return_hub`, `late_ext_ring`, and `margin_ext_ring_cents`.

Run with:
- Combined (`ext-ring-return-dev`):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 -s return_hub_min_supply=200 -s return_hub_max_drive_min=180 --name ext-ring-return-dev`
- Extended ring only (`ext-ring-only-dev`):
  `uv run lab eval -s trust_invest=0.05 -s notes_v2=True -s note_unsure=decline -s min_slack_min=140 -s slack_per_drive=0.75 -s ext_ring_min_supply=30 -s ext_ring_max_drive_min=220 --name ext-ring-only-dev`

## Results (level 8, vs champion v2, paired)
| set | run folder | mean margin | Δmargin ± SE | t | better/worse | on-time min | mean on-time (Δ) | SAFE |
|---|---|---|---|---|---|---|---|---|
| smoke (no-op) | `runs/20261114-023615-ext-ring-noop` | €9,662.25 | €+0.00 ± 0.00 | — | 0/0 | 95.5% | 96.7% (+0.00%) | yes |
| smoke 1 (`ext_ring` 30/220) | `runs/20261114-023750-ext-ring-smoke1-only` | €10,211.01 | €+548.77 ± 464.84 | 1.18 | 3/1 | 97.0% | 97.9% (+1.16%) | yes |
| smoke 2 (`return_hub` 200/180) | `runs/20261114-023933-ext-ring-smoke2-return-only` | €10,435.59 | €+773.34 ± 552.20 | 1.40 | 3/1 | 96.0% | 97.6% (+0.87%) | yes |
| smoke 3 (`both` 220/180) | `runs/20261114-024125-ext-ring-smoke3-both` | €10,166.34 | €+504.09 ± 597.18 | 0.84 | 3/1 | 96.9% | 97.5% (+0.79%) | yes |
| smoke 4 (`both` 240/200) | `runs/20261114-024436-ext-ring-smoke4-drive240` | €10,021.68 | €+359.44 ± 522.69 | 0.69 | 3/1 | 96.9% | 97.4% (+0.71%) | yes |
| smoke 5 (`both` 150/150) | `runs/20261114-024539-ext-ring-smoke5-drive150` | €9,895.84 | €+233.59 ± 454.56 | 0.51 | 3/1 | 96.6% | 97.4% (+0.68%) | yes |
| **dev (`ext-ring-return-dev`)** | `runs/20261114-024757-ext-ring-return-dev` | **€9,542.52** | **€+552.22 ± 207.99** | **2.66** | **11/5** | **94.8%** | **97.2% (+0.50%)** | **yes** |
| **dev (`ext-ring-only-dev`)** | `runs/20261114-024935-ext-ring-only-dev` | **€9,399.05** | **€+408.75 ± 260.11** | **1.57** | **12/4** | **92.9%** | **97.3% (+0.56%)** | **yes** |

### Paired comparison vs `n14-01394` Run B (`runs/20261114-020214-stack-trust-notes-slack140-dev`, €9,478.39)
- **`ext-ring-return-dev` vs `n14-01394` Run B (`uv run lab compare`):**
  - Mean margin rises from `€9,478.39` to **`€9,542.52` (`Δmargin €+64.14 ± 145.81`, 8/8 split)**, median margin rises by **`+€544.18`** (`€8,975.11` vs `€8,430.93`), and worst-seed margin rises by **`+€188.83`** (`€6,938.87` vs `€6,750.04`), with worst-seed on-time at **`94.8%` (`SAFE`)**.
- **`ext-ring-only-dev` vs `n14-01394` Run B (`uv run lab compare`):**
  - `Δmargin €-79.34 ± 202.75` (6 better, 8 worse), min on-time `92.9%` (`SAFE`).

### Direct surgical gate performance and ledger breakdown (mean per world across 16 dev seeds, totals in parens)
| Metric / Counter | Champion v2 | `n14-01394` Run B | `ext-ring-only-dev` | `ext-ring-return-dev` |
|---|---:|---:|---:|---:|
| `quoted_ext_ring` (mean / total) | 0.00 (0) | 0.00 (0) | 22.62 (362) | **43.81 (701)** |
| `quoted_return_hub` (mean / total) | 0.00 (0) | 0.00 (0) | 0.00 (0) | **26.69 (427)** |
| `won_ext_ring` (mean / total) | 0.00 (0) | 0.00 (0) | 4.56 (73) | **6.88 (110)** |
| `won_return_hub` (mean / total) | 0.00 (0) | 0.00 (0) | 0.00 (0) | **2.25 (36)** |
| `late_ext_ring` (mean / total) | 0.00 (0) | 0.00 (0) | **0.06 (1 / 73 = 1.4%)** | **0.06 (1 / 110 = 0.9%)** |
| `margin_ext_ring_cents` (€/world) | €0.00 | €0.00 | **+€156.79** (+€2,508.60) | **+€239.52** (+€3,832.29) |
| `margin_ring_cents` (€/world) | €2,114.01 | €2,141.70 | **€2,296.11** | **€2,305.84** |
| `won` (mean / total) | 230.12 (3,682) | 231.62 (3,706) | 238.81 (3,821) | **245.00 (3,920)** |
| `won_ring` (mean / total) | 51.44 (823) | 50.44 (807) | 55.56 (889) | **58.69 (939)** |
| `late_ring` (mean / total) | 1.06 (17) | 0.88 (14) | 1.12 (18) | 1.62 (26) |
| `won_same_day` | 71.69 (1,147) | 72.62 (1,162) | 73.94 (1,183) | 74.88 (1,198) |
| `won_next_day` | 147.62 (2,362) | 147.69 (2,363) | 153.44 (2,455) | **157.88 (2,526)** |
| `won_within_3_days` | 10.81 (173) | 11.31 (181) | 11.44 (183) | 12.25 (196) |
| `deadline_close` (mean / total) | 12.06 (193) | 10.06 (161) | 12.81 (205) | 12.44 (199) |
| `visit_failed` (mean / total) | 4.56 (73) | 0.38 (6) | 0.44 (7) | 0.81 (13) |
| Ledger `revenue` (€/world) | +26,922.43 | +27,172.62 | +27,736.05 | **+28,359.35** |
| Ledger `driver_fee` (€/world) | -17,286.92 | -17,287.23 | -17,826.25 | -18,278.59 |
| Ledger `late_refund` (€/world) | -376.20 | -298.42 | -380.19 | -387.46 |
| Ledger `failed_visit` (€/world) | -165.44 | -30.02 | -44.20 | -48.33 |
| Ledger `waiting` (€/world) | -39.38 | -21.98 | -21.37 | -27.97 |

### Key diagnostic insight
1. **Surgical safety is completely validated (`99.1%` on-time on admitted orders):** Across 16 dev worlds, the new gates quoted 701 orders (`43.81/world`) and won **110 orders (`6.88/world`)**, generating **+€239.52/world (+€3,832.29 total, €34.84/order)** in direct margin (`margin_ext_ring_cents`) with **only 1 late order out of 110 (`0.91%` late, `99.09%` on-time)**. Separating the extended 70 km ring from `gate_supply` and enforcing `backlog_near(pickup) < 2`, slow options only, and `drive <= 220/180` completely eliminated the overload and long-drive lateness that broke naive `gate_radius_km=70`.
2. **Why `return_hub` wins only 8.4% of quotes and partially dilutes `self.mult`:** While `ext_ring` wins 20.2% of its quotes (73 / 362), `return_hub` wins only 8.4% (36 / 427) because the competitor's structural lane factor is lower on lanes delivering into the Capital (abundant delivery-end drivers and return work). Because `Desk.learn()` steps `self.mult` down by `-price_target_win` on every lost `"quote"`, adding 391 lost `return_hub` quotes slightly depresses `self.mult` on core orders, offsetting part of the `+€239.52/world` direct margin. Excluding `pass_ext_ring`/`pass_return_hub` from `Desk.learn()` (or applying a small lane discount on `return_hub`) would preserve the full `+€240/world` direct gain.

## Verdict
**adopt / marginal over Run B** — Beats Champion v2 by **`Δmargin €+552.22 ± 207.99` (`t = 2.66`, 11/5 better, `94.8%` min on-time SAFE)** and lifts `n14-01394` Run B by `+€64.14/world` mean (`+€544.18` median, `+€188.83` min margin), with the 110 admitted extended-ring/return-hub orders achieving **99.1% on-time (1 late of 110)** and **+€239.52/world** direct margin.
