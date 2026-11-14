## Where you start: `tas-fees`, the fee oracle (every car at the lowest fee a driver would have taken)
Branch `exp/gemini-tas-fees`. World: **dev-12** first. Read `~/.spread-lab/tas/STATUS.md` (from `tas-price`) before
your first fork-heavy run; until it is there, do step 1 and build on the toy world. The steps are a first path, and
you have a free hand (see above).

**Why.** Driver fees are the biggest line: €20.1k of €31.3k revenue on dev-12 (64%), €19.1k a week on the dev worlds.
The desk opens at 0.85 × the typical fee and climbs to 1.6 × by the deadline warning. Drivers who have seen our fees
rise wait for the rise. The typical fee "is not the least fee that a driver takes": a driver who lives near the
delivery, or stands near the pickup after another gig, needs much less. A fork can read that price.

**1. The fee bill as it is (one world, no forks).** Play the champion's week on dev-12 through `Tas` and keep the
events (a small script under `experiments/scripts/`). One row per booked gig: fee ÷ typical fee, minutes from post to
booking, the first fee a driver viewed, views before the booking, drops, whether it booked after the warning. By class
(pickup supply hub/mid/thin × drive short/mid/long), by hour of posting, by lead time to the last pickup. Where does
the bill come from: the opening fee, the climb, the warnings, the late cars?

**2. The oracle.** At the minute the desk would post a gig: on forks, post it at one flat fee `f` and play on. Is it
booked? By whom, when? Does the booking hold to the pickup? Bisect `f`: `f*` is the lowest fee that moves the car on
time. Settle these on Monday's first twenty orders before you spend a week of forks:
- **The horizon.** How far must a fork play to know? To the booking is cheap; to the pickup shows the drops ("a fee
  that only just pays gets more drops"). A car booked two hours later is still on time: what does waiting buy?
- **App or offer.** A direct offer is taken "when the fee pays for the gig and what else their day is worth", with no
  waiting game. On a fork you can offer the gig to any driver at any fee and see who says yes: three open offers a gig,
  three a day a driver, inside each fork, but forks are free. Scan the drivers near the pickup and the drivers who end
  one of our gigs near it; the main line then sends only the offer that will be taken.
- **Order.** A driver who takes this car is gone for the next. Go in the main line's order and probe at each posting.
- **What drivers learn.** The booked fee ÷ the first viewed fee, and the minutes to the booking. Flat fees that book
  at once teach them not to wait: is Thursday's `f*` lower than Monday's for the same kind of car?
- **When to post.** Nobody is notified 23:00–07:00, a driver hears of an order once, and most views come in the first
  minutes. Is 07:00 better than 22:30 the evening before for a car won late?

Build it on `on_fork` (in `scripts/tas.py`) as a Desk subclass, `src/spread_lab/policies/tas_fees.py`, that asks the
oracle where the desk calls `fees_for` (give the desk a reference to the game). Staffing is not a hook: the desk
matches the world's answers to its own actions.

**3. Layer 3: the champion's orders, staffed by the oracle.** Fix the quotes with the champion's book
(`book-won.json` from `tas.py limits`, or the desk's own quotes) so that only staffing differs. Unlike perfect prices
this is a new week, not the same week: other drivers are busy, cars arrive at other times, trust moves. Measure it end
to end: the fee bill, the late cars, the margin. Hold the on-time share at or above the champion's.

**4. Stack.** The same week with `tas-price`'s limits (`--apply`): layers 1 and 3 together. Then, when `tas-routes`
has tours, the oracle prices a tour as it prices a car.

**5. The rule for Sunday.** `f*` ÷ typical fee by class, hour and lead time: where does opening at 0.85 overpay (it
booked at once: would 0.6 have?), and where does it underpay and then climb to 1.6 (open at `f*` at once and teach
nobody to wait)? An opening-fee table by class needs no fork. And how much cheaper is the driver who has just
delivered one of our cars nearby (idea 31, the route network)?

**And your own ideas.** Drivers are the game's richest hidden model, and a fork shows any of it you ask for. Some
questions to start you off; yours will be better. Does a fee schedule whose first step lies in the future show its
first fee to early viewers, and what do they learn from it? Does an `experienced` or `manualLicence` audience change
who looks? Can a gig be posted with a window that picks the driver you want? Is a release (25% of the fee more than
24 hours ahead) ever cheaper than keeping a driver who will be late? What do withdrawn and reposted gigs do to "a
driver hears of an order once"? What is a driver's second gig of the day really worth to them? Test what you think
of, on forks, and write down what you find.
