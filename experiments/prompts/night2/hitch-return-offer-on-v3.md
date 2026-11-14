Idea 26, the return-offer form: build on the champion on main (v3), no merge needed, and compare with the champion
as usual. This is the day's biggest volume bet, so take care with the details. Read docs/GAME.md, then idea 26 and
12(a) in experiments/IDEAS.md, and the R11 table in `experiments/20261114-0635-gemini-snow.md` on
`origin/exp/gemini-n14-06263-snow-and-hitch-research`.

Why: the leaders win ~430 orders a week, we ~280, and drivers are our constraint, not demand (thin-town quoting
alone took drivers from the other orders, `n14-05162`). R11: 165.7 of our declined slow requests a week pick up
within 15 km of where one of our won orders delivers on the same or previous business day, inside 12 hours of driving.
That's 94 disjoint chains a week, ~30–38 extra wins at our win rate. Our gigs book within minutes, so a return car
rarely finds an unbooked partner gig. The handbook names the channel that works after booking: a direct offer
"reaches a driver whom a notification does not, for example a driver who finishes one of your gigs far from home",
and a driver who is working one of our gigs today does read offers.

Implement in src/spread_lab/policy.py, flags off by default (A noop must show +0.00 on every smoke seed):
- Track every booked gig's driver and the planned delivery minute and place of each of its cars (from `gig_booked`
  and the gig's stops and road minutes; rebuild in `rejoin()` from the snapshot's gigs).
- `return_offer_km: float = 0.0` (0 = off): a request that fails the supply gate is quoted for its slow options when a
  driver of ours delivers within this many km (straight line) of its pickup, before the pickup window closes, with
  time to reach it and still be on time with `min_slack_min` to spare. Try 15. Price: the tracker's price ×
  (1 + `return_markup` (0.0)). At most `return_cap_day` (8) such wins a day. These quotes don't move the tracker.
- On winning one: post its gig as usual, but at `return_fee_open` (0.75) × the typical fee (the driver is already
  there), and send that driver a direct offer of it at `return_offer_mult` (0.9) × the typical fee, timed for when
  they deliver (an offer lasts 10 minutes, a driver gets at most 3 a day, a gig at most 3 open: respect the limits
  that `offers_per_warning` code already knows). If the offer is declined or expires, the gig stays on the board and
  climbs as usual.
- Counters: `ret_quoted`, `ret_won`, `ret_offered`, `ret_accepted`, `ret_late`, `ret_margin_cents`, and how often the
  outbound driver had already finished and gone home.
Smoke: `return_offer_km` 15 with the cap 4, then 8; once with `return_fee_open` 1.0. Dev: the best two. The hard rule
is that every dev world stays ≥ 92% on time. Report the worst world first, then won orders a week and margin against
the champion. If offers are rarely accepted, say why: timing, fee, or the limits.
