# Ideas backlog

The lead (with Fable) owns this list: it picks, orders and rewrites the ideas, and agents take one each.
Mark an idea **taken** with your branch when you start, and link your experiment note when you finish.
The first list below is Claude's from setting up the lab (13 Nov, 22:00); it is a starting point, not a plan.

Status: `open` · `taken (<branch>)` · `done → <note>` · `dropped (<why>)`

## Staying ranked (the hard constraint)
1. `open` **On-time guard.** The first baseline missed 90% on 3 of 5 worlds while winning ~390 orders. Track
   the risk live (orders past their deadline warning without a driver, late deliveries so far, unstaffed
   backlog) and throttle intake (raise the decline bar or the price) when the projected on-time share
   falls under ~94%. The final is one world: the guard matters more than any margin idea.
2. `open` **Flu and bulk-order days.** A sudden fall in views/bookings (flu) or a burst of 30–40 requests
   from one yard (bulk order, often one `batchId`) should make the desk stand down rather than overcommit.
3. `open` **Release a late driver.** On `driver_late`, release (free until they leave) when their
   `pickupAt` makes the car late and a fresh post can still be on time.

## Pricing
4. `open` **Expected-profit quoting.** Model P(win | price/list, dealer, lane, option, hour) from our own
   outcomes and pick the price that maximises (price − expected cost) × P(win) − risk, instead of a
   target win rate.
5. `open` **Lane priors across worlds.** Part of each lane's competitor factor is the same in every world.
   Learn it offline from many practice worlds (quotes and outcomes are in each reveal) and start each
   world from those priors instead of one global multiplier.
6. `open` **Price war and outage.** Detect the price-war day (a losing streak everywhere from 08:00) and sit
   it out (the baseline only freezes the multiplier). Detect the outage (one region suddenly wins
   everything) and charge more there that day: dealers' backup costs ~30% more than the competitor.
7. `open` **Option strategy.** Which options to quote, and the same_day markup: slower options are cheaper
   to staff (more time, more drivers, chains), and the dealer weighs each price against the value of speed.
8. `open` **Dealer trust (level 8).** Track each dealer's on-time count from the ledger and price up where
   trust is high; avoid risky orders from dealers whose trust a late car would halve.

## Fees and staffing
9. `open` **Fee schedule shape.** Drivers learn booked fee ÷ first viewed fee and time-to-book; a rising
   schedule teaches them to wait. Compare flat fees, a single late jump, and opening levels set per region.
10. `open` **Learn the fee per region during the week.** Use our own bookings (fee ÷ typical fee, minutes to
    book, by pickup region) to set opening fees and the expected cost used in selection.
11. `open` **Chains and multi-car gigs.** Pair a delivery with a return leg towards the driver's area, or two
    cars from one yard, in one gig (≤ 12 h of driving): one driver's trips for two cars.
12. `open` **Smarter direct offers.** The baseline's offers mostly go unread (183 sent → 3 accepted on one
    world). Offer to drivers who are *working now* (recent views) or who finish one of our gigs near the
    pickup (`driverPositions` in the snapshot), earlier than the deadline warning.
13. `open` **Supply estimate.** Weight drivers by distance and licence/experience fit, and update who works
    today from views and bookings, instead of a static count within 30 km of the pickup.

## Notes
14. `open` **Note reader, measured.** Score `notes.py` against the reveal's truth (`readyAt`, hours,
    `manualGearbox`, `needsPlates`, `summerTyres`, `noteDeadline`) on a few worlds; fix the misses
    (relative days: "huomenna", "i morgon", weekday names 2–6 days ahead, tighter deadlines). A cheap LLM
    (Gemini) for the hard notes is possible, but the final allows 4.5 s per request and must be deterministic
    in practice (cache by note text).

## Research (no policy change; results feed the ideas above)
15. `open` Acceptance curve: from reveals, P(win) against price ÷ list by option, dealer and hour.
16. `open` What makes an order late: features of won orders against lateness (pickup supply, hour, option,
    distance, notes), to sharpen selection.
