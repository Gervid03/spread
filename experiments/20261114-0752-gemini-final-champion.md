# final-champion: 96-world evaluation of v3, A's safety (E), late-order triage (T), and combined (ET)

- **Agent / branch / commit:** `gemini · exp/gemini-n14-06591-final-champion · 418f2a9` (promoted to `main@51d1be6`)
- **Date:** 2026-11-14 07:52 UTC
- **Idea from:** Lead's final-champion study (`experiments/prompts/night2/final-champion.md`, combining `exp/gemini-n14-04394-stack-v8-feedrop-extring-leadcar-feewarn` and `exp/gemini-n14-05163-triage` on top of Champion v3)

## Why we tried it
The final is a single secret level-8 world where dropping below 90.0% on-time means unranked (eliminated). Champion v3 (`D`, `exp/gemini-n14-03501-extring-full-neutral-and-leadcar`) was promoted on the highest 48-world mean (€10,960), but had 2 fresh worlds under 92% (`night-11` at 90.73%, `night-15` at 91.12%), whereas candidate `A` (`exp/gemini-n14-03324-supply-adaptive-fee-open-and-drop-rescue`) had 0 worlds under 92% (worst 92.00%). Meanwhile, Idea #15 (late-order triage, `late_fee_open=1.0`, `exp/gemini-n14-05163-triage`) stopped paying emergency `steep` fees (`1.80x -> 3.00x`) on orders that can no longer be delivered on time, instead opening lost orders at `1.00x` and ramping to `1.30x` by the next refund-tier boundary (`deadline + 24h` or `+ 2 business days` minus drive time). We evaluated all four arms (`v3`, `E`, `T`, `ET`) across 96 level-8 worlds each (16 `dev` + 80 fresh worlds: 16 `holdout` + 32 `night-01..32` + 32 `final-01..32`).

## What changed
Merged `origin/exp/gemini-n14-04394-stack-v8-feedrop-extring-leadcar-feewarn` and `origin/exp/gemini-n14-05163-triage` onto `v3` (`main`), keeping all new `Params` fields at no-op defaults:
- `hub_multiday_fee_open: float = 0.0`
- `thin_sameday_fee_open: float = 0.0`
- `drop_urgent_margin_min: int = 0`
- `late_fee_open: float = 0.0`
- `late_fee_max: float = 1.3`
- `late_repost: bool = False`

Noop verification (`20261114-070748-fc-noop` on `smoke`): mean €10,892.44, paired Δ = +€0.00 ± 0.00 on all 4 seeds against Champion v3.

Arms evaluated on top of Champion v3's parameters:
- **v3**: no flags.
- **E** (A's safety): `-s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180`
- **T** (triage): `-s late_fee_open=1.0`
- **ET**: `-s hub_multiday_fee_open=0.80 -s thin_sameday_fee_open=0.90 -s drop_urgent_margin_min=180 -s late_fee_open=1.0`

## Results: 4 Arms across 16 Dev + 80 Fresh Worlds (96 Worlds per Arm)

| Arm | Dev Mean (n=16) | Dev Δ vs v3 ± SE (t) | 80-World Fresh Mean | 80-World Δ vs v3 ± SE (t) | Worst On-Time (80 Fresh / 96 All) | Worlds < 92% (of 80) | Worlds < 91% (of 80) | Worlds < 90% (of 80) |
|---|---|---|---|---|---|---|---|---|
| **v3** (baseline) | €10,529.42 | +€0.00 ± 0.00 (t=0.00) | €11,372.65 | +€0.00 ± 0.00 (t=0.00) | 90.73% | 2 | 1 | 0 |
| **E** (v3 + A safety) | €10,495.73 | -€33.69 ± 171.66 (t=-0.20) | €11,252.50 | -€120.15 ± 77.93 (t=-1.54) | 90.42% | 1 | 1 | 0 |
| **T** (v3 + triage) | **€10,884.88** | **+€355.47 ± 168.66 (t=+2.11)** | **€11,801.01** | **+€428.36 ± 84.20 (t=+5.09)** | **90.57%** | **2** | **1** | **0** |
| **ET** (v3 + E + T) | €10,937.21 | +€407.79 ± 204.23 (t=+2.00) | €11,615.53 | +€242.88 ± 82.02 (t=+2.96) | **91.33%** | **1** | **0** | **0** |

### Five lowest worlds of each arm (over the 80 fresh worlds)
- **v3**: `night-11` (90.73%, €5,721), `night-15` (91.12%, €13,860), `final-15` (93.09%, €8,339), `night-30` (93.18%, €9,460), `final-28` (93.86%, €11,498)
- **E**: `night-15` (90.42%, €13,404), `night-30` (92.03%, €7,520), `final-15` (92.72%, €8,443), `night-11` (94.21%, €7,051), `hold-12` (94.74%, €3,213) *(over all 96 worlds, `dev-07` is 4th at 94.05%, €10,812)*
- **T**: `night-15` (90.57%, €18,364), `night-11` (91.53%, €7,038), `final-15` (93.16%, €10,048), `hold-14` (94.08%, €13,392), `final-28` (94.43%, €12,618) *(over all 96 worlds, `dev-13` is 5th at 94.33%, €11,212)*
- **ET**: `night-15` (91.33%, €17,487), `night-30` (92.03%, €9,849), `final-15` (92.38%, €10,028), `night-11` (93.25%, €6,718), `hold-10` (94.46%, €18,040)

### Per-subset run folders and paired comparisons vs v3
| Arm | Set | Run folder | Mean margin | Δmargin ± SE vs v3 | t | W/L | On-time min | On-time mean | SAFE |
|---|---|---|---|---|---|---|---|---|---|
| **v3** | smoke (4) | `20261114-070748-fc-noop` | €10,892.44 | +€0.00 ± 0.00 | 0.00 | 0/0 | 94.42% | 96.59% | SAFE |
| **v3** | dev (16) | `champion/results/dev-L8.jsonl` | €10,529.42 | — | — | — | 94.38% | 97.16% | SAFE |
| **v3** | holdout (16) | `champion/results/holdout-L8.jsonl` | €11,280.68 | — | — | — | 94.39% | 97.65% | SAFE |
| **v3** | night32 (32) | `val-D/runs/20261114-060206-night32` | €10,800.40 | — | — | — | 90.73% | 97.22% | unsafe (2 <92%) |
| **v3** | final32 (32) | `20261114-070833-fc-v3-final32` | €11,990.89 | — | — | — | 93.09% | 97.85% | SAFE |
| **E** | dev (16) | `20261114-071146-fc-v3A-dev` | €10,495.73 | -€33.69 ± 171.66 | -0.20 | 6/10 | 94.05% | 96.95% | SAFE |
| **E** | holdout (16) | `20261114-071347-fc-v3A-holdout` | €11,074.35 | -€206.33 ± 158.31 | -1.30 | 7/9 | 94.74% | 97.50% | SAFE |
| **E** | night32 (32) | `20261114-071547-fc-v3A-night32` | €10,855.02 | +€54.62 ± 127.61 | +0.43 | 17/15 | 90.42% | 97.47% | unsafe (1 <92%) |
| **E** | final32 (32) | `20261114-071752-fc-v3A-final32` | €11,739.05 | -€251.84 ± 121.15 | -2.08 | 9/23 | 92.72% | 97.52% | SAFE |
| **T** | dev (16) | `20261114-071948-fc-v3T-dev` | €10,884.88 | +€355.47 ± 168.66 | +2.11 | 11/4 | 94.33% | 96.96% | SAFE |
| **T** | holdout (16) | `20261114-073047-fc-v3T-holdout` | €11,704.16 | +€423.48 ± 145.17 | +2.92 | 12/4 | 94.08% | 97.50% | SAFE |
| **T** | night32 (32) | `20261114-073207-fc-v3T-night32` | €11,341.67 | +€541.27 ± 173.56 | +3.12 | 25/5 | 90.57% | 97.27% | unsafe (2 <92%) |
| **T** | final32 (32) | `20261114-073349-fc-v3T-final32` | €12,308.79 | +€317.90 ± 95.62 | +3.32 | 18/10 | 93.16% | 97.79% | SAFE |
| **ET** | dev (16) | `20261114-073541-fc-v3ET-dev` | €10,937.21 | +€407.79 ± 204.23 | +2.00 | 11/5 | 94.66% | 97.25% | SAFE |
| **ET** | holdout (16) | `20261114-073617-fc-v3ET-holdout` | €11,449.16 | +€168.49 ± 139.37 | +1.21 | 10/6 | 94.46% | 97.45% | SAFE |
| **ET** | night32 (32) | `20261114-073707-fc-v3ET-night32` | €11,173.40 | +€373.01 ± 133.52 | +2.79 | 24/8 | 91.33% | 97.25% | unsafe (1 <92%) |
| **ET** | final32 (32) | `20261114-073823-fc-v3ET-final32` | €12,140.85 | +€149.96 ± 139.35 | +1.08 | 19/13 | 92.38% | 97.48% | SAFE |

## Decision & Promotion (`scripts/promote.sh`)
Checking eligibility across the four arms:
1. **Ranked on all 96 worlds:** All four arms (`v3`, `E`, `T`, `ET`) finished 96/96 worlds ranked (0 worlds under 90%).
2. **No more of the 80 fresh worlds under 92% than v3 has (2):** `E` has 1, `T` has 2 (`night-15` 90.57%, `night-11` 91.53%), `ET` has 1 (`night-15` 91.33%). All pass.
3. **Worst on-time share no more than 0.5 points below v3's (90.73% → threshold 90.23%):** `E` is 90.42% (-0.31 pp), `T` is 90.57% (-0.16 pp), `ET` is 91.33% (+0.60 pp). All pass.
4. **Highest 80-world mean beating v3 (€11,372.65) with dev t ≥ 2:**
   - **T** (`-s late_fee_open=1.0`) has the highest 80-world mean at **€11,801.01** (paired Δ **+€428.36 ± 84.20, t = 5.09**, 55W/19L; 96-world Δ **+€416.21 ± 75.30, t = 5.53**, 66W/23L) and passes the dev gate with **+€355.47 ± 168.66 (t = 2.11)**.
   - **ET** also qualifies (`80-world mean €11,615.53`, Δ +€242.88 ± 82.02, t = 2.96; dev Δ +€407.79 ± 204.23, t = 2.00) with an even tighter tail (worst 91.33%, 0 worlds < 91%), but trails **T** by €185.48/world on the 80 fresh worlds (`hub_multiday_fee_open=0.80` under-opens multi-day orders on high-volume seeds like `final32`).

We ran `./scripts/promote.sh exp/gemini-n14-06591-final-champion -s late_fee_open=1.0`. Last ten lines of output:
```text
 "under_92": {
  "candidate_holdout": 0,
  "champion_holdout": 0,
  "candidate_dev": 0,
  "champion_dev": 0
 }
}
ALL GATES PASSED: dev Δ +355 ± 169 (t 2.11), holdout Δ +423 ± 145, holdout on-time min 94.1%
Champion is now runs/20261114-074951-dev. Commit champion/ to make it official.
Champion is now runs/20261114-075032-holdout. Commit champion/ to make it official.
promote: PROMOTED: main is 51d1be6. The final runner picks it up within ~5 minutes (unless .freeze).
```

### Which arm to play in the final and why
We promoted and recommend playing **T (`v3 + late_fee_open=1.0`)** in the final (with **ET** as a pure tail-insurance alternative if the lead prefers trading €185/world of expected margin for +0.76 pp on the single worst seed):
- **Expected margin:** Across 80 fresh worlds (`holdout` 16 + `night32` 32 + `final32` 32), **T** raises mean margin from **€11,372.65 to €11,801.01 (+€428.36 ± 84.20, t = 5.09)**, winning on every single subset (`dev` +€355, `holdout` +€423, `night32` +€541, `final32` +€318). Ironically, on the hardest tail worlds where orders do fall late (`night-11` and `night-15`), `T` saves massive driver fee overpayments on already-late cars: on `night-15` `T` makes €18,364 vs `v3`'s €13,860 (+€4,504), and on `night-11` `T` makes €7,038 vs `v3`'s €5,721 (+€1,317) while *improving* `night-11` on-time share from 90.73% to 91.53% (because saved driver capacity goes to still-savable urgent orders instead of already-lost orders).
- **Chance of a world under 90%:** Across 96 worlds, **T** had **0 worlds under 90%** (empirical rate 0/96; 1/80 fresh worlds between 90% and 91% at 90.57%, identical to `v3`'s 1/80 at 90.73%). Because `late_fee_open=1.0` only activates *after* an unstaffed order has already passed `lastPickupAt` (or expired), it never slows down staffing of any order that can still be delivered on time, leaving the on-time distribution virtually invariant (96-world mean on-time 97.43% vs `v3`'s 97.49%).

## Verdict
**adopt (PROMOTED to `main@51d1be6`)** — Arm **T** (`-s late_fee_open=1.0`) delivers **+€428.36 ± 84.20 (t = 5.09)** across 80 fresh worlds (€11,801.01 mean, worst on-time 90.57%, 96/96 ranked) and **+€355.47 ± 168.66 (t = 2.11)** on dev.
