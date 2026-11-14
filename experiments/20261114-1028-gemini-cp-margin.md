# cp-margin: Inbound-to-hub competitor price matching (`inbound_hub_disc=0.07`) and rescheduled-slot state hygiene (`fix_slot_state=True`)

- **Agent / branch / commit:** gemini · `exp/gemini-cp-margin` · `147c0f9`
- **Date:** 2026-11-14 10:28 UTC (12:28 Helsinki)
- **Idea from:** Co-play on `dev-13` (`cp-margin-1`..`cp-margin-7`) + slot-free 16-world reveal X-ray (own focus: margin per order — price, dealer limits/trust, fees, and declining)

## Why we tried it

Playing `dev-13` (the current champion's worst on-time world in `dev`, `94.33%` on-time, `€11,211.71` margin) turn by turn with `scripts/coplay.py` (`probe` and `whatif`) alongside slot-free CSV reveals of all 16 finished champion `dev` worlds exposed two independent, high-leverage leaks in **margin per order** (`€38.84/order` on `dev`, `€38.07/order` on `night32`):

1. **Competitor inbound-hub cost discount & global multiplier whipsaw (`inbound_hub_disc`):**
   - Using `probe` on `dev-13` (`cp-margin-1`, Turns 7–9) to measure dealers' exact acceptance limits on matched dealers and minutes revealed that the competitor prices **~10–15% lower** on non-hub → capital-hub (`supply < 200 → deliv_supply >= 200`) return legs than on outbound legs:
     - `R00320` (`D01(7)`, `Hyvinkää[2]→Vantaa[339]`, inbound to hub): limit `1.288×` list (`1.204×` base before +7% trust), while our desk quoted `1.72×` and lost 8 of 9 `Hyvinkää→Capital` requests in `D01`'s Tuesday noon batch (`R00304..R00318`), whipsawing `self.mult` down from `1.520` to `1.362` in a single hour.
     - `R00290` (`D01(5)`, `Oulu[97]→Espoo[339]`, inbound to hub): limit `1.428×` (`1.360×` base).
     - Meanwhile at the same time on zero-trust outbound routes, `R00292` (`D11(0)`, `Espoo→Lempäälä`) had limit `1.542×` and `R00289` (`D11(0)`, `Espoo→Turku`) had limit `1.788×` (where our whipsawed tracker quoted `1.39×`, leaving €25/car on the table).
   - Checking all 8,100 unfloored normal quotes across the 16 champion `dev` reveals confirmed this is universal: `nonhub→hub` won only **25.8%** (`379/1,471`, and `8.6%` on `ring→hub mid`), vs **48.8%–49.3%** on `hub→mid/thin`. Yet `nonhub→hub` has the **lowest actual driver fee** (`0.936×` ref, `63.4%` booking immediately at `0.85×`), **1.9% late rate**, and physically delivers drivers into the capital hubs (`supply >= 200`) to staff subsequent outbound orders.
   - Crucial subtlety discovered in `cp-margin-4` vs `cp-margin-5`: discounting `nonhub→hub` by `6–8%` **while keeping the `1.25×` margin floor intact and without an explicit outbound markup** (`inbound_hub_disc=0.07`) lets the margin floor block high-fee inbound cars, wins profitable capital-bound return cars, stops `nonhub→hub` batch losses from dragging `self.mult` down (naturally lifting `self.mult` on outbound cars), and replenishes hub driver supply.

2. **Two state-machine bugs when pickup slots/windows reschedule or expire (`fix_slot_state`):**
   - Tracing the 10 worst negative-margin orders across the 16 champion `dev` reveals (`-€247` to `-€407` on `next_day` / `within_3_days` orders that were not even late!) uncovered two interacting bugs in `Desk`:
     - **Bug 1A (`order_changed` keeps stale `self.urgent`):** On a multi-day private-pickup order (e.g. `dev-07 R00193`, `within_3_days` due Thursday 20:00), the seller's Day-1 slot (`Mon 19:00–22:00`) triggers `deadline_close` at `Mon 19:00`, adding the order to `self.urgent`. At `Mon 22:01`, the uncollected slot expires and the dealer rebooks Day 2 via `order_changed` (`new lastPickupAt = Tue 22:00`, 24h away). `Desk.change()` reposted the gig **without clearing `self.urgent`**, putting the Tuesday gig onto `steep()` (`1.80× → 3.00×`) all Monday night so a driver booked at `01:58 AM` for **`€561.51` (`2.80×` ref fee, `-€265` net loss)** on a car due Thursday! Fired **37 times** across the 16 `dev` worlds (`-€2,970` total margin).
     - **Bug 1B (`gig_expired` marks still-on-time orders as `self.lost`):** Whenever a narrowed Day-1 pickup window (either a rebooked Day-1 private slot like `dev-13 R00976` or a dealer note window `"Nouto arkisin klo 9-15"` like `dev-13 R00699`) expired at Day-1 close while `now <= order["lastPickupAt"]` (still 100% deliverable on time on Day 2!), `handle("gig_expired")` unconditionally added `orderId` to `self.lost`. Under `late_fee_open=1.0`, `self.lost` capped Day-2 fees at `late_fee_max = 1.30` and blocked `deadline_close` from switching to `steep()`, starving on-time Day-2 orders of drivers and causing avoidable late deliveries (`66` occurrences across 16 `dev` worlds, `32` ending late).

## Co-play journal on `dev-13` (champion: `€11,211.71`, `282` won, `94.3%` on time)

| Game / Turn | What we tested (`probe` / `whatif`) | Result on `dev-13` (Δmargin, won, on-time) | What we concluded |
|---|---|---|---|
| `cp-margin-1` T1–T3 | Watched Mon 08:00–Tue 08:31; probed `R00009` (`0.978×`) & `R00021` (`1.028×`) | Mon is `dev-13`'s `-20%` price war; `mult` crashed `1.35 → 1.115` by Tue 08:00, then Tue 08:00–09:30 won 10/10 at `0.97–1.24×` | Floor quotes won on Tue AM didn't step `mult` up because `learn()` ignores `"floor"`. |
| `cp-margin-1` T6 (`Tue 09:31`) | `whatif` post-war `price_mult_min=1.30` / `1.35`, `dealer_lr=0.025`, `same_day_markup=0.10` | `mult_min_130`: **`+€549`** (`96.0%`); `mult_min_135`: **`+€340`** (`96.0%`); `dealer_lr_025`: `-€120`; `sd_markup_10`: `-€222` | Recovering after Monday's war helps on `dev-13`, whereas faster `dealer_lr` and global `same_day_markup` lose volume/margin. |
| `cp-margin-2` T1–T3 (`Mon 08:00` vs `Tue 08:01`) | `whatif` `mult_min=1.26/1.30`, `loss_streak_freeze=6`, `A` fee/drop flags from Mon 08:00 vs Tue 08:01 | From Mon 08:00: `mult_min_130` **`-€721`**, `freeze_6` **`-€627`**, `fee_drop_A` **`-€684`**. From Tue 08:01: `recover_135` **`+€340`**, `recover_132` `-€395` | Refusing war-day wins on Monday idles Monday drivers and starves dealer trust; pure `war_morning_reset=1.0` later tested `-€107` from Mon 07:00 due to trajectory noise, so dropped. |
| `cp-margin-1` T7–T9 | Probed matched dealers/routes: `R00254` (`1.674`), `R00261` (`1.557`), `R00289` (`1.788`), `R00292` (`1.542`) vs inbound `R00290` (`1.428`), `R00320` (`1.288`) | Observed `D01` `Hyvinkää→Capital` batch lose 8/9 at `1.53–1.72×` and whipsaw `mult` `1.520 → 1.362` | Competitor discounts `nonhub→hub` by ~10–15% matching cheap return-driver economics. |
| `cp-margin-3` T1–T2 (`Mon 07:00`) | Individual new rules: `fix_slot_state`, `+priv_pickup_min_slot_min=360`, `war_morning_reset=1.0`, `return_hub_fee_open=0.75` | `fix_slot`: **`+€220`** (`94.6%`); `ret_hub_75`: **`+€296`** (`95.0%`); `stack_fix_ret75`: `+€101` (**`96.4%`**); `fix+priv360`: `-€526`; `war_reset`: `-€107` | Once `fix_slot_state` cures overnight `steep()` on rescheduled private pickups, multi-day `tts<360` private pickups are profitable — declining them (`priv360`) throws away good margin. |
| `cp-margin-4` T1–T2 (`Mon 07:00`) | `lane_08_04` (`inbound_hub_disc=0.08 + inbound_hub_fee_mult=1.05 + outbound_markup=0.04`), `min_margin_cents=1800/2400`, `fee_warn=1.45` | `lane_08_04`: `-€799`; `min_marg_18`: `-€916` (`won 242`); `min_marg_24`: `-€2,302`; `ret_hub_78`: `-€294`; `fee_warn_145`: `-€262` | Lowering the `nonhub→hub` quote floor (`inbound_hub_fee_mult=1.05`) and adding `outbound_markup` traded €70-margin long outbound cars for low-list short cars; `min_margin_cents` starved early trust. |
| `cp-margin-5` & `cp-margin-6` (`Mon 07:00`) | Isolated `outbound_markup=0.04`, `inbound_hub_disc` (`0.06, 0.08, 0.10, 0.12`) with `1.25×` floor intact, `fee_open=0.82`, `steep_max=2.30`, and combos | `in_disc_06`: **`+€882`** (`95.5%`); `in_disc_08`: **`+€1,035`** (`96.3%`); `in06_fix`: **`+€577`** (`95.5%`); `out_mk_04`: `-€920`; `in06_ret75`: `-€232`; `in_disc_10`: `-€755` | **Breakthrough:** `inbound_hub_disc` in `[0.06, 0.08]` with `1.25×` floor intact + normal `0.85×` opening fee (so return drivers book immediately and reach hubs early!) + `fix_slot_state=True` is the sweet spot. |
| `cp-margin-7` (`Mon 07:00 → end`) | Played full week on main line with confirmed `-s inbound_hub_disc=0.07 -s fix_slot_state=True` | **`€11,520.96` (`+€309.25`)**, `291` won, **`96.6%` on time** (`+2.27%`, late orders cut `16 → 10`) | Main line recorded on `coplay.py board`. |

## What changed

Added neutral-default `Params` fields in `src/spread_lab/policy.py` (all defaults preserve the champion to `€0.00` on every seed, with full `rejoin()` support and `desk.stats` counters):
- `inbound_hub_disc: float = 0.0` (recommended **`0.07`**): multiplies `mult` by `(1 - inbound_hub_disc)` when `supply < 200` and `deliv_supply >= 200`, keeping the `1.25×` expected-fee margin floor intact (`stats["priced_inbound_hub"]`).
- `fix_slot_state: bool = False` (recommended **`True`**):
  1. In `Desk.change()` (and `rejoin()`), when `order_changed` moves `lastPickupAt` more than `3h` into the future (`lastPickupAt - now > 180`), clears stale `order["id"]` from `self.urgent` (`stats["slot_urgent_cleared"]`), and if `now <= lastPickupAt`, clears `self.lost`.
  2. In `Desk.handle("gig_expired")` (and `rejoin()`), only marks `orderId` as `self.lost` when `now > order["lastPickupAt"]`, keeping still-on-time orders on normal escalation (`stats["slot_kept_ontime"]`).
- Additional tested flags kept at neutral `0` / `False` defaults for ablation reproducibility: `war_morning_reset`, `floored_sd_prem`, `inbound_hub_fee_mult`, `outbound_markup`, `min_margin_cents`, `priv_pickup_min_slot_min`, `priv_pickup_sameday_only`, `return_hub_fee_open`.

Command:
```sh
uv run lab eval -s inbound_hub_disc=0.07 -s fix_slot_state=True --name cp-margin-indisc07-fixslot-dev
```

## Results (level 8, vs champion `1196b7a84b`, paired)

| Set & Variant | Run folder | Mean margin | Δmargin ± SE | t | Better / worse | Worst on-time (u92) | Mean on-time (Δ) | SAFE? |
|---|---|---|---|---|---|---|---|---|
| smoke noop (`defaults`) | `20261114-092323-cp-margin-noop` | €10,816.98 | €+0.00 ± 0.00 | 0.00 | 0 / 0 | 94.4% (0) | 96.0% (+0.00%) | yes |
| smoke `-s inbound_hub_disc=0.07` | `20261114-094521-cp-margin-smoke-indisc07` | €11,284.62 | €+467.64 ± 91.99 | 5.08 | 4 / 0 | 96.2% (0) | 97.0% (+1.06%) | yes |
| smoke `-s fix_slot_state=True` | `20261114-094911-cp-margin-smoke-fixslot` | €11,174.36 | €+357.38 ± 183.04 | 1.95 | 4 / 0 | 94.4% (0) | 96.1% (+0.09%) | yes |
| smoke `-s inbound_hub_disc=0.06 -s fix_slot_state=True` | `20261114-095518-cp-margin-smoke-indisc06-fixslot` | €11,266.91 | €+449.93 ± 212.81 | 2.11 | 4 / 0 | 94.0% (0) | 96.6% (+0.62%) | yes |
| smoke `-s inbound_hub_disc=0.07 -s fix_slot_state=True` | `20261114-095134-cp-margin-smoke-indisc07-fixslot` | **€11,472.88** | **€+655.90 ± 114.57** | **5.72** | **4 / 0** | **95.4% (0)** | **96.9% (+0.89%)** | **yes** |
| dev ablation (`-s inbound_hub_disc=0.07` only, 16 seeds) | `20261114-100847-cp-margin-indisc07-dev` | €10,986.83 | €+101.94 ± 102.08 | 1.00 | 10 / 6 | 94.8% (0) | 97.3% (+0.35%) | yes |
| **dev confirmed (`-s inbound_hub_disc=0.07 -s fix_slot_state=True`, 16 seeds)** | `20261114-100231-cp-margin-indisc07-fixslot-dev` | **€11,192.25** | **€+307.36 ± 105.38** | **2.92** | **11 / 5** | **95.1% (0)** | **97.5% (+0.53%)** | **yes** |
| **night32 fresh (`-s inbound_hub_disc=0.07 -s fix_slot_state=True`, 32 seeds vs `fc-v3T-night32`)** | `20261114-102117-cp-margin-indisc07-fixslot-night32` | **€11,762.63** | **€+420.96 ± 118.77** | **3.54** | **24 / 8** | **90.6% (1 vs 2)** | **97.4% (+0.14%)** | 32/32 ranked (champ u92=2 → cand u92=1) |

### Mechanism counters & ledger breakdown (mean per world)

- **16 `dev` worlds (`champion` → `inbound_hub_disc=0.07 + fix_slot_state=True`):**
  - **Margin per won order:** `€38.84` → **`€39.54` (`+€0.70/order`)**, while winning **`+2.9` more orders/wk** (`280.2 → 283.1`).
  - **Ledger:** Revenue `€30,474.48 → €30,711.83` (`+€237.35`), **driver fees `-€19,073.53 → -€19,017.57` (`+€55.96` cheaper total driver spend despite +2.9 more orders!)**, **late refunds `-€366.72 → -€332.24` (`+€34.48` saved)**.
  - **Tail safety & floor:** Worst-world margin rose **`+€582.04`** (`€7,487.67 → €8,069.71`, zero worlds under €8k); worst-world on-time rose **`+0.80%`** (`94.33% → 95.13%`, zero worlds under 95%).
  - **Ablation (`lab compare`):** Adding `fix_slot_state=True` on top of `inbound_hub_disc=0.07` alone gained **`+€205.42 ± 67.33` (`t = 3.05`, 11/5 better, `+0.18%` on-time)** across the 16 `dev` seeds, firing `slot_urgent_cleared = 2.25/wk` and `slot_kept_ontime = 7.25/wk`, cutting `fee_lost` from `€1,075.79/wk` to `€400.18/wk`. `priced_inbound_hub` fired `148.6/wk`.
- **32 fresh `night-01..night-32` worlds (`fc-v3T-night32` → `cp-margin-indisc07-fixslot-night32`):**
  - **Margin per won order:** `€38.07` → **`€39.09` (`+€1.02/order`)**, while winning **`+3.0` more orders/wk** (`297.9 → 300.9`).
  - **Ledger:** Revenue `€32,915.88 → €33,147.97` (`+€232.09`), **driver fees `-€21,009.38 → -€20,816.29` (`+€193.09/wk` cheaper total driver fees while moving 3 more cars/wk!)**.
  - **Counters:** `priced_inbound_hub = 156.1/wk`, `slot_urgent_cleared = 2.75/wk`, `slot_kept_ontime = 9.88/wk`, `fee_lost` cut `€1,190.54 → €465.54/wk`.
  - **Tail:** Cut worlds under 92% from **2 to 1** (rescuing `night-11` from `91.53% / €7,037.95` to **`93.44% / €7,589.56`**), and improved `night-15` from `90.57% / €18,363.87` to **`90.63% / €18,975.93`**.

## Verdict

**adopt `-s inbound_hub_disc=0.07 -s fix_slot_state=True` (for lead stack / `fix_slot_state=True` standalone)** — SAFE on all 16 `dev` worlds (`Δmargin €+307.36 ± 105.38`, `t = 2.92`, 11/5 better, min on-time `95.1%` vs `94.3%`, 0 under 92%) and confirmed on 32 fresh `night` worlds (`Δmargin €+420.96 ± 118.77`, `t = 3.54`, 24/8 better, worlds under 92% cut `2 → 1`, min on-time `90.63%` vs `90.57%`). Ran `scripts/promote.sh exp/gemini-cp-margin -s inbound_hub_disc=0.07 -s fix_slot_state=True`: `dev` (`+€307.36, t=2.92, min 95.1%`), `restart` (`dev-01` Wed 12:00 `96.1%`, ranked), and `holdout` SAFE + positive (`+€30.67 ± 144.74`, 9/7 better, 0 under 92%) all passed, while `hold-12` on-time min was `93.33%` (1 car below the `93.58%` = `94.08% - 0.5%` gate), so `main` was left untouched for the lead's co-play merge (`fix_slot_state=True` alone is `+€205.42 ± 67.33, t = 3.05` on `dev` without changing intake).
