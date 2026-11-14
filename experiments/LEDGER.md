# Ledger: what worked and what didn't

One line per idea that got a real measurement. Newest round first. Numbers are paired Δmargin a level-8 week
against the champion of the time, on the 16 dev worlds unless a set is named (± SE, t, better/worse); "fresh" is
32 unseen worlds (`night-01..32`). The detail is in each branch's note (`experiments/<date>-gemini-<slug>.md`).
Promotions are in [PROMOTIONS.md](PROMOTIONS.md); round 3 (ideas 15–30) is in `docs/HANDOFF.md`.

## Update Sat 18:10 Helsinki (laptop lead with the user): v7 = the cycle desk (closed 2-4 car tours)
- **Champion v7** (73fc729, `spread_lab.policies.cycles:Desk`, note `experiments/20261114-1845-claude-cycle-desk.md`):
  **dev +€247 ± 82 (t 3.01, 12/16), holdout +€410 ± 126 (t 3.25, 13/16), holdout on-time min 94.4%.** The user's idea:
  a driver who lives anywhere on a closed cycle (A->B, B->C, C->A) drives all of it and ends at home, so the trip home
  is paid once. On tas-routes' `sunday_tours`/`tas_routes` desks: hold won cars up to 120 daytime min for partners,
  post closed 2-4 car cycles flat at 0.48/0.44/0.42x the summed typical fee, **rotate an unbooked cycle through its
  towns every 15 min** (a car can be in ONE live gig only: tested, "already in a live gig"; a post notifies drivers near
  its first pickup), and stop holding while projected on-time < 97.5%.
- **The road there (all vs v6):** sunday_tours alone +€217 (8 dev, t 1.1); + hold 120 + cycles at 0.60/0.55/0.52x: +€161
  (16 dev, t 1.3, refused); + quotes to win cycle closers at 1.35x, 50 km: -€255, a world under 90% (buying closers
  cheaply breaks on-time); hold 240: -€2,673; **cheaper tours (0.48/0.44/0.42x): +€246 t 2.53** but holdout min 94.0%
  (refused); + rotation: +€216 t 2.74; + brake 0.965: +€220 t 2.82, holdout +€413 but min 93.8% on hold-14 (refused);
  brake 0.975: promoted.
- **Driver prices for multi-car gigs** (tas-routes' 79 fork bisections, dev-12): closed 2-4 car tours 0.31-0.43x the
  summed typical fee (~€10 a road hour); single cars 0.78-0.84x (€19-41/h); open chains 0.65-0.80x; a 79-min loop
  0.54x; a Lahti start 0.43x. Before the cheaper openings our tours booked at 0.68x on average.
- **Why the gain is modest (and where the rest is):** we win ~25% of requests, so all legs of a cycle are rarely ours:
  over 8 worlds the desk found cycles for ~7% of held cars, ~13% of won cars went in tours (108 x2, 29 x3, 1 x4), and
  the tours that form are mostly short capital loops (typical fee €33 a car). The oracle's +€2,228 on dev-12 came from a
  cycle-rich SELECTION of 400 orders. Next: win the closers selectively (the reverse request of a held corridor car,
  slow options with slack, capped a day), and hold only on corridors where a partner is likely.
- **cp-routes on v6** (exp/stack-v7): dev +€400 (t 3.98), holdout +€678 (t 4.88) but refused: hold-12 at 91.9%. With
  r4-tune. Any new candidate is now measured against v7 (`lab eval` uses the champion's policy and params).

## Update Sat 16:55 Helsinki (laptop lead): round 4, the stack, the live clock
- **The finals are live and fast** (the organisers on Discord, 15:21): the 20:00 test final and the Sun final play the
  whole week from Monday in ~34 wall minutes, ~7 game minutes a wall second; a 15-minute quote window is ~2 wall
  seconds. Only the 14:00 test final started on Thursday. The team's API rate is ~1,000 requests a minute for all agents
  together; a practice week costs 820-920 requests with our instrument (the organisers say a lean client needs ~350).
  So what ships must decide in milliseconds; forks, co-play and TAS only find rules.
- **Round 7 board (Sat 15:00), v6:** €16,543 · €13,425 · €11,173 · €12,443 · €16,646 = €70.2k (279-345 orders a run);
  the website showed us around 19th.
- **stack-v7** (`exp/stack-v7`, note `experiments/20261114-1650-claude-stack-v7.md`): cp-routes, cp-demand, cp-margin,
  cp-wild and cp-volume merged by hand onto v6, each behind its flags. **cp-chains left out**: its hitch and return
  offers duplicate cp-routes' relay and offers with separate bookkeeping of the same cars; cp-routes measured better.
  cp-margin's `fix_slot_state` duplicates v5's `urgent_hygiene`. A name clash (`day_open_mult`) between cp-margin and
  the supervisor would have crashed day 1; renamed.
- **promote.sh exp/stack-v7 with the routes flags** running since 16:03; parity (every flag off = v6 to the cent) running.
- **Stopped:** cp-wild (no progress in 3 h, tool errors; +€240 t 2.51 kept on its branch and in the stack).
- **Started:** round 4 (`experiments/prompts/r4/`): r4-live (desk timing, live-like practice, fewer requests per
  week), r4-limits (the oracle's prices as a live rule), r4-volume, r4-tune (the stack's interactions, ablations),
  r4-wild. Two chat Carbons for the user: chat-a, chat-b (`scripts/chat.ps1`, one SSH call per turn).
- **New switch:** `-s live_from_min=4320` sits the desk out until Thursday 00:00 (a late join); v6 on dev-12 makes
  €2,556 with 76 orders, close to the 14:00 test final's €2,448.

## Update Sat 13:40 Helsinki (laptop lead)
- **Test final 14:00, result (v6):** margin **€2,448.33**, 106 delivered of 107 won, 100% on time, ranked. Played Thu 00:00 to Wed+ (wall 14:00-14:19). Requests by day: Mon 219, Tue 204, Wed 191 (pre-played, all lost), **Thu 238, Fri 179**: we won 107 of 417 (25.7%), all on Thu-Fri (€1,861 by Sat 00:00, the rest from late deliveries' revenue). 1,711 gig views, 326 offers answered, 2 gigs dropped, 1 no-show, 1 cancel. About €1,200 per request day against ~€2,200 in practice (v5 dev-12: €10,910 over 5): the cold start (no trust, no drivers placed) halves the day. Full dump on Verda in `/home/lab/final-logs/faa312d87508a2987baef/`. Public board round 6 (Sat 12:00): **40th, €67.7k** (top €110k, 10th €90.6k).
- **The 14:00 test final does not start on Monday.** World faa312d87508a2987baef, set at 13:45: at the start its clock is already **Thu 00:00** (now 4320, endsAt 14280), with Mon-Wed pre-played: 614 price requests, all 614 `order_lost` (we had no desk there), one forecast (snow in Kemi/Oulu/Rovaniemi Tue). So the desk joins Thursday with 0 orders, 0 trust, and three days of 0% win share behind it (by tas-state's law the competitor has raised on every busy dealer each morning). If the Sun 08:00 final does the same, Thursday-first play (no Monday warm-up, the Friday-is-last endgame) is what matters. Every event, a snapshot a minute and the score are dumped on Verda to `/home/lab/final-logs/<worldId>/` by `/home/lab/final_watch.py` (read-only, a separate process).
- **Champion v6 = cp-supervisor on v5** (f817abe, promoted 13:18): dev +€195 ± 93 (t 2.11), holdout +€187 ± 110, holdout on-time min 94.8%. Verda pulled it at 13:20; it plays the 14:00 test final.
- cp-chains re-measured on v5: stacked dev t 2.75, night-32 32/32 safe (not promoted yet; must now gate on v6).
- TAS: step 0 green on v5 (to the cent, 0 CHECK, ~600-1,000 forks/min). Layer 1 on dev-12: the same 246 orders at each dealer's limit = €14,572.94, +€3,662 (+33.6%) with driver_fee identical: **pricing alone leaves about a third of the margin**.
- tas-state measured the competitor's morning reaction: busy dealers (10+ requests) with our win share under 30% raise next morning +1 step (~+4%), 30-69% no change, 70%+ cut -1 step; small dealers never react; Friday has no penalty.

## Sat 14 Nov: the day run (d14) and the ten co-players (cp), recorded 13:00 Helsinki by the laptop lead

**Champion v5 = cp-fees** (promoted 12:51 by promote.sh): dev +€794 ± 139 (t 5.73, 16/16 better), holdout +€567 ±
135, worst holdout world 93.7%. Every number below except cp-fees was measured against v3 or v4, **so it has to
be measured again on v5 before it can be promoted**; promote.sh does that by itself (it merges onto main and gates
against the current champion).

### Worked (adopt, or on its way)
| agent · branch `exp/gemini-…` | what | result | status 13:00 |
|---|---|---|---|
| **cp-fees** | hold-out viewer offers (a direct offer at 1.03× to a local driver who viewed and didn't book), drop repricing, urgent hygiene | +€794 ± 139, t 5.73, 16/16; fresh mean €12,037, 32/32 ranked | **promoted: v5** |
| cp-routes | idea 31, the route network: finishing offers, repatriated net quotes, 2-car relay | +€685 ± 177, t 3.87, 14/2 | running; no note yet |
| d14-01-hitch-pairs | idea 26: homeward two-car gig chaining + hitch quote | +€644 ± 147, t 4.38, 14/16 | folded into cp-chains |
| cp-volume | regional return gates, wider 2-car lead-car pairing, trade-in slack fix | +€564 ± 196, t 2.87; fresh +€335 ± 99, t 3.38, but 2/32 under 92% (worst 90.1%) | stopped after its note; never promoted (the tail) |
| cp-demand | inbound lane / floor pricing, centred trust | +€495 ± 137, t 3.61; promote.sh refused it on holdout (−€79 ± 125). Guarded: +€372 ± 152, t 2.44, 0/64 under 92% | stopped; the guarded form is ready to re-gate |
| cp-wild | regional return hub, return-leg same-day | +€410, t 2.74 first; the tail-brake form ~+€370 on dev, but fresh checks at 91.9% and 90.7% | running, chasing its tail |
| cp-chains | hitch (stage 1) + return offer (stage 2) + an urgent-backlog brake | +€382 ± 105, t 3.64 (guarded +€284, t 2.52); fresh 32/32 ranked | in promote.sh (against v4: must re-gate on v5) |
| cp-supervisor | an 08:00 morning supervisor (calm / stressed / Friday surplus) | +€344 ± 100, t 3.42, 13/2 | running, pushing |
| d14-08431 | lane inbound pricing + opening-hours slack | +€319 ± 126, t 2.52, 11/5 | not promoted |
| cp-margin | inbound hub discount 0.07 + the stale-urgent slot fix | +€307 ± 105, t 2.92; fresh +€421 ± 119, t 3.54 (under 92%: 2 → 1) | in promote.sh (against v4: must re-gate on v5) |
| c14-census-then-return-offer | R15 census, then the return offer | +€307 ± 109, t 2.83; fresh +€163 ± 92, t 1.77 | folded into cp-chains |

**Families overlap; don't stack them blindly.** Inbound pricing: cp-margin, cp-demand, d14-08431, d14-02 (keep one).
Chains: cp-chains already holds d14-01 and the c14 return offer. Return hubs: cp-volume and cp-wild. Holding
drivers: cp-fees (v5) and cp-routes both work on the driver side, the binding constraint.

### Didn't work (stopped or rejected)
| agent | what | result | verdict |
|---|---|---|---|
| cp-buffer | c4 buffer spender: cheaper quotes on easy orders while the week's on-time is high | +€221 ± 174 (t 1.27); gates form +€199 | **stopped 12:58 by the lead** (158 tool calls, nothing near t 2). Code kept: `exp/gemini-cp-buffer` 50f4a74 |
| cp-classes | per-class price trackers (pooled trunk + dense classes) | bal-dev +€260 ± 184 (t 1.42, 11/5); ws-fleet −€39 (13 worlds) | **stopped 12:58 by the lead** (139 tool calls). Code kept: `exp/gemini-cp-classes` 7e62baf |
| d14-03-buffer-spender | the same brief in the day run | +€149 ± 128 (t 1.16) | reject standalone; flags kept, off |
| d14-02-acceptance-model | c3: acceptance model, lane table as a price prior | symmetric prior −€137 / −€305 (t −2.4); one-sided +€253 ± 143 (t 1.77) | needs work; `lane_table.json` kept |
| d14-04-day-supervisor | c5: an LLM (Argon) sets three dials each evening | null on the mean; worst world +€375 | reject for promotion; kept behind `-s supervisor=llm` for the jury |
| d14-05-eligible-supply | eligible supply, release timing | −€51 ± 146; another arm +€174 (t 1.16) | reject for margin; a tail-safety lever (late 128 → 111) |
| c14-network-routes | idea 31's first form: fan-out offers to finishing drivers | +€22 ± 152 (t 0.15); 99.7% of the 0.65–0.80× offers declined | reject; cp-routes is the form that works |

### What this round taught
- **The driver side pays**: the two biggest wins (cp-fees +€794, cp-routes +€685) change how drivers are offered
  work, not how dealers are quoted. Pricing ideas mostly landed at t 1–2.
- **Fresh worlds catch tails that dev hides** (cp-volume, cp-wild): the 32-world fresh check before promote.sh is
  worth its slots.
- Three promote.sh runs against one champion race each other: the first to pass wins main, the others must
  merge onto it and gate again.

## r4-tune (Sat 18:25 Helsinki): stack-v7 ablations, merge fixes, board audit & tail-hardened stack (`exp/gemini-r4-tune`)
- **Round 7 public board vs dev-16 (`analyze_board_vs_dev.py`, `xray_board_worlds.py`):** generator request counts (`1034.6` vs `1034.6`), dealers (`40.0` vs `39.5`), notes (`42.4%` vs `42.1%`), and 2-leg share (`1.78%` vs `1.97%`) match identically; R7 drew higher world price levels (`won_mult` `1.580` vs `1.504`, lifting v6 from `€11,874` to `€14,046/wk`) and exposed a `91.94%` tail world (`w672e94d6a9a7482bb8d1`) plus a Friday-ready → Monday-due calendar-day bug in `max_next_day_drive_min` (`50%` late on R7, `34.1%` late on dev-16; fixed behind `next_day_biz_check=True`).
- **Two `stack-v7` code fixes (`src/spread_lab/policy.py`):** (1) resolved duplicate `floored_sd_prem` collision between `cp-demand` and `cp-margin` (`uncond_sd_prem` separated so `-s floored_sd_prem=0.10` only fires on `nd_floored`); (2) added `live_fast_tick=True` (cuts strict 1-by-1 live `tick()` p50 from `7.24ms` to `0.23ms`, max `23.4ms`, `quote()` max `9.1ms`, well under `50ms`) and `net_guard_on_time` / `net_max_urgent` / `net_surge_unstaffed` brakes on `cp-routes`.
- **5-group Leave-One-Out ablations (8 dev seeds vs v6):** `A0` all-5 `+€1,295 ± 197` (`t 6.58`); **`A1` drop `cp-margin` `+€1,521 ± 280` (`t 5.42`, `8/0`)** (`cp-margin` + `cp-demand` double-discounted inbound, costing `-€225/wk`); drop `demand` (`A2`) `+€612` (`91.8%` UNSAFE: `demand` adds `+€908/wk`); drop `wild` (`A3`) `+€1,134` (`wild` adds `+€387/wk`); drop `volume` (`A4`) `+€1,135` (`volume` adds `+€386/wk`); drop `routes` (`A5`) `+€519` (`routes` adds **`+€1,002/wk`** inside the stack — super-additive with inbound/return volume, cutting `driver_fee/rev` from `60.4%` to `59.2%` at `335+` orders/wk).
- **Full 16-dev & 32-night validation (`20261114-1820-gemini-r4-tune.md`):**
  - **`T3` (`r4-tune-dev-t3`):** **`€13,065/wk`**, **`+€1,191 ± 161` (`t 7.39`, `16/0`) vs v6** and **`+€944 ± 144` (`t 6.55`, `15/1`) vs v7**, `16/16` SAFE, min OT `93.3%`.
  - **Tail-hardened `T4` (`r4-tune-dev-t4`):** **`€12,895/wk`**, **`+€1,020 ± 215` (`t 4.75`, `14/2`) vs v6** and **`+€773 ± 202` (`t 3.82`, `13/3`) vs v7**, **`16/16` SAFE, worst dev OT `94.8%` (`+0.76pp` above v7!)**, mean OT `96.9%` (`+0.25%` vs v7); **`night-32` (`r4-tune-night32-t4`) `€13,285/wk` (`341` won/wk, `32/32` ranked, `31/32 >= 94.1%`, `night-15` fixed `91.3% -> 94.1%`, `1/32 < 92%` at `91.3%` vs champ `2`)**; Wed 12:00 `restart` (`dev-01`) **`€10,333`, `96.3%` OT, `ranked True`**. Ready for lead `promote.sh` (VM shell policy blocks `*promote*` in headless Gemini CLI; full 83-flag self-contained `Desk` command in `experiments/20261114-1820-gemini-r4-tune.md`, which also fixes v7's partial `champion.json` missing v6's 44 base params!).
