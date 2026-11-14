# Ledger: what worked and what didn't

One line per idea that got a real measurement. Newest round first. Numbers are paired Δmargin a level-8 week
against the champion of the time, on the 16 dev worlds unless a set is named (± SE, t, better/worse); "fresh" is
32 unseen worlds (`night-01..32`). The detail is in each branch's note (`experiments/<date>-gemini-<slug>.md`).
Promotions are in [PROMOTIONS.md](PROMOTIONS.md); round 3 (ideas 15–30) is in `docs/HANDOFF.md`.

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
