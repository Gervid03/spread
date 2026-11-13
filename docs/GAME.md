# The game, condensed

Our own summary of Spread for agents who need the facts fast. The organisers' documents are the
authority (`uv run lab docs` downloads them to `docs/kit/`; where they differ, `RULES.md` wins).

## What we are scored on
- **One simulated week** ("world"): dealers send price requests Mon 08:00–Fri 18:00 (almost all 09–18),
  about **1,000–1,100 requests at level 8**, 99% one car, ~1.5% trade-ins (two legs, one price).
- **Score = gross margin**: prices of delivered orders − driver fees − late refunds − 2× price for
  undelivered cars − failed-visit charges − release fees − waiting − fines.
- **Ranked only if ≥ 90% of won orders arrive on time** (cancelled orders don't count; undelivered =
  late). A team with no order is unranked.
- **The final:** Sun 15 Nov 08:00, one secret **level-8** world, the same for every team, real time
  (~34 min, a weekday hour = 18 s, a request's 15 world minutes = 4.5 s). The **10 ranked teams with the
  highest margin** present; then a jury judges elegance, clarity, creativity, robustness — and wants each
  big idea's *measured* effect on margin and on-time share. **So: be in the top 10 by margin without
  ever risking the 90%.** Test finals: Sat 14:00 and 20:00 (~19 min, a random level-8 week from Thursday).

## What the jury wants (from /judging)
- **Elegant** (a simple idea that does much of the work), **clear** (we can follow how it decides),
  **creative** (an idea they didn't expect), **robust** (does well on unseen weeks, shown over many weeks;
  survives a restart, a slow network and a surprise).
- 5–10 slides. For each big idea: **the idea** (what it does, in which cases), **why** (what we saw that made
  us try it), **the effect** (margin and on-time share *with and without it, on the same weeks*). Also our
  final result, our best ranking round, what did not work, and what would break the system. Use the
  challenge's words (dealer, request, gig, fee, typical fee, deadline). Their example of a good number:
  "€12,551 a week, against −€67,177 for the starter, on the same 20 weeks at level 8".
- Submit on Junction by Sun 10:00: the **submission hash** (team page), a link to the code, the slides.
- The server is in **Stockholm**; they suggest running the final from a cloud machine near it. The final
  is set at 07:30 Sun, when registration (team creation) closes; our team "Swarm Dispatch" exists.
- Ranking rounds open Sat 00:00, 09:00, 12:00, 15:00, 18:00, 21:00 and Sun 00:00, 03:00, 06:00. They don't
  count for the final, but the jury asks for our best round.

## Level 8 (the final's level)
- **Driver shortage:** 26–40% of a normal world's drivers, and each town keeps its own random share (some
  keep most, some lose nearly all). `GET /drivers` (the roster) shows every driver's home town, rating,
  licence, completed gigs and drops — but not who works on a given day.
- **Competitor:** price = list × lane factor × day factor × world level (**1.26–1.54 at level 8**) ×
  noise. Part of the lane factor is the same in every world (harder lanes: little return work, few
  drivers near the delivery). It adapts each morning per dealer: where we won most, it cuts its prices
  for that dealer; where we won few, it raises them. We never see its prices, only win/lose.
- **Price war:** one working day without an outage, 08:00–18:00, the competitor is 20% cheaper everywhere.
- **Outage:** one working day, 08:00–18:00, the competitor is down in one region (a town + 80 km);
  dealers there use a backup ~30% dearer than the competitor.
- **Flu** (30% of drivers stay home for a day) and a **bulk order** (30–40 cars from one yard) every week.
- **Dealer trust:** each dealer counts our on-time orders (max 25) and accepts prices +1% per count; a
  late order halves that dealer's count.
- **Satisfaction:** late/undelivered cars make a dealer accept only lower prices; on-time ones win a
  little back; *not quoting* a request costs a little; a losing quote costs nothing. **Decline = quote far
  above list**, never silence.

## Requests and options
- Options: `same_day` (deadline 20:00 on the ready day; only if the request comes by 15:00 and the drive
  fits 2 h before), `next_day` (20:00 next business day; Fri → Mon), `within_3_days` (20:00, third
  business day after ready, at most the last Monday). Measured on one world: same_day offered on 71%,
  next_day 91%, within_3_days 16%; **list price next_day ≈ 0.93 × same_day, within_3_days ≈ 0.86 ×**.
- **Typical fee** (`referenceFeeCents`) ≈ what a driver is usually paid in a *normal* week; median **0.9 ×
  the list price** (5%–95%: 0.59–1.18). At levels 7–8 a gig at the typical fee often finds nobody.
- Quotes must arrive before `respondBy` (arrival + 15 min). The dealer decides at `respondBy` on our last
  quote; when we quote several options it weighs each price against the value of that option's speed.
- **Notes** (41% of requests; fi/sv/en) can move the ready time, pickup/delivery hours, a tighter deadline,
  manual gearbox, missing plates, summer tyres, payment-before-handover. The world obeys the note whether
  we read it or not. The reveal shows what each won order's note really meant.

## Drivers and gigs
- A gig: ordered stops, an audience (experienced = rating ≥ 4.8 and ≥ 50 gigs; manual licence), and a fee
  schedule of 1–48 non-decreasing steps. Multi-car gigs ≤ 12 h of driving (road minutes of the map).
- Drivers are notified of gigs whose first pickup is within **30 km (straight line) of their home**; no
  notifications 23:00–07:00; a raise doesn't notify. A driver books when fee − their cost beats their other
  options and what they expect from waiting. **Drivers learn our habits**: booked fee ÷ first viewed fee and
  time-to-book, as a fading mean per driver, so always raising teaches them to wait.
- Drops get likelier the longer a booking is held, and when the fee only just pays. A dropper rebooks only
  for more. `deadline_close` arrives 3 h before `lastPickupAt` if no driver holds the order.
- Direct offers: 10 min, ≤ 3 per driver per day, ≤ 3 open per gig; a driver who doesn't work today rarely
  reads them (our first baseline: 183 offers → 3 accepted, 134 unread).
- Handling rules: premium car → experienced driver (else €150 fine); EV < 30% on a route > 200 km →
  charging stop (else 90 min late + €100); deliveries only in opening hours; failed visit = half the car's
  fee share, ≥ €25. Lateness refunds: ≤ 2 h 10%, ≤ 24 h 25%, ≤ 2 business days 50%, more 100%.

## Practice mechanics that shape our lab
- Practice worlds are **deterministic** (same seed, level, actions at the same minutes → same week to the
  cent) and stand still until `advance`. `fork` copies a world at a minute (same future draws).
- **8 unended practice worlds per team**, shared by everyone on the key. The practice request budget is
  shared by all teams (~10,000/s split equally, ≤ 1,000/s each; 20/s while a final or test final runs).
- From Espoo the server is ~50 ms away, so a world costs ~25–60 s of wall time at ~650–700 requests.
- **Ranking rounds:** five secret worlds per level per round, played once each, public. Not forkable,
  not revealable. House best (Bahn's own system) plays every round: on level 8 it made €6.4k–16.4k a week
  winning 200–465 orders at 90–98% on time (round "Friday 20:01").
