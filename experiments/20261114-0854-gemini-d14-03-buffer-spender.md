# d14-03-buffer-spender: Spend unused on-time budget on `<2%` late easy classes (`c4`)

- **Agent / branch / commit:** gemini · `exp/gemini-d14-03-buffer-spender` · built on `1a2075b` (Champion v3T)
- **Date:** 2026-11-14 08:54
- **Idea from:** User brief `c4` / `experiments/prompts/day/03-buffer-spender.md` (with `<2%` late classes from `c3` / `exp/gemini-d14-02-acceptance-model`)

## Why we tried it
Champion v3T finishes level-8 weeks at **96.96% mean on-time** (worst dev world **94.33%**) against the 90% ranking cliff and our 92% safety rule — leaving ~10–14 late orders of on-time budget unspent in a typical week. Earlier attempts to "give safety back" globally via `price_target_win = 0.45` failed three times out of three (unsafe on tail worlds and worth only €100–160) because lowering prices everywhere admits risky afternoon/thin/long orders while cutting the price of cars we already win.

The user's narrower hypothesis (`c4`) is that **short/safe orders from deep driver pools are almost never late (`<2%`), so winning more of them while the week has budget to spare (`projected_on_time() >= buffer_hi`) both adds volume (margin, dealer trust, drivers positioned in hubs) and dilutes the late share when risky classes fail**. Because `c3` (`exp/gemini-d14-02-acceptance-model`, `experiments/20261114-0827-gemini-d14-02-acceptance-model.md`) had just completed its 96-world (`28,307` won orders) lateness model before we built `c4`, we followed the brief's rule and used **`c3`'s verified `<2%` late buffer union** (`1.36%` empirical late rate, `1.58%` 95% Wilson upper bound across 96 v3T worlds) as `"easy"`, and also ablated the prompt's fallback heuristic rule (`default`) and the inbound/slow under-won subset (`c3_inbound`).

## What changed
Added four neutral-default `Params` fields and telemetry counters in `src/spread_lab/policy.py` (all off at defaults `buffer_discount = 0.0`, reproducing Champion v3T to **`Δmargin = €+0.00 ± 0.00`** on smoke):
- `buffer_discount: float = 0.0` and `buffer_hi: float = 0.955`: while `projected_on_time()` (with `guard_min_orders = 30` floor and `guard_risk_weight = 0.5`) is `>= buffer_hi`, easy options are quoted at `tracker_price * (1 - buffer_discount)`, still bounded below by the expected-fee margin floor `fee / (1 - min_margin_frac)`. Below `buffer_hi`, quoting reverts immediately to normal. Quotes where at least one option is discounted (`self.buf_reqs`) do not move the tracker (`Desk.learn()`). `Desk.rejoin()` rebuilds `self.buf_won_orders` and normalizes buffer-discounted win ratios so mid-week restarts preserve `self.mult`.
- `buffer_rule: str = "c3"`:
  - **`"c3"` (primary, used per brief from `exp/gemini-d14-02-acceptance-model`):** `within_3_days` with `drive < 300m` and sure/no note (`0.54%` late on 96w); OR `next_day` with `drive < 300m`, no note, and `(pickup in Capital or delivery in Capital or 60 <= drive < 180)` (`1.20%–1.76%` late); OR `same_day` with `drive < 180m`, no note, Mon–Thu before `13:00`, and `(pickup in Capital or delivery in Capital)` (`1.58%` late). Combined 96-world late rate on v3T: **`1.36%`** (95% UB `1.58%`).
  - **`"default"` (ablation of prompt fallback rule):** `supply_30km >= 100`, `drive <= 120m`, not `same_day` at/after `13:00`, and no note (or v2 note with `not pn.unsure`).
  - **`"c3_inbound"` (ablation excluding Capital-outbound `60–299m` lanes we already win ~50% of the time):** `within_3_days` (`drive < 300m`, sure/no note) OR `delivery in Capital` (inbound & intra-Capital) with no note and (`next_day < 300m` or Mon–Thu `<13:00` `same_day < 180m`).
- `buffer_learn_b: float = 0.0`: `0.0` = strict skip-`learn()` ("These quotes don't move the tracker"); `> 0` = diagnostic ablation shifting `target_win` along `c3`'s logistic acceptance slope (`b = 11.92`) instead of skipping `learn()`.
- Telemetry counters in `desk.stats`: `buf_quoted`, `buf_easy_floored`, `buf_won`, `buf_late`, `buf_margin_cents`, `buf_open_min` (and weekday 08–18h `buf_open_busy_min`), `end_on_time`, `buf_skipped_learn`, plus complementary `nonbuf_won`, `nonbuf_late`, `nonbuf_margin_cents` (attributing multi-car `lead_car` gig fees by `referenceFeeCents` share so `buf_margin_cents + nonbuf_margin_cents` equals total world margin).

*(Instrument note: `baselines/fast14-dev` on `main` was recorded at `9c56669` with `busy_start_min`/`busy_end_min` from the refused `REBASE=1` branch and prior to `late_fee_open=1.0` in `51d1be6`; because normal 10-minute worlds take ~14s per 6-world wave on this host, all smoke, 8-world `dev-01..08`, and 16-world `dev` runs below use the exact normal instrument directly against Champion v3T.)*

Best command on `dev`:
```sh
uv run lab eval -s buffer_discount=0.05 -s buffer_hi=0.955 --name buffer-spender-d05-hi955-dev
```

## Results (normal instrument vs Champion v3T; worst world reported first)

Champion v3T baseline on `dev` (16 worlds): worst world on-time **`94.33%`** (`dev-13`, `0/16` under 92%), **`280.2`** won orders/wk, mean on-time **`96.96%`**, mean margin **`€10,884.88`** (worst margin **`€7,487.67`** on `dev-01`).

| Run | Set (n) | Flags (`rule`, `disc`, `hi`) | Worst world on-time (`<92%`) | Won / wk (vs ch) | Mean margin (min margin) | Paired Δmargin ± SE (t, W/L) | Mean OT (ΔOT) | SAFE? |
|---|---|---|---:|---:|---:|---:|---:|---|
| `20261114-083711-buffer-spender-noop` | smoke (4) | off (`0.0`) | **94.38%** `dev-01` (0/4) | 283.2 (283.2) | €10,816.98 (€7,487.67) | **€+0.00 ± 0.00** (0/0) | 95.98% (+0.00%) | SAFE |
| `20261114-083745-buffer-spender-hi955-buffer_discount0.05` | smoke (4) | `c3`, `0.05`, `0.955` | **94.83%** `dev-01` (0/4) | **319.5** (283.2) | €11,485.36 (€7,910.52) | **€+668.38 ± 265.35** (`t=2.52`, 4/0) | 96.69% (+0.71%) | SAFE |
| `20261114-083756-buffer-spender-hi955-buffer_discount0.10` | smoke (4) | `c3`, `0.10`, `0.955` | **94.01%** `dev-01` (0/4) | **331.2** (283.2) | €10,945.18 (€7,484.57) | **€+128.20 ± 136.29** (`t=0.94`, 2/2) | 96.00% (+0.03%) | SAFE |
| `20261114-083919-buffer-spender-d05-hi945` | smoke (4) | `c3`, `0.05`, `0.945` | **94.29%** `dev-01` (0/4) | **321.8** (283.2) | €11,481.50 (€7,895.08) | **€+664.52 ± 266.57** (`t=2.49`, 4/0) | 96.55% (+0.57%) | SAFE |
| `20261114-083930-buffer-spender-d05-hi955-defrule` | smoke (4) | `default`, `0.05`, `0.955` | **92.81%** `dev-01` (0/4) | 314.2 (283.2) | €11,067.44 (€8,153.06) | **€+250.46 ± 323.53** (`t=0.77`, 3/1) | 95.57% (-0.41%) | SAFE |
| `20261114-084042-buffer-spender-d05-hi955-dev8` | dev-01..08 (8) | `c3`, `0.05`, `0.955` | **94.60%** `dev-05` (0/8) | **314.6** (288.5) | €11,543.21 (€7,896.53) | **€+423.16 ± 180.10** (`t=2.35`, 6/2) | 96.78% (+0.13%) | SAFE |
| `20261114-084104-buffer-spender-d10-hi955-dev8` | dev-01..08 (8) | `c3`, `0.10`, `0.955` | **94.01%** `dev-01` (0/8) | **328.0** (288.5) | €11,292.73 (€7,484.57) | **€+172.68 ± 165.04** (`t=1.05`, 4/4) | 96.37% (-0.27%) | SAFE |
| `20261114-084140-buffer-spender-d05-hi945-dev8` | dev-01..08 (8) | `c3`, `0.05`, `0.945` | **94.29%** `dev-01` (0/8) | **315.8** (288.5) | €11,541.28 (€7,895.08) | **€+421.23 ± 180.12** (`t=2.34`, 6/2) | 96.71% (+0.06%) | SAFE |
| `20261114-084725-buffer-spender-d05-hi955-comp1192-smoke` | smoke (4) | `c3`, `0.05`, `0.955`, `b=11.92` | **94.72%** `dev-01` (0/4) | **338.5** (283.2) | €11,367.20 (€7,796.03) | **€+550.22 ± 212.48** (`t=2.59`, 4/0) | 96.07% (+0.09%) | SAFE |
| `20261114-084751-buffer-spender-d05-hi955-comp1192-dev8` | dev-01..08 (8) | `c3`, `0.05`, `0.955`, `b=11.92` | **91.60%** `dev-07` (**1/8**) | **338.0** (288.5) | €11,376.51 (€7,796.03) | **€+256.46 ± 203.97** (`t=1.26`, 7/1) | 96.20% (-0.45%) | **NOT SAFE** |
| `20261114-085012-buffer-spender-inbound06-hi955-dev8` | dev-01..08 (8) | `c3_inbound`, `0.06`, `0.955` | **95.22%** `dev-07` (0/8) | **299.6** (288.5) | €11,459.63 (€7,105.48) | **€+339.58 ± 216.28** (`t=1.57`, 7/1) | 96.96% (+0.31%) | SAFE |
| **`20261114-084317-buffer-spender-d05-hi955-dev`** | **dev (16)** | **`c3`, `0.05`, `0.955`** | **94.60%** `dev-05` (**0/16**) | **303.0** (280.2) | **€11,034.04** (**€7,896.53**) | **€+149.16 ± 128.49** (`t=1.16`, **9/7**) | **97.13% (+0.17%)** | **SAFE** |
| **`20261114-085050-buffer-spender-inbound06-hi955-dev`** | **dev (16)** | **`c3_inbound`, `0.06`, `0.955`** | **94.49%** `dev-14` (**0/16**) | **286.7** (280.2) | **€11,032.44** (€7,105.48) | **€+147.56 ± 133.34** (`t=1.11`, **10/6**) | **96.85% (-0.10%)** | **SAFE** |

### Mechanism counters across configurations (mean per world)
| Run (set) | `buf_quoted` | `buf_won` | `buf_late` (late %) | `buf_margin` (€/win) | `nonbuf_won` | `nonbuf_late` (late %) | `buf_open_min` (busy min) | `end_on_time` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `d05-hi955-defrule` (`smoke`, `default`) | 177.5 | 74.8 | 4.25 (**5.69%**) | €1,716.76 (€22.97) | 242.2 | 9.50 (3.92%) | 10,977 (2,708) | 0.9557 |
| `d05-hi955-dev8` (`dev-8`, `c3`) | 298.1 | 110.5 | 2.38 (**2.15%**) | €3,347.14 (€30.29) | 207.0 | 7.75 (3.74%) | 12,110 (2,879) | 0.9678 |
| `d10-hi955-dev8` (`dev-8`, `c3`) | 301.2 | 131.9 | 3.25 (**2.46%**) | €3,494.62 (€26.50) | 199.5 | 8.62 (4.32%) | 12,089 (2,865) | 0.9637 |
| `d05-hi945-dev8` (`dev-8`, `c3`) | 305.5 | 113.8 | 2.50 (**2.20%**) | €3,435.77 (€30.20) | 204.9 | 7.88 (3.84%) | 13,854 (3,018) | 0.9671 |
| **`d05-hi955-dev` (`dev-16`, `c3`)** | **266.3** | **103.0** | **1.75 (`1.70%`)** | **€3,090.70 (€30.01)** | **202.9** | **7.00 (`3.45%`)** | **13,007 (2,949)** | **0.9713** |
| **`inbound06-hi955-dev` (`dev-16`, `c3_inbound`)** | **148.6** | **42.7** | **1.12 (`2.64%`)** | **€1,147.11 (€26.87)** | **247.1** | **7.94 (`3.21%`)** | **13,229 (2,944)** | **0.9686** |

### Answering the two questions of `c4`

#### 1. Does extra easy volume let the champion's own risky classes fail more safely (the worst world)? **Yes — decisively.**
- **Verified `<2%` realized lateness on `dev`:** Across all 16 dev worlds in `buffer-spender-d05-hi955-dev`, the `c3` buffer classes won **`1,648` orders (`103.0/wk`) with only `28` late (`1.70%` late)** — half the late rate of non-buffer orders (`112 / 3,247 = 3.45%`). By contrast, the fallback `default` rule (`sup30 >= 100, drive <= 120m`) suffered **5.69% late** on smoke (`17/299`, dragging `dev-01` down to `92.81%`) because Friday `same_day` morning and tight-deadline notes inside `<120m` were still discounted, while starving `30–99`-driver regional yards (`dev-02` lost `−€678`). Using `c3`'s 96-world `<2%` union gained **`+€418/wk` and `+2.02 pp` worst-world on-time** over the heuristic rule on smoke.
- **Lifting the champion's tail worlds (`d05-hi955-dev` vs Champion v3T):**
  - **`dev-13` (Champion's worst on-time world: `94.33%`, `16/282` late):** Buffer spender won `122` buffer orders with **only `1` late (`0.82%`)**, while risky non-buffer classes still failed `15/199` times (`7.54%` late). The extra `+36` safe wins diluted total lateness to `16/318` = **`94.97%` on-time (`+0.64 pp`)**.
  - **`dev-01` (Champion's 2nd worst on-time & worst margin world: `94.38%`, `14/249` late, `€7,487.67`):** `projected_on_time()` dipped below `0.955` mid-week, **automatically closing the budget gate after `1,900` of `3,020` weekday request minutes (`4,242` world minutes)**. `dev-01` finished at **`94.83%` on-time (`+0.46 pp`)** and **`€7,910.52` margin (`+€422.85`)**. (`buffer_hi = 0.945` stayed open all week on `dev-01`, slipping to `94.29%` and `€7,895.08`, confirming `0.955` is the sharper cutoff.)
  - **`dev-02` (`94.98%` → `96.71%`, `+1.73 pp`, `+75` won orders, `+€408.84`)** and **`dev-07` (the 58-drop snow world: `95.27%` → `95.61%`, `2/133` late on buffer vs `13/215` non-buffer, `+€530.62`)** both gained volume, safety, and margin simultaneously.
  - Across all 16 dev seeds, **worst-world on-time rose from `94.33%` (`dev-13`) to `94.60%` (`dev-05`)**, **mean on-time rose `+0.17 pp` (`96.96% → 97.13%`)**, and **worst-world margin rose `+€408.86` (`€7,487.67 → €7,896.53`)**.

#### 2. Does extra easy volume add margin? **Modestly (`+€149 ± 128`, `t = 1.16`), capped by two structural tracker/inframmarginal effects.**
- **`buffer_discount = 0.05` beats `0.10` (`+€423 ± 180` vs `+€173 ± 165` on `dev-8`):** At `0.10`, buffer wins rose `110.5 → 131.9/wk`, but margin per buffer win fell `€30.29 → €26.50` (`€3,347 → €3,495/wk` gross on buffer while eating local driver capacity on `dev-03` and `dev-08`).
- **Why `+€423 ± 180` (`t = 2.35`) on `dev-01..08` settles at `+€149.16 ± 128.49` (`t = 1.16`, 9/7) on all 16 dev seeds:**
  1. **Inframarginal giveaway on already-won easy cars:** Discounting `103` easy wins/wk by `5%` (`~€5.50/car`) gives up `~€400/wk` on the `~80` easy cars/wk we would have won without a discount (`dev-05 -€282`, `dev-13 -€202`, `dev-14 -€388`), nearly offsetting the `~€600/wk` earned on the `+22.8` net new wins/wk.
  2. **Tracker sample starvation (`buf_skipped_learn = 266/wk`, ~50% of normal quotes):** Because half of normal quotes skip `Desk.learn()`, `self.mult` adapts at half speed during regional outages (`dev-16` Wednesday outage: `q/list` reached `1.719` vs `1.834` in champion, `−€551`) and only tracks the remaining non-easy half of quotes (`dev-09`: Monday `q/list` drifted `+4.7%` higher, losing 14 orders and `−€505`).
  3. **Why narrower `c3_inbound` (`+€147.56 ± 133.34`, `t = 1.11`, 10/6) and logit-compensated `learn()` (`b = 11.92`) confirm the ceiling:** Restricting to `c3_inbound` (`149` quotes/wk, keeping 70% of quotes in `Desk.learn()`) fixed both `dev-09` (`+€199`) and `dev-16` (`+€554`) and won on **10/16 seeds**, while landing at the identical mean (`+€147.56/wk`). Conversely, keeping `buf_reqs` inside `Desk.learn()` with `target_win` shifted by `c3`'s global slope `b = 11.92` (`55.1%`) won **7/8 seeds** on `dev-01..08`, but on `dev-07` — where inbound easy lanes have a `28.8%` baseline win rate rather than `40%` — chasing `55.1%` dragged `self.mult` down (`1.545 → 1.504`), flooding `nonbuf_won` to `314` (`393` total wins, `30` non-buffer late, **`91.60%` NOT SAFE**). Thus **"these quotes don't move the tracker" (`buffer_learn_b = 0.0`) is essential for tail safety**.

## Verdict
**reject for standalone promotion (keep flags in `policy.py`, defaults off)** — `buffer_discount=0.05, buffer_hi=0.955` (`buffer_rule=c3`, `runs/20261114-084317-buffer-spender-d05-hi955-dev`) is **SAFE** (`0/16` under `92%`, worst world **`94.60%`** vs `94.33%` champion, **`303.0`** vs `280.2` won orders/wk, worst-world margin **`€7,896.53`** vs `€7,487.67`) and positive (**`Δmargin €+149.16 ± 128.49`, `t = 1.16`, 9/7 seeds**; `c3_inbound` **`€+147.56 ± 133.34`, `t = 1.11`, 10/6**), proving that `<2%` easy buffer orders (`1.70%` realized late) genuinely cushion risky-class failures on the worst worlds, while confirming Principle 1 (`€150/wk` price-cut ceiling < `t = 2.0` bar).
