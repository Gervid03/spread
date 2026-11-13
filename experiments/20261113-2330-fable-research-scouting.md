# research-scouting: what seven finished worlds say about where the margin and the late orders are

- **Agent / branch / commit:** Fable (lead's scout) · main
- **Date:** 2026-11-13 23:00–23:45
- **Idea from:** own (grounding for the rewrite of `IDEAS.md`)

## Question
Before proposing ideas: where does v0 leave money, and which orders are late? No new worlds were played. I
revealed seven finished ones (one request each):

| Set | Worlds | Desk |
|---|---|---|
| A | dev-03, dev-11, dev-04, hold-10 (from `champion/results/`) | v0 (`min_supply` 30, win target 0.35) |
| B | dev-01, dev-03, dev-04 (from `runs/20261113-215255-s1-…min_supply6-fee_warn1.6`) | `min_supply` 6, win target 0.55: 375–397 orders, 82–91% on time |

Scripts: `experiments/scripts/scout_*.py`. Each takes a folder of `reveal-<world id>` folders
(`uv run lab reveal <world id>` writes one; run it outside the repo). Four and three worlds are small
samples: treat every share below as a lead to confirm (research item R2), not as a result.

## The map and the demand (set A)
- 30 places, 651–886 drivers a world. Within 30 km: Helsinki, Espoo and Vantaa 327–444 (one pool); Oulu
  33–118; Tampere and Lempäälä 31–60; Turku and Raisio 41–168; Jyväskylä 28–53; everything else under 60,
  most under 25.
- **Hyvinkää:** 173, 200, 219, 203 pickups of ~1,035 requests, and 122, 135, 147, 112 deliveries. Drivers
  within 30 km: 20, 5, 8, 22. Straight-line distance to Vantaa 39 km, Espoo 49 km, Helsinki 51 km.
- Requests whose pickup has under 30 drivers within 30 km (all declined by v0): 395, 455, 528, 427.
- D01 sends 282–372 requests a week, mostly from one yard (Vantaa in three worlds). The dealer whose yard is
  Hyvinkää is D02 in three worlds and D03 in one. 39–40 dealers; half send fewer than 10 requests.
- 144–152 `batchId`s a world: about 45% of requests. Most batches have 2–4 cars; 3–6 a world have 10–40.
- 64–67% of requests of 60 km or more have a request on the reverse lane (within 30 km at both ends) on the
  same or the next day.

## Which orders are late (set A: 791 orders, 41 late)
| Class | Orders | Late |
|---|---|---|
| Capital pickup, `same_day` | 302 | 10 (3.3%) |
| Capital pickup, `next_day` | 229 | 8 (3.5%) |
| Other pickup, `same_day` | 109 | 16 (14.7%) |
| Other pickup, `next_day` | 108 | 7 (6.5%), 3 of them one Turku → Rovaniemi batch |
| `within_3_days`, anywhere | 43 | 0 |
| Drive of 500 km or more, any option | 104 | 14 (13.5%): `next_day` 10 of 80, `same_day` 4 of 15 |

- 30 of the 42 orders with a `deadline_close` ended late; 11 late orders never had one.
- Orders with a drop: 73, of which 7 late. Orders with a failed visit: 16, of which 2 late.
- dev-04 (93.0%, v0's worst): a 20-car `same_day` batch from Lempäälä, 10 won, 5 late.
- About 10 of the 41 late orders carried a note on delivery hours, pickup hours or a tighter deadline.
- dev-11 (v0's lowest margin, €3,169): orders of 500 km or more lost €1,612 on 22 orders.

## What happened when the desk did take thin towns (set B: 1,168 orders)
| Class | Orders | Late | Notes |
|---|---|---|---|
| Hyvinkää pickup, `next_day` or `within_3_days` | 50 | 1 | margin €20–43 an order; median fee 1.0–1.03× typical; booked in ~30–40 min |
| Hyvinkää pickup, `same_day` | 120 | 9 (7.5%) | 58% of all Hyvinkää bookers live in the capital ring |
| Capital pickup, `same_day` | 454 | 65 (14%) | against 3.3% at v0's volume (75 a week): a daily ceiling |
| Capital pickup, `next_day` | 213 | 17 (8%) | |
| 30–200 drivers, `same_day` | 120 | 29 (24%) | |
| 30–200 drivers, `next_day` | 61 | 5 (8%) | |
| Under 30 drivers (not Hyvinkää), `same_day` | 85 | 27 (32%) | margin negative in two of three worlds |
| Under 30 drivers (not Hyvinkää), `next_day` | 44 | 7 (16%) | |

## Fees and drivers (set A)
- Booked fee ÷ typical fee: the median is 1.00 in every world and every distance band; 60% of bookings are at
  exactly the opening fee. Booked within 5 minutes of the first post: `same_day` 63–81%, `next_day` 55–61%.
  Median number of drivers who had viewed the gig when it was booked: 3.
- `next_day` orders booked on the post day cost 1.01–1.03× typical; those booked later 1.21, 1.65, 1.32, 1.21
  (12–19 orders a world).
- Who books: 68–80% live within 30 km of the pickup, 6–10% within 30 km of the delivery, the rest elsewhere.
  28–49% of views come from drivers over 30 km from both ends.
- 448–652 of the drivers view at least one of our gigs in the week; 90–140 book at least one; the busiest
  book 9–11. Bookers' median `completedGigs` is 17–28, the roster's 8–9.
- Direct offers (all after the deadline warning, at 2.2× typical): 218 sent, 3 accepted, 66 declined, 149
  unread, although all but one went to a driver who had viewed one of our gigs earlier that day.
- Driver-days with two or more pickups of ours: 18–41 a world; a third of the consecutive pairs start within
  30 km of the previous delivery.

## Prices (set A)
Wins ÷ quotes and the median quote ÷ list, in two-hour blocks from 08:00:
```
dev-03  Mon  0/12@1.40  5/35@1.31  1/25@1.31  3/25@1.30  6/25@1.26     <- a low day; the tracker follows it down
        Tue 19/24@1.28 17/21@1.32 17/38@1.63  5/13@1.62 15/29@1.89     <- and starts the next morning too cheap
dev-04  Mon 15/19@1.45  5/23@1.61 11/22@1.56  9/22@1.68  9/29@1.69
        Tue  0/24@1.58  0/18@1.57  0/14@1.65  0/25@1.65  3/23@1.57     <- the freeze sits the day out
hold-10 Mon  0/13@1.36  4/17@1.30 12/55@1.29 11/46@1.23  6/20@1.24
        Tue 20/22@1.37 15/27@1.72 15/27@1.80  9/20@1.84  8/21@1.86
dev-11  Tue  0/13@1.49  5/24@1.38  2/25@1.30  3/13@1.27  5/11@1.25
        Wed  7/12@1.32 11/15@1.47  7/22@1.61  9/24@1.53  4/19@1.60
```
- Quote ÷ list of won and of lost quotes have nearly the same distribution in every world: one multiplier
  carries no lane or trust structure.
- D01's median quote ÷ list by weekday: dev-03 1.29, 1.59, 1.79, 2.24, 2.10; hold-10 1.27, 1.82, 2.39, 2.20,
  2.31. The cap is `price_mult_max` 1.8 × `dealer_adj_max` 1.3 = 2.34 (2.46 with the `same_day` markup).
- Margin per order at v0 by lane: capital → elsewhere €22–64, capital → capital €22–28, others volatile.

## What it suggests for the desk
See `IDEAS.md`: the ring gate (1), option steering (2), two clocks for the price (3), trust (4), the fee
floor (6), the yard budget (7), an earlier alarm than `deadline_close` (8).

## Verdict
research — no policy change. The leads to confirm first are the Hyvinkää ring (sweep S1) and the class table (R2).
