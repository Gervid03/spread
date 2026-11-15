# Swarm Dispatch — what our desk does, why, and what each idea is worth

Written Sun 15 Nov ~08:00 for the jury and for our slides. Every number is a level-8 week. "Dev" and "holdout" are
two fixed sets of 16 practice worlds each; an effect is the **paired** difference in margin on the same worlds
(mean ± standard error, t), against the champion of the time.

## The answer
- **The desk that plays the final** (`41d3b46`, `spread_lab.policies.cycles:Desk` + `champion/champion.json`):
  **€12,564 a week on dev, €13,214 on holdout, 32/32 worlds ranked, mean on-time 95.9% / 96.2%.** The organisers'
  kit starter loses €72,612 on `spread-1` at level 8 (45.5% on time); our first ranked desk (v0) made €6,447 / €6,837.
- **Final:** _(to fill in after 09:20: margin, orders, on-time)_. **Best ranking round:** round 7 (Sat 15:00),
  **€70,230** over 5 worlds, 1,554 orders, all 5 ranked (the leader of a round makes €85–110k).
- **The big ideas**, in the order they paid: (1) only win cars we can staff, counting drivers by distance;
  (2) steer each request to the speed we can deliver; (3) fees that rise slowly, then a private raise to a driver who
  looked; (4) closed loops of cars as one gig, because most of a fee is the driver's trip home; (5) a morning
  supervisor that loosens or tightens the gates.

## How the desk decides (one request, one gig)
1. **Request arrives.** Count drivers who live within 30 km and 55 km of the pickup. Too few → decline (quote far
   above the list price: a losing quote costs nothing). A thin town (a "ring") is quoted only its slow options.
2. **Price.** Each option at list price × a multiplier. The multiplier starts at 1.35 (level 8) and tracks a 40% win
   rate online, globally and per dealer (which also absorbs dealer trust and the competitor's reactions).
3. **Won.** The car waits up to 2 daytime hours for partners that close a loop with it (A→B, B→A or A→B→C→A).
4. **Gig.** A loop goes out as one gig at 0.48× (2 cars) / 0.44× / 0.42× the summed typical fee; a single car at
   0.85× the typical fee, rising every daytime half hour to 1.6× by the deadline warning, then 1.65× → 2.25×.
5. **Driver looked and didn't book** → a direct offer at 1.03× the current fee to that local driver.

## Idea 1 — Win only what we can staff, and count drivers by distance (v0, v1, v3, v8)
- **The idea:** a request is quoted only if enough drivers live near the pickup (≥ 22 within 55 km; v8: ≥ 8); towns
  with few drivers within 30 km (< 15) get slow options only; an extended ring (≥ 30 drivers within 70 km) and
  "return to a hub" (a car ending where 200+ drivers live) admit some thin-town cars.
- **Why:** level 8 is a driver shortage that differs by town. The starter quotes everything and posts at the typical
  fee: most cars find nobody, and it loses €72,612 at 45.5% on time. A car's cost is mostly the driver getting there
  and home, so the number of drivers near the pickup predicts whether a car can be delivered.
- **The effect:** v0 (decline below 30 drivers within 30 km): ranked on 32/32, €6,447 dev. v1 (the 55 km gate +
  slow options in thin towns): **+€1,479 dev, +€1,106 holdout**. v3 (extended ring, return-to-hub, notes, lead-car
  pairing): **+€1,539 ± 265 dev (t 5.8), +€1,866 ± 248 holdout**. v8 (tonight: gate 8 drivers, ring below 15):
  **+€442 ± 130 dev (t 3.4), +€346 ± 164 holdout** — at a cost: the worst holdout world fell from 94.4% to 92.2% on time.

## Idea 2 — Fees: rise slowly, and make a private raise to a driver who looked (v2, v4, v5)
- **The idea:** open every single-car gig at 0.85× the typical fee and raise it in small steps through the day;
  reposts of lost or late cars open at 1.0×; when a local driver views a gig and doesn't book, send that driver a
  direct offer at 1.03× the current fee; after the deadline warning, a steep schedule (1.65× → 2.25×).
- **Why:** in the shortage a gig at the typical fee often finds nobody, but many cars find a cheap driver who lives near
  the delivery or is near the pickup. A slowly rising fee is a reverse auction: the cheapest driver who is looking books
  first. The handbook says drivers learn our raises and may wait; we measured that it costs less than it saves.
- **The effect:** v2 (0.85× opening, faster price tracker, 3 h slack): **+€1,064 dev, +€1,472 holdout**. v4 (lost
  orders repost at 1.0×): **+€355 ± 169 dev, +€423 ± 145 holdout**. v5 (offers to viewers, drop repricing, the steep
  schedule): **+€794 ± 139 dev (t 5.7, better on 16 of 16), +€567 ± 135 holdout**.
- **Against flat fees** (tonight, 16 dev worlds): flat at 0.9× / 1.0× / 1.1× lose **€1,517 / €1,515 / €2,551** a week
  (worse on every world); flat 0.9× also drops to 86.5% on time on its worst world.

## Idea 3 — Closed loops as one gig (v7)
- **The idea:** hold each won car up to 2 daytime hours; if cars close a loop (each delivery within 30 km of the next
  pickup, the last back near the first), post the loop as one gig at 0.48× / 0.44× / 0.42× the summed typical fee,
  repost it from each of its towns in turn every 15 minutes, and stop holding when the projected on-time share falls
  below 97.5%.
- **Why:** about two thirds of a typical fee is the driver's trip home. A driver who lives anywhere on a closed loop
  drives all of it and is home at the end. Fork probes (79 binary searches of what drivers accept): closed loops book at
  0.31–0.43× the summed typical fee, a single car at 0.78–0.84×.
- **The effect:** **+€247 ± 82 dev (t 3.0), +€410 ± 126 holdout.** Modest, because a live desk wins only ~25–45% of
  requests, so it rarely holds both halves of a loop: ~13% of won cars go in loops.
- **What the loop is worth when you can choose it** (our oracle harness, one world `dev-12`, the same won cars sent
  alone as control): closed pairs **+€1,597 (+52% margin), costs −19%**, booked at ~0.6×, on time 96.8% vs 99.4%;
  triangles **+€643, costs −21%**; pairs move 1.93 cars per driver-day, the same cars alone 1.35. Open chains book
  cheaply (0.65×) only when they end where many drivers live; elsewhere only after a raise to 0.9×.

## Idea 4 — A morning supervisor (v6)
- **The idea:** at 08:00 each day, classify the day from the projected on-time share, unstaffed orders due within 24 h
  and yesterday's deadline warnings. On a calm day it loosens the same-day gate (35 drivers instead of 50) and the
  slack by 15 minutes; on Friday with drivers to spare it opens slow options due Monday in thin towns. (Its "stressed"
  tightening exists but is switched off in the champion.)
- **Why:** the same gates are too strict on quiet days and too loose on busy ones.
- **The effect:** **+€195 ± 93 dev (t 2.1), +€187 ± 110 holdout.**

## What we learned about the game (measurements, not features)
- **Prices are half noise.** We measured every request's exact limit (the highest price that still wins) by binary
  search on copies of a world. Option, menu, towns, day, dealer, trust and the competitor's moves explain about half of
  the variance; the rest (sd 0.17 in log price) nobody can see. In a pricing test without driver limits, using
  everything predictable earns ~10% more than using nothing; perfect knowledge would earn +64% on top. A live desk
  can't have the noise, so the race is won on the driver side.
- **Dealer trust is real but small for us:** within a dealer, +0.98% accepted price per on-time order, as the rules
  say. Buying trust with early price cuts lost money (−€369 on 4/4 worlds at 15% off for the top 10 dealers).
- **Volume is capped by drivers' price, not their number:** 670–690 of 709 drivers view our gigs in a week; when we
  post more cars, more drivers book (305 vs 171). Each extra car needs a driver for whom it is cheap; past ~280–300
  cars a world, the marginal car earns about nothing at our fees.

## What did not work (each measured; Δ against the champion of the time, 16 dev worlds unless noted)
| idea | result |
|---|---|
| Find each car's fee by binary search with releases (post high, release when booked, repost lower) | −€15,180 on dev-12: release fees swamp the saving; drivers learned nothing |
| Direct offers at the app fee, aimed at recent viewers or not (~9,600 offers) | 3 accepted; no effect. An offer works only as a hidden raise |
| Offer the way back to a driver the minute they deliver the first car | 3 of 174 accepted |
| 4-car loops (oracle harness) | −€1,318: one missing car breaks the loop; 11% late |
| Bid to win the car that closes a loop | −€576 ± 164 (t −3.5); at a higher cap, a world at 88.4% on time |
| Flat fees instead of rising ones | −€1,515 to −€2,551, worse on 16 of 16 |
| A higher win-rate target (0.5 / 0.6) | +€198 ± 235 / −€161 ± 233; on top of v8 it drops a world to 89% |
| Thin-town single cars at a sure fee (oracle prices) | break-even at 1.0× the typical fee, −€2,596 at 1.2× |
| Same-day from thin towns into nearby hubs (e.g. Hyvinkää → Vantaa) | dev +€360 (t 1.9), holdout +€3; a 60-minute form left a world unranked (88.9%) |
| Open chains into a driver pool on the live desk | +€102 ± 117 (noise): few chains form among won cars |
| Price trust explicitly (quote × (1 + count/100)) | −€314 ± 126 (worse on 11 of 16) |
| An LLM that sets three dials each evening | no change on the mean |
| Per-class price trackers; an acceptance model with a lane-price prior | +€260 (t 1.4); −€137 to −€305 |

## What would break it, and what we don't know
- **Lateness on busy worlds.** v8's worst holdout world is 92.2% on time; ranking needs 90%. A world busier than any we
  tested could cross it. The desk's own lateness projection does not see it coming (it stays high until cars are late).
- **A late join.** Our first test final started on Thursday with Monday–Wednesday already played and lost: with no
  trust and no drivers placed, a day earned about half of a practice day (€2,448 for Thu–Fri).
- **A driver map unlike our practice worlds** (each world reshuffles which towns are thin): the gates count drivers, so
  they adapt, but the thresholds (8 / 15 / 22 / 30 drivers) were tuned on 32 worlds.
- **We don't know** how close our desk is to the best possible one: our oracle harness has the limits but not the
  in-run state, and it did not beat the live desk. The leaders make ~1.5× our margin with ~46% more orders, so the gap
  is how cheaply they staff extra cars, which we could only partly close (loops, thinner towns).

## Beyond the game
- **Sell a loop at every node.** In the game a gig has one first pickup and notifies drivers within 30 km of it, so we
  repost an unbooked loop from each town in turn. A real platform could show it to drivers near any of its towns at
  once; a loop is one driver's paid day that ends at home.
- **Show drivers the way home.** The cheapest driver for a car is one who lives near its delivery. Matching outbound
  and return cars into one trip is what freight brokers call backhaul; in a shortage it moves more cars with the same
  drivers (1.93 vs 1.35 cars per driver-day in our measurement).
