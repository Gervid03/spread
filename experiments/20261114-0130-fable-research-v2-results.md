# research-v2-results: what v2's 32 result lines and a second reading of the rules say

- **Agent / branch / commit:** Fable (lead's scout) · ccr-de9434eb-7qs9p6
- **Date:** 2026-11-14 01:30
- **Idea from:** own (grounding for round 3 of `IDEAS.md`)

## Question
Wave 2 (the two price clocks, trust, the fee floor, the yard budget) brought four results inside the noise.
Where is the next thousand euros, and what threatens the 90%? **No world was played and none revealed.** I
read the champion's 32 committed result lines (`champion/results/`), `policy.py` against `RULES.md` and
`HANDBOOK.md` line by line, and the four wave-2 notes on their branches.

Script: `uv run python experiments/scripts/scout_results.py` (any `results.jsonl` works as an argument).
Everything below marked *between worlds* is a correlation over 32 worlds: a lead, not a result.

## v2 in one table (mean per world, 32 worlds)
| | |
|---|---|
| Revenue / driver fees / margin | €28,282 / €18,305 (65%) / €9,202 |
| Late refunds / failed visits / waiting / release fees | €459 / €216 / €45 / €44 |
| Won orders / late orders | 232 / 8.2 |
| Deadline warnings / expired gigs / drops / bookings | 13.2 / 8.7 / 30.7 / 270.6 |
| Quotes: normal / floor / decline | 480 / 205 / 350 |
| Won by option: `same_day` / `next_day` / `within_3_days` | 66 / 155 / 13 |
| Ring orders: won / late / margin | 56 / 2.3 / €2,212 |
| Failed visits in all 32 worlds | `not_ready` 118, `no_plates` 38, `closed` 19, `licence` 0 |

## What the result lines say
1. **Margin follows volume, and volume does not cost on-time share between worlds.** Margin against won
   orders: r = 0.79. On-time share against won orders: r = −0.11. Worlds differ in how many orders they can
   carry, and the desk's gates and its 35% target are the same in all of them. *between worlds*
2. **A late order is an expired gig, and an expired gig is expensive.** Late orders against deadline
   warnings: r = 0.90; against expired gigs: 0.87; expired gigs (8.7 a world) are about as many as late
   orders (8.2). Driver fee per order, least squares on revenue per order, expired gigs, other warned
   orders and drops: **€132 more fee per expired gig, about €1,150 a world**; a warned order that did not
   expire adds €22, a drop €18. *between worlds*
3. **The mechanism behind 2 is in the code.** `repost()` gives an expired gig (a car that is already late)
   the steep schedule: 1.8× the typical fee at once, 2.8× two hours later, and `steep()` also climbs at
   night. A gig that expires at 20:00 stands at 2.8× from 22:00 and the first morning driver takes it. Late
   tiers are 10% (≤ 2 h), 25% (≤ 24 h), 50% (≤ 2 business days): the fee buys nothing that the refund
   table pays for. And between `lastPickupAt` and the end of its window an open gig cannot be booked at
   all (rules: "a car with a 7-hour drive whose delivery window ends at 20:00 gets no driver after 13:00"),
   but the desk waits for `gig_expired` before it posts the car again.
4. **Drops are the second face of the worst worlds.** Late against drops: r = 0.69. hold-14 (93.3%) has 72
   drops on 350 bookings and dev-07 (94.4%) has 58; the median world has 30 and the next highest 42. A
   spike like that needs a cause that hits many drivers at once. The flu comes every week, so snow is the
   candidate ("some drivers stay at home and drop bookings that must start that day"), and the desk
   ignores `forecast` events. `not_ready` visits do not separate the two worlds (8 and 7 against a median
   of 4; three other worlds have 7). Drops also grew with the lower opening fee: 9% of orders had a drop
   at v0 (scouting), v2 has 13 drops per 100 orders; the rules say a fee that only just pays is dropped
   more. *the snow link is a guess: R7*
5. **The worst world is the best one.** hold-10: 91.8% on time and €14,067, the highest margin. 293 orders
   (second most), €179 revenue per order (most, by far), 46 warnings, 25 expired gigs, €2,252 refunds. It
   won 40% of its quotes against the 35% target. The 90% is at risk where the week is rich, not where it
   is poor.
6. **Floor quotes win about as often as normal ones.** Wins ÷ (normal + floor quotes) = 0.339. If normal
   quotes win their 35%, the 205 floor quotes a world win about 31%, at a price *above* the tracker's. A
   floor binds where the typical fee is high against the list price. So where the lane is hard for
   drivers, dealers accept more: the typical fee carries part of the competitor's lane factor, as the
   handbook says it should. Floor outcomes do not teach the tracker; hold-08 has 472 floor quotes and 349
   normal ones. *indirect: R8 fits it*
7. **One rule shapes seven worlds.** `same_day_min_supply` 100 strips `same_day` from 170–313 requests in
   dev-02, dev-10, dev-15, hold-08, hold-09, hold-13 and hold-15 (elsewhere 0–130). Five of them also have
   fewer than 13 ring orders (elsewhere 28–126): the busy yard's town kept 30–99 drivers, so it is neither
   ring nor capital. Their mean margin is €8,461 against €9,202.
8. **`within_3_days` is 5% of the orders** (13 of 232) although 16% of requests offer it and none of 43 was
   late at v0. Every option is priced at the same multiple of its list price.

## What a second reading of the rules says (not used by the desk)
- **The fee clock ticks when nobody can act.** `rising()` spreads the climb to 1.6× evenly over the daytime
  half-hours from the post to the warning. A `next_day` gig posted at 15:00 stands at about 1.2× at 07:00 the
  next morning (half of its daytime steps are that first evening); a Friday gig due on Monday stands at 1.48× on Monday at 07:00, because Saturday and Sunday
  tick. Scouting measured it without naming it: `next_day` gigs booked after the post day cost 1.21–1.65×.
- **Slack is measured to 20:00, not to closing time.** `price()` uses deadline − ready − drive. The world's
  `lastPickupAt` counts the sites' stated opening hours, and a car left at a closed site is delivered when
  it next opens (rule 4). Requests carry `hours` for both sites. *How early sites close is unmeasured.*
- **`order_won` already tells us that a note moved the ready day** (its deadline is later than the
  option's). The desk uses this after the first failed visit (`retry_from`), not before it.
- **Premium cars may only go to experienced drivers** (rating ≥ 4.8, ≥ 50 gigs; the roster's median is 8–9
  gigs). The supply gates count every driver.
- **Friday's slow options are due on the last Monday**: Saturday's weekend drivers and a whole Monday
  without new requests. Trust and the competitor's reaction are worth nothing after Friday 18:00.
- **Multi-car gigs are notified by their first pickup**, and a second car costs a driver "only the extra
  time and tickets". The desk posts them for trade-ins only.
- **The typical fee is the cost of a driver from the pickup town** who must buy a ticket home; "a driver
  who lives near the delivery place ... needs much less". The gates look at the pickup only.

## What it suggests for the desk
Round 3 of `IDEAS.md`: late-order triage (15), the fee clock (16), slack by opening hours (17), a price
that knows the cost (18), the thermostat (19), a same-day quota (20), Friday and the surplus (21), snow
(22), the free signals (23), and the research cuts R6–R14 that size them.

## Verdict
research — no policy change. Confirm point 2 first (one reveal: fees paid on orders whose gig expired).
