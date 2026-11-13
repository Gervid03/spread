# Ideas backlog

The lead (with Fable) owns this list: it picks, orders and rewrites the ideas, and agents take one each.
Mark an idea **taken** with your branch when you start, and link your experiment note when you finish.

Status: `open` · `taken (<branch>)` · `done → <note>` · `dropped (<why>)`

**This version: Fable's scouting pass, 13 Nov 23:30.** Nothing below is tested. Every number marked
*measured* comes from the reveals of seven finished worlds and is in
[`20261113-2330-fable-research-scouting.md`](20261113-2330-fable-research-scouting.md), with the scripts
that produced it (`experiments/scripts/scout_*.py`). Everything else is a guess to test. Gains in euros are
rough guesses per level-8 week, there to order the work, not to quote.

## What the reveals say (read this first)
1. **v0 declines the biggest pickup town.** Hyvinkää sends 173–219 of the ~1,035 requests a week (17–21%) and
   is the top delivery town. It has 5–22 drivers within 30 km, so `min_supply` 30 declines all of it. It is
   39 km from Vantaa, and the Helsinki–Espoo–Vantaa ring holds 327–444 drivers. In the three `min_supply` 6
   runs we have, Hyvinkää `next_day` and `within_3_days` orders were 1 late of 50, at a median fee of 1.0× the
   typical fee, and 58% of the drivers who booked Hyvinkää cars live in the ring. *measured*
2. **Lateness sits in a few classes.** At v0: capital `same_day` 10 late of 302, capital `next_day` 8 of 229,
   `within_3_days` 0 of 43, but `same_day` outside the capital 16 of 109, and drives of 500 km or more 14 of
   104. One 20-car bulk order (same yard, `same_day`) gave 5 of one world's 10 late orders. About a quarter
   of the late orders carried a note about delivery hours or a tighter deadline. *measured*
3. **The deadline warning is an obituary.** 30 of the 42 orders that got `deadline_close` ended late, and 30 of
   the 41 late orders had one. Direct offers after it: 218 sent, 3 accepted, 149 unread, although every one
   went to a driver who had viewed a gig of ours that day. *measured*
4. **We pay the opening fee, at once.** 55–81% of gigs are booked within 5 minutes of the post and 60% at
   exactly 1.0× the typical fee. Driver fees are 67% of revenue (€15.0k of €22.3k a week). We have never
   posted below the typical fee. `next_day` gigs that book after the post day cost 1.21–1.65× the typical
   fee, against 1.01–1.03× for those booked on the post day. *measured*
5. **The price tracker loses a day around every price war.** It either sits the low day out (dev-04 Tuesday:
   4 wins from 105 quotes) or follows it down and starts the next morning far too cheap (dev-03 Tuesday
   08–12: 36 wins from 45 quotes at 1.28–1.32× list, the same afternoon 1.6–1.9× still won 40%). The caps
   bind too: on hold-10, D01's median quote from Wednesday is 2.39× list, which is `price_mult_max` ×
   `dealer_adj_max`. *measured*
6. **One dealer is a third of the market.** D01 sends 282–372 requests a week, mostly from one yard. Trust
   (+1% per on-time order, up to 25) is therefore worth most at D01, and a late D01 order costs far more
   than its refund. *measured (the sizes), the rest from the rules*
7. **Volume has a ceiling per day in the capital.** At v0 the capital carries about 75 `same_day` orders a
   week at 3% late; in the `min_supply` 6 runs it carried 112–172 at 11–19% late. More volume has to come
   from slower options and other pools, not from more `same_day` in the same town. *measured*

**The principle for this round.** v0 buys its safety with two blunt levers, `min_supply` 30 and a 35% win
target, which tax every order to stop a few classes. Replace each blunt lever with a gate on the class that
is actually late, then give the tax back (lower `min_supply`, higher `price_target_win`) and measure again.
After any idea below that removes late orders, re-run `-s price_target_win=0.45` on top of it.

## Tier 0: sweeps that need no code (run these tonight)
Each is one command on smoke, then dev if it looks good. One short note per sweep.

| # | Status | Command | Why |
|---|---|---|---|
| S1 | `taken (exp/gemini-sweeps)` | `lab sweep -g supply_radius_km=30,40,55` | 55 km puts Hyvinkää (and Porvoo) inside the capital's supply. Crude form of idea 1. Watch the on-time share: this also wins Hyvinkää `same_day`. |
| S2 | `taken (exp/gemini-sweeps)` | `lab sweep -g price_mult_max=1.8,2.3 -g dealer_adj_max=1.3,1.6` | The caps bind on worlds with a dear competitor and high trust. |
| S3 | `taken (exp/gemini-sweeps)` | `lab sweep -g fee_open=0.85,0.9,1.0` | Most gigs book in minutes at 1.0: is the floor lower? Crude form of idea 6. Watch `deadline_close` and drops. |
| S4 | `taken (exp/gemini-sweeps)` | `lab sweep -g loss_streak_freeze=12,9999 -g price_lr=0.02,0.05` | Does following the price war down beat sitting it out? Crude form of idea 3. |
| S5 | `taken (exp/gemini-sweeps)` | `lab eval --seeds-from smoke -s offers_per_warning=0` | 3 offers accepted of 218: if nothing changes, the offers go, and the desk is simpler. |
| S6 | `taken (exp/gemini-sweeps)` | `lab sweep -g min_slack_min=120,180,240` | `same_day` long drives are late; more slack is the bluntest fix (idea 2 is the sharp one). |

## Tier 1: mechanisms, ordered by expected gain per hour of work

### 1. `taken (exp/gemini-ring)` The ring: gate on who can reach the car, not on who is notified
- **Mechanism.** The app notifies drivers within 30 km of the first pickup, but drivers browse further and
  book what pays them (rules: "a gig far away gets fewer views, unless its fee could pay them"). For a ring
  driver, Hyvinkää → capital even ends at home, so it costs less than the typical fee assumes.
- **Evidence.** Point 1 above. A third of all views come from drivers who live over 30 km from both ends.
- **Change.** `gate_radius_km` (default = `supply_radius_km`): the radius of the supply count used by the
  decline gate only. `far_options` (default `all`): with `slow`, a pickup that passes only on the wider ring
  is quoted `next_day` and `within_3_days` only. Count `won_ring` and its late orders in `stats`.
- **Measure.** dev, with `gate_radius_km` 45 and 55, `far_options` `slow` and `all`. Report won, late and
  margin for ring orders separately.
- **Risk.** Hyvinkää `same_day` was 9 late of 120 in the overloaded runs; start with `slow`.
- **Guess.** +50–70 orders at €20–30: **+€1.0–2.0k**.

### 2. `taken (exp/gemini-options)` Option steering: quote the speed we can staff
- **Mechanism.** We choose which options to quote. A `next_day` order gives drivers an evening to plan and a
  morning to travel; a `same_day` order needs a free driver within the hour.
- **Evidence.** Point 2. In the overloaded runs `same_day` was 24% late in towns with 30–200 drivers and 32%
  in thinner ones, `next_day` 0–16%. Late `same_day` long drives at v0: Vantaa → Oulu (602 km), Espoo →
  Joensuu (445 km, twice), Oulu → Lempäälä (497 km).
- **Change.** `same_day_min_supply` (default 0): quote `same_day` only where at least this many drivers are
  notified. `slack_per_drive` (default 0): required slack = `min_slack_min` + this × drive minutes.
  `long_drive_min` (default off): above it, quote only options whose deadline is on a later day than the
  ready day, so the driver can start in the morning.
- **Measure.** dev; then give the tax back: `-s price_target_win=0.45` and `-s min_supply=20` on top.
- **Guess.** Removes about a third of the late orders; worth **+€0.5–1.5k** once the blunt levers are loosened.

### 3. `open` Two clocks for the price: the week's level and today's shift
- **Mechanism.** The competitor's price is level × day factor × lane × noise. The level holds all week, the
  day factor is new every morning, and one day is a price war (−20%). One multiplier with one small step
  mixes them up.
- **Evidence.** Point 5. Monday also starts blind: the prior 1.35 against a level of 1.26–1.54.
- **Change.** `level` moves slowly; `shift` starts at 0 every morning (`morning_reset`, default off) and
  takes large steps for the day's first outcomes (`price_lr_day0` 0.15, falling as 1/√n to `price_lr`). At
  the day's end the level takes over a part of the shift, unless the shift is under `war_shift` (−0.12): a
  price-war day never moves the level. On a war day keep quoting at the shifted price wherever
  `min_margin_frac` still holds (dealers with trust do pay), instead of freezing. Outage: a region (town +
  80 km) that wins 8 quotes in a row gets its own upward shift for the day, up to +25%.
- **Measure.** dev. Add `stats` for wins by weekday and the detected war day. Compare the morning after.
- **Risk.** Faster steps overshoot; cap the shift at ±0.30.
- **Guess.** A recovered war day and its morning after: **+€0.8–1.5k**.

### 4. `open` Trust is capital: count it exactly, buy it on Monday, never gamble it
- **Mechanism.** Each on-time order raises what that dealer accepts by 1%, up to 25; a late order halves the
  count. The count is exact from our own ledger (a revenue line without a late refund).
- **Evidence.** Point 6. D01's winning quotes climb from 1.3× list on Monday to 2.2× by Thursday while the
  per-dealer tracker (`dealer_lr` 0.02, cap 1.30) follows with a lag.
- **Change.** (a) `trust_gain` (default 0): multiply the quote by 1 + `trust_gain` × count/100; with it, the
  per-dealer factor only has to follow the competitor. (b) `trust_invest` (default 0): a discount on safe
  classes (capital, short, no note) for the three dealers with the most requests so far, until their count
  is 25, Monday to Wednesday only; one count at D01 on Monday morning is worth about 1% of ~€9k of later
  revenue. (c) `trust_guard` (default off): for a dealer with a count of 13 or more, decline the late-prone
  classes of idea 2 instead of pricing them. Trust is worth nothing after Friday 18:00, so (b) and (c) fade.
- **Measure.** dev. `stats`: trust count of the top dealer at each day's end, mean price ÷ list by weekday.
- **Risk.** The competitor cuts its prices each morning for dealers where we "won most". R4 below measures
  that; until then keep the investing share of a dealer's requests under a half.
- **Guess.** **+€0.5–1.5k**.

### 5. `open` The twin ladder: let batches bracket the competitor
- **Mechanism.** About 45% of requests arrive in batches (same dealer, same yard, same minutes; 144–152
  `batchId`s a world, most of 2–4 cars). Quote the cars of a batch at different prices around the estimate:
  the dearest win and the cheapest loss bracket this dealer's price today in one step. A single quote tells
  only "above" or "below".
- **Change.** `ladder_spread` (default 0): batch members are quoted at the estimate × exp(±spread), evenly
  spread (try 0.05 and 0.08). When a batch both wins and loses, move the day's shift (idea 3) to the middle
  of the bracket. Works without idea 3 as a larger step of `mult`.
- **Measure.** smoke first: how many quotes until the multiplier settles on Monday and after the price war.
- **Guess.** Mostly speeds up idea 3; alone **+€0.2–0.5k**. The jury has probably not seen it.

### 6. `open` Find the fee floor: the same tracker on the drivers' side
- **Mechanism.** The typical fee is the cost of a typical driver from the pickup town, "not what the cheapest
  driver needs". With hundreds notified, the cheapest one needs less.
- **Evidence.** Point 4.
- **Change.** `fee_open_dense` (default = `fee_open`) for pickups with at least `dense_supply` (200) drivers
  notified, rising to 1.0× in `open_ramp_min` (45 for `same_day`, 120 otherwise), then the v0 schedule.
  Better: one opening multiple per town, learned as the price is: down a step when a gig books within 5
  minutes, up when it waits 30 daytime minutes, within 0.7–1.1. And `night_hold` (default off): a gig posted
  after 17:00 for a later day keeps its opening fee until 08:00 instead of climbing overnight.
- **Measure.** dev: booked fee ÷ typical fee, minutes to book, drops, `deadline_close`.
- **Risk.** Drivers learn booked ÷ first-viewed fee; a low start with a quick rise teaches them to wait, and
  a fee that only just pays is dropped more often. Compare a flat low fee with the ramp.
- **Guess.** −8% on two thirds of the fees: **+€0.6–1.0k**.

### 7. `open` Bulk orders: budget the yard, count the quotes in flight
- **Mechanism.** The backlog gate counts won orders. A bulk order's 10–40 requests are all quoted before any
  is won, so none sees the others. A world has 3–6 batches of 10 or more.
- **Evidence.** dev-04, v0's worst world (93.0%): 20 `same_day` cars from Lempäälä, 10 won, 5 late.
- **Change.** `yard_cap_ratio` (default 0 = off): per pickup town and deadline day, won-and-unstaffed orders
  plus quotes in flight × `price_target_win` may not exceed max(`backlog_min`, ratio × supply). Within a
  batch quote the safest cars first (slow option, short, towards a town with drivers) and decline the rest.
- **Measure.** dev; `stats`: declined by the cap, late orders from batches of 5 or more.
- **Guess.** Safety on exactly the world that came closest to 90%.

### 8. `open` An early staffing alarm instead of the deadline warning
- **Evidence.** Point 3. 75–92% of gigs are booked within an hour of the post.
- **Change.** `alarm_after_min` (default 0 = off): an order with no driver this many daytime minutes after
  its post (try 45 for `same_day`; 10:00 on the deadline day for the others) is treated as urgent now: the
  fee jumps to `alarm_fee` × typical (1.4) and then climbs. A second signal to try: fewer than 2 viewers
  in the first 15 minutes.
- **Measure.** dev: late orders among alarmed orders, fees paid, against the 71% late after `deadline_close`.
- **Risk.** Higher fees on orders that would have booked anyway; raises teach drivers to wait.

### 9. `open` Give drivers an earlier deadline than the dealer's
- **Mechanism.** A driver plans to reach each stop inside its window, and real drives vary around the road
  minutes. A plan that ends at 19:55 is a late car. A stop may carry its own, narrower window.
- **Evidence.** 11 of the 41 late orders never had a deadline warning: they had a driver and were late anyway.
- **Change.** `delivery_buffer_min` (default 0) and `buffer_per_drive` (default 0): the delivery stop's
  window ends that much before the deadline (try 45 + 0.1 × drive). When the gig expires, the repost uses the
  order's own window, as today.
- **Measure.** R3 first (how late are these orders: minutes or hours?). Then dev.
- **Risk.** A narrower window leaves fewer drivers who fit, and the gig expires earlier.

### 10. `open` The on-time share as a budget, and Friday as the repair day
- **Mechanism.** The minimum is a share: nine on-time orders pay for one late one. So a safe order has a value
  beyond its margin when the share is tight, and a late-prone order has a cost beyond its refund.
- **Why the old guard failed.** `guard_target` read the ledger, where lateness shows up a day late, and it
  could only close the gate. This one projects from classes and can also add safe orders.
- **Change.** Projected late = known late + 0.7 × warned-without-driver + Σ over open orders of their class's
  late rate (the table from R2). `budget_target` (default 0 = off): under it, discount the safest classes
  (capital and ring, `next_day` or slower) by up to `ballast_discount` and decline the worst classes. On
  Friday every `next_day` order is due on Monday 20:00 and Saturday has weekend drivers: `friday_ballast`
  wins safe Friday orders when the projection is under 93%.
- **Measure.** holdout-like worst cases matter here: report the worst world, not the mean.
- **Risk.** The capital has a daily ceiling (point 7): ballast has to be slow options.

### 11. `open` Notes: harvest the truth, then price out what we cannot read
- **Mechanism.** The reveal gives the truth of every *won* car's note, delivered or not.
- **Change.** (a) A research policy `policies/note_harvest.py`: quote 0.9× list on every request with a note,
  decline the rest, post nothing. One world gives ~400 labelled notes; ten give 4,000. Never promote it.
  (b) Score `notes.py` field by field on that set and fix it (delivery hours, "by tomorrow 17:00", weekday
  names, hours in words). A language model may write the rules offline; none runs in the final.
  (c) Use the reader when quoting: delivery hours and note deadlines shorten each option's slack, and
  `note_unsure` (default `quote`) = `decline` when a note has a time the reader cannot place.
- **Evidence.** Late at v0 with a timing note: "Nobody at the destination after 3pm", "perillä liike kiinni
  klo 15 jälkeen", "Open weekdays 9:00-14:30", "must be at destination by monday 13:00", "mottagaren har
  öppet 9 - 16", "haettava ennen klo 14". Failed visits cost €237 a week.
- **Guess.** A quarter of the late orders and most failed visits: **+€0.3–0.6k** and safety.

### 12. `open` Supply follows our cars: return offers, return-aware quotes, lead cars
- **Mechanism.** A driver who delivers our car far from home has to buy a ticket back. A car from there
  towards their home is nearly free for them, and the app does not tell them ("the app does not notify a
  driver where your gigs have taken them"); a direct offer does. We know who and where from our bookings.
- **Evidence.** 64–67% of requests of 60 km or more have a request on the reverse lane the same or next day.
  Only a third of our drivers' consecutive gigs start near the previous delivery. The capital sends 175–252
  requests a week to other towns, and 100–131 come back from them, mostly from towns we decline.
- **Change, in three steps; stop at the first that fails.** (a) `return_offer_mult` (default 0 = off): when
  one of our drivers will deliver within 30 km of an open gig's pickup in time, offer them that gig at this
  multiple of the typical fee (try 0.8) as they deliver. Measure the accepted share against 3 of 218.
  (b) Only if (a) is accepted at least one time in five: `return_gate` lets a thin-town request pass the
  supply gate when such a driver is on the way and the delivery is towards their home, with a small
  `return_discount` on the price to win it. (c) `lead_car` (default off): post a thin-town car as the second
  car of a gig whose first pickup is in a dense town, so the dense town's drivers are notified (multi-car
  gigs: at most 12 hours of driving). Try it on Hyvinkää first.
- **Risk.** Offers have been close to useless so far; that is why (a) is a cheap test before (b).

### Kept from the first list
- 13. `open` **Release a late driver.** On `driver_late`, release (free until they leave) when their
  `pickupAt` makes the car late and a fresh post can still be on time.
- 14. `open` **Flu day.** Distinct viewers per town by 10:00 against the same hour on earlier days; a fall of
  a quarter or more means the flu: that day raise `same_day_min_supply` and the win target's price.

## Research (no policy change; results feed the ideas above)
- R1. `open` **X-ray by fork** *(touches the instrument: agree it with the lead first)*. A fork has the same
  future draws. Fork a world at Monday 08:00 into six copies, quote every request at a different multiple of
  list in each (1.1 … 1.7), post nothing, play to 18:00: each request's outcomes across the copies bracket
  the price that dealer accepted. Check first that outcomes are monotone in price. It gives the acceptance
  curve, the lane factors that hold in every world (ten worlds = 10,000 brackets), the value of speed per
  option, and the price war and outage sizes. The same trick on the drivers' side: fork after a post and
  open at 0.6 … 1.0× in the copies to see the lowest fee that books within 30 minutes, by town and hour.
- R2. `open` **The class table.** Reveal every finished world in `runs/` (one request each) and tabulate late
  share, margin per order and booked fee ÷ typical fee by pickup class (capital, ring, 30–200, under 30) ×
  option × drive length × weekday. `scout_classes.py` is a start. Ideas 2 and 10 take their gates from it.
- R3. `open` **How late is late.** Minutes late per late order (reveal `deliveredAt` − deadline), split by
  whether a driver held it at the deadline warning. Sizes idea 9.
- R4. `open` **The competitor's morning reaction.** Fork at Monday 18:00 after winning 0%, 30%, 60% and 90% of
  D01's requests; quote a fixed ladder on Tuesday morning in each. Where does it start cutting?
- R5. `open` **The capital's daily ceiling.** From runs at different volumes: `same_day` orders per day in the
  capital against that day's late share. Gives idea 10 its capacity.

## For the jury (collect as you go)
Each idea above is one sentence, one reason and one paired number. The three most likely to be the story:
*we gate on who can reach the car, not on who is notified* (1); *trust is capital* (4); *the spread has two
trackers, one per side, and two clocks* (3 and 6). The failures count too: the ledger guard, and direct offers.
