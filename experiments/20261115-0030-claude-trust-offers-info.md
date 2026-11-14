# Trust first, shapes later, return offer at delivery, offers always, and what a desk can predict (Sun 15 Nov ~00:00–01:00)

His five questions after the status board. Scripts: `orc/loops1.py` (arms `ret6 ret9 off0 offa offu`), `orc/info.py`
(the information test), and two default-off switches on branch `exp/trust-first` (`trust_invest_top`,
`trust_invest_days` relative to the desk's first day, `cyc_from_day`). Sweeps: `runs/trust-sweeps.log`,
`runs/trustgain.log`; oracle arms: `runs/loops1-dev12-run4.log`.

## 1. Trust: how many dealers, how much is it worth, does investing early pay?
- dev-12: **40 dealers**, but very uneven: the top dealer sends 269 of 1,036 requests, the top 10 send 77%, the median
  dealer 8 a week. Big dealers reach 25 by themselves; small ones never matter.
- In the limits, trust is worth what the rules say: within a dealer, **+0.98% per count**. Under the desk that measured
  the limits, the mean count at a request was 6.7 of 25.
- Model (tape, won cars delivered ~22 h later): trust is ~9% of revenue at a 45% win share. Winning 65% on the first
  day adds ~€700 of trust over the week and costs ~€1,200 in price cuts that day (plus the margin of ~40 extra cars).
  So: a few hundred euros at best, as he guessed.
- **Live desk, 4 dev worlds** (v7 already has `trust_invest=0.05`: 5% off for the top 3 dealers Mon–Wed):
  | variant | Δ margin vs v7 |
  |---|---:|
  | no investment (0) | +€145 ± 104 |
  | 10% top 3 Mon–Wed | −€165 ± 240 |
  | 15% top 3 Mon–Wed | +€14 ± 247 |
  | 5% / 10% / 15%, top 10, first 2 days | −€106 ± 312 / −€20 ± 101 / **−€369 ± 47 (worse on 4 of 4)** |
  | Thursday start (`live_from_min=4320`): 10% top 10, Thu–Fri vs none | +€224 ± 223 |
  Investing harder in trust does not pay; the strong version loses on every world.
- Pricing the trust we have (`trust_gain`: quote × (1 + gain × count/100)), **16 dev worlds**: gain 0.5 −€32 ± 90,
  gain 1.0 **−€314 ± 126** (worse on 11 of 16). The desk's slow per-dealer learning already takes what there is.

## 2. Shapes from day 2 (only sure singles on day 1)
- Live desk: `cyc_from_day=1` −€66 ± 350, `=2` −€223 ± 191 (4 worlds). Holding cars for cycles on day 1 does not
  measurably hurt; no gain from waiting.

## 3. Return offer the minute the driver delivers (pairs, 178 chosen; the first car alone at 0.9×, the second held
## until the first is delivered, then posted at 0.9× and offered to that driver in the same minute)
- 87 offers sent: **at 0.6×: 1 accepted, 50 declined, 36 unread; at 0.9× (= the app fee): 2 accepted, 45 declined,
  40 unread.** They read it (more than half, against ~30% for other offers) and decline. Timing is not the problem: a
  driver who just finished a gig does not take a second one. Pairs must be sold as one gig.

## 4. Offers always, aimed vs unaimed (406 cars, each alone at 0.75×, raised to 0.9× after 2 h; offers at the gig's fee)
| arm | offers | accepted | booked | margin |
|---|---:|---:|---:|---:|
| none | — | — | 329 | €4,266 |
| aimed (viewed in last 6 h first) | 4,799 (3,498 to recent viewers) | **1** | 329 | €4,488 |
| unaimed | 4,833 | **2** | 329 | €4,256 |
- An offer **at the app fee** is worth nothing: the same drivers book the same gigs. The ~4% acceptance seen earlier
  came from offers priced **above** the app fee (0.75× while the gig showed 0.5×): an offer is a private raise, not
  free attention. (The chain arm's offers at its app fee: 9 of 1,934.)

## 5. How much is knowing the price worth? (`orc/info.py`, dev-12's 1,766 exact limits)
Each request priced on its own at the quote maximising (price − cost) × P(win) under a prediction of ln(limit/list);
cost 0.8× the typical fee; residual sd by 10-fold CV grouped by request. No driver capacity.
| what the desk knows | resid sd | margin | win | of perfect |
|---|---:|---:|---:|---:|
| A nothing | 0.237 | €46,563 | 66% | 54% |
| B before the week (option, menu, towns, hour) | 0.197 | €47,997 | 68% | 56% |
| C + trust (exact: we count it) | 0.196 | €48,203 | 68% | 56% |
| D + competitor steps (from our own daily win share per busy dealer) | 0.196 | €48,656 | 69% | 57% |
| E + day factor and dealer taste (live: only from wins/losses, an upper bound) | 0.167 | €51,110 | 73% | 60% |
| F + lane (in-sample floor) | 0.158 | €52,195 | 74% | 61% |
| P perfect: the oracle | 0 | €85,511 | 95% | 100% |
- Everything predictable together adds **~+10%** over knowing nothing; trust and the competitor's steps add ~€100–450
  each (within a dealer: +0.98% per trust count, +3.7% per competitor step). **Perfect knowledge is +64% over the best
  prediction.** Same picture at cost 1.0× and 1.15× (the best prediction reaches 53–57% of perfect).
- So the oracle's edge is almost all the irreducible noise, which no live desk can have. A live desk gains a few % from
  better prediction. Juhus's 1.58× is mostly **volume** (2,419 vs 1,659 orders, +46%) and only +9% per order: they
  staff more cars, which is the cost side (shapes, drivers), not the pricing side.
- The champion tracks trust per dealer but does not price it (`trust_gain` = 0); its per-dealer adjustment learns
  slowly from wins (`dealer_lr` 0.01). Nothing models the competitor's steps explicitly.

## 6. Who books the return-home shapes? (his question: they start outside the capital but need capital drivers)
From the booked gigs' drivers' homes (loops1 runs 1–3):
- chain home (106 booked): **41 by a driver living at the end (A), starting outside a pool** — exactly his pattern;
  20 more by end-drivers on chains starting in a pool; 24 by drivers near the start; 21 elsewhere.
- pairs (115 booked): 58 start in a pool and go to a driver there; of the 52 starting outside, 38 went to drivers living
  neither end within 30 km, e.g. Vantaa drivers on Hyvinkää loops (39 km).
- triangles: Helsinki drivers booked loops starting in Pori (224 km), Salo, Hyvinkää.
So drivers find gigs well beyond the 30 km notification ring; the app sells these shapes with no trick, at 0.5–0.65×
the typical fees, because the gig ends near home. Pairs and triangles are the clearly working part; the chain books
as cheaply but runs late (13%).

## 7. "Driver first" (his idea, ~01:00): find the driver inside the 15-minute quote window, then bid safely
- Not allowed literally: a gig's stops name orders, and an order exists only after the dealer accepts at `respondBy`;
  an offer needs a gig. So there is nothing to offer a driver before the car is won.
- What it would buy, tested directly: quote every thin-town car v7 declines (319 one-car slow requests, < 22 drivers
  near the pickup) at 0.92× its limit, post it at once at a fee that nearly guarantees a driver, raise to 1.4× after 2 h:
  | arm | booked | on time | margin |
  |---|---:|---:|---:|
  | posted at 1.0× typical | 296 of 300 | 98.0% | **−€153** |
  | posted at 1.2× typical | 300 of 302 | 98.0% | **−€2,596** |
- At 1.0× they book and arrive, but even at the oracle's prices they only break even. Knowing the driver in advance
  would not make them pay: a single car out there costs about what the dealer pays. Only a cheaper driver does
  (a shape that ends near the driver's home).

## What it says
1. Trust and competitor reactions are real but small levers for a live desk (hundreds of euros); investing in trust
   with price cuts loses.
2. Offers only work as a hidden raise; return offers after a gig don't work at any timing.
3. Prediction can't close the oracle gap; the live gains are on the cost side: shapes that end near the driver's home.
4. Thin-town single cars break even at best, even with perfect prices and a sure driver: v7 is right to decline them.
