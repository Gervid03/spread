The route network (idea 31, the user's design, Sat 14 Nov 09:30): build on the champion on main (v3), no merge needed,
compare with the champion as usual. Two other workers build idea 26 at the same time (`hitch-return-offer-on-v3`:
an offer to our own driver for a declined thin request; `hitch-pairs-on-v3`: two cars in one gig). This is a third
route to the same volume, and the best one wins. Read docs/GAME.md, idea 31 and idea 26 in experiments/IDEAS.md, and the
R11 table in `experiments/20261114-0635-gemini-snow.md` on `origin/exp/gemini-n14-06263-snow-and-hitch-research`.

Why: drivers are our constraint, not demand (thin-town quoting alone took drivers from the other orders,
`n14-05162`). A driver who has just delivered one of our cars is the cheapest driver there is for the next car near
them: no trip to the pickup, and if the next car goes towards their home, no ticket home either (the rules: the trip
home is the dear ticket, bought on the day). But the app notifies drivers only by their home, so the next car has to
reach them by a direct offer, and the handbook names this case: an offer "reaches a driver whom a notification does
not, for example a driver who finishes one of your gigs far from home". One offer can fail, so the design is
redundancy: when several of our drivers finish near a pickup, offer it to up to three of them at once (the rules allow
3 open offers a gig, 3 offers a driver a day). The app post stays up as well, so local drivers can take it too.

Implement in src/spread_lab/policy.py, every flag off by default (the noop must show +0.00 on every smoke seed):

(a) The position ledger (no behaviour change on its own). For every booked gig, from `gig_booked` (it carries
`driverId`) and the gig's stops with the map's road minutes: the driver, where they finish (the last delivery place),
when (start from the gig's planned pickup, or `pickupAt` after `driver_late`; add road minutes, plates 30, charging
40), and their home (`homePlaceId` in the driver list). Drop the entry on `gig_dropped`, `no_show`, `order_cancelled`.
Correct it on `delivered` and from the snapshot's `driverPositions`. Rebuild it in `rejoin()` from the snapshot's
gigs.

(b) `net_offer: bool = False`. Every few minutes in `tick()` (daytime only, 07:00–21:00), for each of our open,
unbooked gigs: the candidates are our drivers who finish within `net_km` (30.0, straight line) of its first pickup,
early enough to reach it inside its window and still deliver with `min_slack_min` to spare, and who passed the
audience (experienced, manual licence). Rank them: the one whose home is nearest the gig's last delivery first, then
the one finishing nearest the pickup. Offer the gig to the top `net_fanout` (3) at once, at `net_offer_mult` (0.80) ×
the gig's typical fee, or at `net_home_mult` (0.65) × when the gig's last delivery is within 30 km of that driver's
home. Send it `net_lead_min` (60) minutes before the driver's planned finish (they plan from where they will be), never
before 07:00 or after 21:00. A declined or expired offer moves to the next candidate. Respect 3 offers a driver a day
and 3 open a gig. The app schedule stays as it is: that is the patch when the offers fail.

(c) `net_quote: bool = False`, with `net_discount` (0.05) and `net_cap_day` (8). At quote time, a request is "on the
network" when one of our drivers finishes within `net_km` of its pickup between 3 hours before and 1 hour after the car
is ready, and can still deliver it with `min_slack_min` to spare. On-network requests that pass the gate are quoted at
the tracker's price × (1 − `net_discount`); on-network requests that fail the supply gate are quoted for their slow
options at the tracker's price, at most `net_cap_day` such wins a day. Neither moves the tracker. A won on-network
order is posted as usual and reaches (b) at once.

(d) `net_seed: float = 0.0` (the discount; 0 = off) with `seed_min` (6). From Monday 12:00, keep a count of requests
(any outcome) by pickup town. A request from a pickup with ≥ 100 drivers within 30 km whose delivery lies within 30
km of a town that has sent ≥ `seed_min` requests this week is quoted at the tracker's price × (1 − `net_seed`). Try
0.05. This wins more of the outbound cars that leave a driver where return work appears. It does not move the tracker.

Counters (stats): `net_offers`, `net_accepted`, `net_declined`, `net_expired`, each also for home-bound offers;
the accepted fee ÷ typical fee (sum and count); `net_quoted`, `net_won`, `net_won_thin`, `net_late`;
`seed_quoted`, `seed_won`, `seed_late`; driver-days with two or more of our gigs; candidates per offered gig
(how often 0, 1, 2, 3+).

Order of runs (this task may use up to 8 smoke runs and 3 dev runs): smoke (a)+(b) alone, with `net_home_mult` 0.65,
then 0.80 = `net_offer_mult` (does home-bound matter?), and `net_lead_min` 0 against 60 (timing). If fewer than one
offer in five is accepted, say why (timing, fee, the limits, or nobody reads them) before going on. Then (b)+(c),
then (b)+(c)+(d). Dev: the best two settings, then the best with `net_cap_day` 16. Every dev world must stay ≥ 92% on
time. Report the worst world first, then won orders a week, the offer acceptance rate (home-bound and not), and margin
against the champion. Your branch name stays `exp/gemini-<your slug>`.
