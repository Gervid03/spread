Idea #15 of experiments/IDEAS.md, "Late-order triage: a car that cannot be on time is a cost to cut, not a
rescue to pay for". Read point 9 of IDEAS.md and experiments/20261114-0130-fable-research-v2-results.md first.
Today `Desk.repost()` gives an expired gig (its car is already late) the steep schedule through `fees_for`,
and `steep()` climbs at night too. Implement in src/spread_lab/policy.py:
- `late_fee_open: float = 0.0` (0 = off, the champion's behaviour) and `late_fee_max: float = 1.3`. Keep a set
  `self.lost` of orders that can no longer be on time: an order whose gig expired, and an unstaffed order with
  `self.now > order["lastPickupAt"]`. While `late_fee_open` > 0, `fees_for` gives a lost order a schedule that
  opens at `late_fee_open` x the typical fee and climbs in daytime half-hour steps (reuse `rising` with its two
  ends as arguments) to `late_fee_max` at the next refund-tier boundary minus the drive: deadline + 24 h, then
  deadline + 2 business days. Refund tiers: 10% up to 2 h late, 25% up to 24 h, 50% up to two business days.
  In the world's last 36 hours the schedule goes to `steep_max`: an undelivered car costs twice its price.
  (The world ends on the second Wednesday at 22:00, minute 14,280; `rejoin` also gets `endsAt` in the snapshot.)
- `late_repost: bool = False`: in `tick()`, an order that has just become lost and still has an open, unbooked
  gig is withdrawn and posted again at once without stop windows (as `repost` does), instead of standing
  unbookable until `gig_expired` at the deadline. Do it once per order. `tick()` runs after every step in
  practice and after every event in the final, so do not assume a step size.
- `rejoin()`: rebuild `self.lost` from the snapshot (waiting orders, unstaffed, `lastPickupAt` in the past) and
  the `gig_expired` events of the history.
- Counters: `late_reposts`; fees paid on lost orders and on warned orders that were not lost
  (`fee_lost_cents`, `fee_lost_n`, `fee_warned_cents`, `fee_warned_n`, from `gig_booked.feeCents`); late orders
  by tier from `delivered.at` against the order's deadline (`late_le_2h`, `late_le_24h`, `late_more`).
Before any code, play one world with the champion and read these counters (add them first, they change no
behaviour): how much does the desk pay today on lost orders? Then smoke: `late_fee_open` 1.0 alone, then with
`late_repost`. Then dev. The on-time share should not move; report driver fees, late refunds and the tiers.
