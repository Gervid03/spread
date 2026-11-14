# The cycle desk: closed 2-4 car tours as one gig (Sat 14 Nov, 18:45 Helsinki, the laptop lead with the user)

**Idea (the user's):** a driver who lives anywhere on a closed cycle of jobs (A→B, B→C, C→A) can drive all of it and end
at home, so the trip home, most of a single car's fee, is paid once for the whole cycle.

**Why:** tas-routes bisected driver fees on forks of dev-12 (79 forks): closed 2-4 car tours book at **0.31-0.43x the
summed typical fee (about €10 a road hour)**, single cars at 0.78-0.84x (€19-41 a road hour). Open chains (not ending
near home) save little (0.65-0.80x); short loops have a fixed cost (a 79-minute loop: 0.54x). With hindsight, tours
staffed the same quotes for +€2,228 on dev-12. But single cars book in 5-15 minutes and the return request comes 30-120
minutes later, so a desk that posts at once never sees a cycle.

**The rule** (`src/spread_lab/policies/cycles.py`, on tas-routes' `sunday_tours` and `tas_routes` desks, both taken from
`exp/gemini-tas-routes`): hold a won one-car order with 8 h of slack off the board for up to 120 daytime minutes; on every
change, search the closed cycles of 2-4 cars among held cars and open single gigs (30 km between a delivery and the next
pickup, and back home); post each as one flat gig (0.60x / 0.55x / 0.52x the summed typical fee for 2 / 3 / 4 cars) from
the feasible rotation whose start town has the most drivers; release the rest alone. The tour desk steps an unbooked tour
up and splits it back to single cars.

**Measured** (8 dev worlds, paired against v6):
| variant | Δ margin | t | better | on time |
|---|---|---|---|---|
| sunday_tours alone | +€217 ± 199 | 1.09 | 6/8 | -0.04 pt |
| **+ hold 120 + cycles (this candidate)** | **+€305 ± 62** | **4.96** | **7/8** | +0.06 pt, safe |
| + cycle-closing quotes up to 1.35x list, 50 km | -€255 ± 401 | -0.64 | 4/8 | one world under 90% |

On dev-12 in co-play, the cycle desk held 29 cars on Monday and formed no cycle from them: we win ~25% of requests, so
all legs of a cycle are rarely ours. Winning the closers cheaply buys cars but breaks on-time (row 3). The open question
is how to win the right closers without that.

Flags: `--policy spread_lab.policies.cycles:Desk -s sunday_tours=true -s sunday_stage_min=90 -s sunday_tour_quote=true
-s tour_dynamic=true -s cyc=true`. Co-play with cycles (the `tour` and `tourprobe` moves, the Cycles view) is on
`exp/claude-cycles`.
