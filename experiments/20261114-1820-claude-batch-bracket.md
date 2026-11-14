# batch-bracket: use the signals v6 ignores; the one with room, `batchId`, prices a batch's later cars from its earlier outcomes

- **Agent / branch / commit:** claude (the user's rules session) · `exp/claude-batch-bracket` · `c1d865a`
- **Date:** 2026-11-14 18:20 Helsinki
- **Idea from:** own, after mapping everything the API exposes against what v6 reads (the user: "make use of the extra data")

## Why we tried it
v6 reads no `forecast`, no `driver_late` (the free release), no `batchId`, no `driverPositions`, and only the
roster's counts. Before building anything, each was sized slot-free on v6's 16 finished dev worlds
(`experiments/scripts/signals_*.py`: events, reveal, roster and snapshot of each world, ~4 requests a world):

| signal | what the 16 dev worlds show | verdict |
|---|---|---|
| `driver_late` | **2 events in 16 worlds** (no_show 11, visit_failed 6) | nothing to win |
| `forecast` | 27 forecasts; orders touching a snow zone in its window are late 5.8% vs 4.3% **for the same towns without snow** (the raw 5.8% vs 2.7% is mostly the thin-town effect) | ~0.3 late orders a world: below what 16 worlds can show |
| roster `drops` | the roster is **live**: no driver's end-of-week drops are below our observed drops (0 of 487). With our drops removed, a driver's prior drops barely predict ours (10.8% for 0 prior, 14.9% for 4+); the raw table (0% vs 31%) is a tautology | weak, and the app does not let us choose who books |
| active viewers today (views × roster homes) | correlates 0.70 with the static roster count and does not separate late or warned orders within a static-supply bucket | no gain over the gate we have |
| **`batchId`** | **47% of requests** (7,861 of 16,554) carry one. Every batch is **one dealer and one yard**; 2–4 cars arrive within ~3 min (median), 5–14 within 15, bulk (15+) within 56 | the one with room |

The price structure, from tas-price's exact dealer limits on dev-12 (`limits-all.jsonl`, 1,788 exact (request, option)
pairs, log sd of limit ÷ list): all 0.237 · lane+option 0.168 · dealer+lane+option+day 0.112 · **batch+option+delivery
place 0.09–0.14**. So a won or lost quote in a batch tells us the price of the next car of the same option and
destination, and the rules let us act on it: *"A new quote for the same request replaces the earlier one"*, until
`respondBy`. An offline replay of v6's dev-12 batch quotes against those limits gave +€100–400 of revenue a week,
with the sign flipping for larger steps (`signals_batch_bracket_offline.py`).

## What changed
`src/spread_lab/policy.py`, all off by default (`batch_bracket=False` is v6 to the cent):
- `batch_bracket` — groups 1-leg requests by (batchId, option, delivery place). A win sets the group's low end
  (`priceCents ÷ list`), a loss sets the high end for every quoted option.
- The champion's price for a batch car is then moved: both ends known → the middle; wins only → at least the best win
  × (1 + `bb_up`, 0.04); losses only → at most the lowest loss × (1 − `bb_down`, 0.06). Never below v6's margin floor,
  never above `bb_cap` (2.5) × list.
- `bb_requote` (True) — when an outcome lands, the group's open quotes are replaced (while `now < respondBy`).
- `bb_neutral_learn` (True) — quotes the bracket moved skip `learn()`, so the multiplier keeps tracking normal quotes.
- `rejoin()` rebuilds the low ends from `order_won` history (lost prices are not in the history).
- Counters: `bb_won`, `bb_lost`, `bb_up`, `bb_down`, `bb_mid`, `bb_moved_at_quote`, `bb_requoted`, `bb_moved_won`,
  `bb_moved_lost`, `bb_skipped_learn`.

Run with: `uv run lab eval -s batch_bracket=true --name claude-bb-a-dev`

## Results (level 8, vs champion v6, paired; normal instrument)
| set | run folder | flags | mean margin | Δmargin ± SE | t | better/worse | on-time min | SAFE |
|---|---|---|---|---|---|---|---|---|
| smoke | `20261114-154202-claude-bb-noop` | none (no-op) | €12,000.96 | €+0.00 ± 0.00 | — | 0/0 | 93.4% | yes |
| smoke | `20261114-154520-claude-bb-a` | `batch_bracket` (0.04 / 0.06) | €12,146.81 | €+145.85 ± 70.21 | 2.08 | 4/0 | 94.4% | yes |
| smoke | `20261114-154816-claude-bb-b` | + `bb_up=0.06 bb_down=0.08` | €12,139.80 | €+138.84 ± 147.01 | 0.94 | 2/2 | 93.8% | yes |
| **dev** | `20261114-155411-claude-bb-a-dev` | `batch_bracket` (0.04 / 0.06) | €11,913.70 | **€+39.33 ± 96.68** | 0.41 | 8/8 | 94.4% | yes |
| dev | `20261114-155709-claude-bb-a-norequote-dev` | + `bb_requote=false` | €11,749.67 | €−124.70 ± 82.11 | −1.52 | 7/9 | 94.0% | yes |
| dev | `20261114-160122-claude-bb-downonly-dev` | + `bb_up=0` (down moves and the middle only) | €11,603.68 | €−270.69 ± 107.06 | −2.53 | 3/13 | 92.9% | yes |

Counters on smoke (per world): ~145 batch wins and ~200 batch losses recorded, ~50 quotes replaced, 3–11 moved at
quote time; of the moved quotes 12–32 won and 18–32 lost. Almost all of the effect comes through replacement: in
practice the runner answers at 10-minute step ends, so a car of a 2–4 batch (median spread 3 minutes) is usually
quoted before any outcome of its batch, and only replacement reaches it.

Per world on dev (v6: revenue €31,404, driver fees −€18,987, late refunds −€385, 285.9 won):

| arm | revenue | driver fees | late refunds | won | requoted | moved won / lost |
|---|---:|---:|---:|---:|---:|---:|
| A | €31,120 | −€18,713 | −€381 | 285.8 | 53.9 | 20.9 / 31.2 |
| A, no requote | €31,347 | −€19,043 | −€426 | 286.4 | — | 3.6 / 6.4 |
| down-only | €30,942 | −€18,714 | −€423 | 286.0 | 40.5 | 16.2 / 24.2 |

The bracket does not buy volume: every arm wins the same ~286 orders as v6. Lowering a batch after a loss gives
revenue away (−€462 against v6) without winning more cars, so the losses in a batch are not near misses. A's
+€39 comes from fees (−€274) against revenue (−€284), which is noise in where the week's drivers went, not the
mechanism.

## Verdict
**reject** — dev +€39 ± 97 (t 0.41, 8/8) for the main arm, −€271 ± 107 (t −2.53) for down-only; the tight spread
of limits inside a batch is real (log sd 0.09–0.14), but a 4–6% move on it is too coarse to beat v6's multiplier.
Flags stay off. The signals table above stands as measured: none of v6's unused signals carries a week's money.

Notes for the lead:
- **Practice understates replacement.** Live, the desk answers each `order_won`/`order_lost` as it streams, so an
  outcome reaches every later car of its batch whose `respondBy` has not passed; in practice only those whose
  `respondBy` is after the next 10-minute step end. The ablation says replacement is the part that pays (+€164
  between the arms on the same 16 worlds).
- **Without replacement it hurts** (−€125, t −1.5). The at-quote moves are few (3–11 a world), so the likely cause
  is `bb_neutral_learn` changing the multiplier's path, not the moves themselves. Not separated.
- The sizing tables above (snow, roster drops, active viewers, `driver_late`) are the jury's "what did not work":
  measured, then not built.
