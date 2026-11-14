# Ideas backlog

The lead (with Fable) owns this list: it picks, orders and rewrites the ideas, and agents take one each.
Mark an idea **taken** with your branch when you start, and link your experiment note when you finish.

Status: `open` · `taken (<branch>)` · `done → <note>` · `dropped (<why>)`

**This version: Fable's round 3, 14 Nov 01:30.** Nothing new below is tested. Numbers marked *measured*
come from reveals of seven worlds at v0 ([scouting note](20261113-2330-fable-research-scouting.md)) or from
the champion's 32 result lines at v2 ([results note](20261114-0130-fable-research-v2-results.md), script
`experiments/scripts/scout_results.py`); the second kind are correlations *between worlds* and are leads.
Everything else is a guess to test. Gains in euros are rough guesses per level-8 week, there to order the
work. Ideas keep their numbers for good: 1–14 are round 1, 15–30 round 3.

## Night directive from the cloud lead (Sat 14 Nov, 06:55 Helsinki): read this before planning
For the night lead and every worker. It overrides the order of everything below until the night ends.

**1. The base is the champion on main: v3 = D, promoted 06:12 UTC by `scripts/promote.sh`** from
`exp/gemini-n14-03501-extring-full-neutral-and-leadcar` (the GTN base + backlog weights + extended ring + lead car +
`dealer_lr` 0.01). It made €10,529 on dev and €11,281 on holdout, Δ +1,539 (t 5.8) and +1,866 against v2, worst world
94.4% on both (`experiments/PROMOTIONS.md`; the validation note is on `exp/gemini-n14-05161-validate-top`). New
workers build on main and compare with the champion as usual: no merge, no `--vs`.

Workers already running on A (`exp/gemini-n14-03324-…`, flags in the note of that branch) finish as they are. Their Δ
against A stays informative, and their mechanisms are flags, so a winner is ported onto v3 by merging its branch and
re-measuring against the champion. A's own fee and drop flags (`hub_multiday_fee_open` 0.80, `thin_sameday_fee_open`
0.90, `drop_urgent_margin_min` 180) are not in v3. The v8 stack (A + D's flags) made €10,585, inside the noise, so
porting them needs a re-test on v3, not an assumption.

**2. Stacking tonight's mechanisms has stopped paying.** A, 03111, 03501, 03503, 03504 and the v7 stacks all
make €10.4–10.6k on dev, within one SE of each other, so no more stacking workers. The next gain is structural.

**2b. The gap that matters is volume.** On the public level-8 board ("Saturday 00:00", 151 teams, 63 ranked) we
are 35th with €54.2k for 5 worlds; the top 10 need ~€75.5k, and House best has €71.8k. The leaders win 410–460
orders a week at 96–98% on time, and their margin per order (~€40) is the same as ours. We win ~270. So the next
€4–5k a week is volume. The margin x-ray (`origin/exp/gemini-n14-01392-margin-xray-v2`) shows where it is: the thin
class (under 30 drivers within 55 km) is 287 requests a week, all declined, and same_day from mid towns and the
ring is all declined too. Ideas that open these classes safely (25, 24, 20, 21, 26) come before price and fee polish.
The handbook (`/kit/HANDBOOK.md`, "Dealers compare prices") names the other route: **"At levels 7 and 8 the list
price wins most requests"** (the competitor is 26–54% above list), and a request is good when it is cheap for us to
staff: it goes towards towns where drivers live, it pairs with an order we have (a return leg, a second car from the
same yard), or it starts in a busy area at a busy hour. One win target for every request wins the dear lanes and
loses the cheap ones. So pricing by staffing cost (idea 18; 02461's lane tilt was a first cut) and chains (26) are
volume ideas too: they win more of the cars we can staff cheaply.

**3. Fable's round 3 (ideas 15–30 below) is untested.** It was written at 01:30, before the night began, and
never reached the queue. It gets the worker slots, in this order: 25 + 24 (in `02-thin-volume`), 15 triage, 19 thermostat, 18 price by cost, 20 quota,
21 (a)+(b), 26 hitch (R11 first), 16 fee clock, 17 hours, 23 signals, then 22 (after R7). The briefs are in `experiments/prompts/gemini-<name>.md`. They were written for v2, so adapt each to A
in the worker prompt (merge A, A's flags, A's runs). Research briefs (R6–R14) cost almost no practice slots
(reveals are one request each), so one research worker can run beside the others at any time.

**4. Already done tonight. Don't repeat it** (the numbers are in the night ledger, `origin/night/20261114`):
3 two clocks (reject) · 4 trust (`trust_invest` 0.05, in A) · 5 ladder (reject) · 8 + 9 alarm and buffer (03111, adopt
candidate) · 10 budget (02464, 03503, small) · 11 notes v2 (in A) · 12 return and lead car (03112, 03501, small) ·
13 release (nothing) · 14 flu (nothing) · S7 opening fee 0.70–0.80 (worse) · S9 `fee_warn` 1.40–1.50 (+€200–450 on
v2, nothing on the stacks) · S10 same-day markup (worse) · S11 margin floor (worse) · S12 `dealer_lr` (0.01 best) ·
S13 gate radius (worse) · S14 win target 0.40 with `min_supply` 22 (in A). Not done yet: **S16 (`step_min=3`, the
final's live parity)** and S17. S16 is in `01-validate-top`.

**5. Sweeps are useful again, on v3's own flags.** `01-validate-top` reset the swarm host's root checkout to main
(34e7063) at 06:16 UTC, so the sweep track, the ranking rounds and INPUT.md's paired deltas now run on v3.
(INPUT.md's line "Champion v2 on dev: 8,990" is a stale hard-coded label in this night's copy of night_status.py, fixed
on main. The deltas under it are against v3.) Up to 6 sweep lines a tick, on v3's flags, with
`--seeds-from dev`. For a candidate final champion, the validation note's lesson holds: v7 was the best on dev and
went unranked on a fresh world (night-15, 89.3%), so measure the tail on fresh seeds, not the dev mean.

**6. The cloud lead's five prompts were queued at the 05:11 UTC tick** (`n14-05161-validate-top`, then thin-volume,
triage, thermostat and research-volume), and they now sit in `experiments/prompts/night2/` as a record. Don't queue
them again. Write your own prompts as usual. A brief for idea 16, already adapted to A, is in
`experiments/prompts/night2/feeclock-on-a.md`: copy it into `night-queue/` when a slot frees.
**Copy `experiments/prompts/night2/capacity-steps.md` into `night-queue/` at your next tick.** It measures whether
14-minute steps and event-driven evenings make practice worlds 20–40% cheaper without changing what they measure.
Practice slots are the lab's bottleneck, so this is the cheapest capacity there is.

**7. Promotion.** `01-validate-top` runs A, 03111, 03501 and the best v7 stack on holdout plus 32 fresh worlds,
checks a restart and `step_min=3`, and promotes the winner through `scripts/promote.sh` (gated against the
champion on dev, holdout and a restart). Nobody else touches `champion/` or `main`. To promote a later winner,
write a prompt that runs `bash scripts/promote.sh <branch> <flags>` (see `01-validate-top`, step 3).

## Where we are
| Version | What it added | Dev mean | Holdout mean | Worst world |
|---|---|---|---|---|
| v0 | `min_supply` 30, win target 35% | €6,447 | €6,837 | 93.0% |
| v1 | the ring (idea 1) and option steering (idea 2) | €7,926 | €7,942 | 92.7% |
| **v2** | opening fee 0.85×, tracker step 0.05, no offers, slack 180 (sweeps S1–S6) | **€8,990** | **€9,414** | **91.8%** (hold-10) |

Wave 2, each against v1 on dev, none merged: two price clocks +€46 ± 204 · fee floor in dense towns with a
night hold +€104 ± 196 · trust: investing +€215 ± 157, a trust gain on the price −€285 ± 117 · yard budget
−€98 ± 220 (safer on the bulk world). **Lesson: with 16 seeds one standard error is €200–300, so an idea
worth €300 is invisible** (see "For the lead" at the end), and tracker tuning is not where the money is.

## What we know (read this first)
**From seven reveals at v0** *(measured)*
1. Hyvinkää sends 17–21% of all requests and has 5–22 drivers within 30 km; the capital ring, 39 km away,
   holds 327–444. *(Now served by the ring, slow options only: 56 orders a world, 4% late, €2,212.)*
2. Lateness sits in classes: `same_day` outside the capital 15%, drives of 500 km or more 13.5%,
   `within_3_days` 0 of 43. A quarter of the late orders had a note about hours or a tighter deadline.
3. The deadline warning is an obituary: 30 of 42 warned orders ended late.
4. Most gigs book within 5 minutes of the post at the opening fee. `next_day` gigs booked after the post
   day cost 1.21–1.65× the typical fee, against 1.01–1.03× on the post day.
5. The tracker loses a day around the price war; quotes that won and quotes that lost have the same
   distribution of price ÷ list: one multiplier carries no lane structure.
6. D01 is a third of the market. 45% of requests come in batches. 64–67% of requests of 60 km or more have
   a request on the reverse lane the same or the next day.
7. The capital carries about 75 `same_day` orders a week at 3% late, and 112–172 at 11–19% late.

**From v2's 32 result lines and a second reading of the rules** *(measured between worlds, or read in the code)*

8. **Margin follows volume (r = 0.79); the on-time share does not fall with volume (r = −0.11).** Worlds
   differ in how many orders they can carry; the gates and the 35% target are the same in all of them.
9. **A late order is an expired gig (8.7 against 8.2 a world), and each expired gig goes with €132 more
   driver fees: about €1,150 a world.** The code explains it: an expired gig, already late, is posted
   again at 1.8× the typical fee, 2.8× two hours later, and stays there overnight. The late tiers are
   10% / 25% / 50% of the price: that fee buys nothing. Between `lastPickupAt` and the end of its window
   an open gig cannot be booked at all, and the desk waits for `gig_expired`.
10. **The fee clock ticks when nobody can act.** The climb from 0.85× to 1.6× is spread over every daytime
    half-hour to the warning: a `next_day` gig posted at 15:00 is at about 1.2× at 07:00 next morning, a
    Friday gig due Monday at 1.48× on Monday 07:00 (Saturday and Sunday tick). This is point 4.
11. **Drops are the other face of the worst worlds** (late against drops r = 0.69; 31 drops a world, 11% of
    bookings). hold-14 and dev-07 have 72 and 58 drops; the median is 30 and the next world has 42. A spike
    like that needs a cause that hits many drivers at once. The flu comes every week, so snow is the
    candidate ("drop bookings that must start that day"), and the desk ignores `forecast` events. *A guess
    until R7: `not_ready` visits do not separate these two worlds (8 and 7 against a median of 4).*
12. **The worst world is the richest**: hold-10, 91.8% on time, €14,067, 293 orders at €179 each, 46
    warnings. The 90% is at risk where the week is good.
13. **Floor quotes (205 a world, priced above the tracker) win about 31%**, nearly as often as normal
    quotes: where the typical fee is high against the list price, dealers accept more. The typical fee
    carries part of the competitor's lane factor. Floor outcomes do not teach the tracker.
14. **`same_day_min_supply` 100 strips `same_day` from 170–313 requests in 7 of 32 worlds**; in 5 of them
    the busy yard's town kept 30–99 drivers, so it is neither ring nor capital (mean margin €8,461).
15. `within_3_days` is 13 of 232 orders. Failed visits in 32 worlds: `not_ready` 118, `no_plates` 38,
    `closed` 19. Slack is measured to 20:00, not to the delivery site's closing time. Premium cars need
    experienced drivers, and the gates count every driver. `order_won` already shows when a note moved the
    ready day. Friday's slow options are due on the last Monday.

## Principles for this round
- **Spend safety on gates, not on price.** Every "tax back" through the win target (0.45) was unsafe and
  worth €100–160: it cuts the price of the orders we would win anyway. Opening a class at full price (the
  ring) was worth €1,500. The unspent safety (96.5% on average against a 92% rule: about 10 late orders a
  world) should buy *new classes*, in the worlds and on the days that can carry them.
- **A fee is worth what it can still save.** Before `lastPickupAt` it can save the order, the dealer's
  trust and a place in the 90%. After it, it can save one refund tier.
- **Measure as the world measures**: opening hours, `lastPickupAt`, who may drive the car.
- **The plan lives in the world.** When our process stops, gigs keep their fee schedules. Put a new
  escalation into the schedule at post time where you can, not into a timer; and keep `rejoin()` right.
- **One load number should move both sides of the spread**: the dealer's price and the driver's fee.

## Tier 0, round 2: sweeps that need no code
On v2, smoke first, then dev for what looks good. Two briefs, so that neither holds the slots for long:
`prompts/gemini-sweeps2.md` (the fee side: S7–S9, S16, S17) and `prompts/gemini-sweeps3.md` (the quote side:
S10–S15). The grids leave out the champion's own values, except S14's.

| # | Status | Command | Why |
|---|---|---|---|
| S7 | `open` | `lab sweep -g fee_open=0.70,0.75,0.80` | S3 was still rising at 0.85 (+€795 at 0.90, +€1,362 at 0.85 on smoke): the floor was not found. Watch `gig_dropped` and `deadline_close`. |
| S8 | `open` | `lab sweep -g steep_max=1.8,2.3` and `lab eval --seeds-from smoke -s steep_open=1.6 -s steep_max=1.6` | Point 9: are fees up to 2.8× after the warning buying on-time orders? 1.8 is one flat step, (1.6, 1.6) is "no steep schedule at all". Crude form of idea 15. Never set `steep_open` above `steep_max`: the schedule would be empty. |
| S9 | `open` | `lab sweep -g fee_warn=1.3,1.45` | Only 1.9 was ever tried (worse). With the opening at 0.85 the climb is steeper than at v0. |
| S10 | `open` | `lab sweep -g same_day_markup=0.12,0.20` | Speed is what dealers pay for and what costs us drivers. Never swept. |
| S11 | `open` | `lab sweep -g expected_fee_mult=1.1,1.4 -g min_margin_frac=0.08,0.18` | The floor assumes a fee of 1.25× typical; we pay about 1.0×. 205 quotes a world sit on it and win 31%. Both directions are open. |
| S12 | `open` | `lab sweep -g dealer_lr=0.05,0.08` | The global step went 0.02 → 0.05 for +€281. The dealer factor carries trust and the competitor's reaction, still at 0.02. |
| S13 | `open` | `lab sweep -g gate_radius_km=70,90` | The ring at 55 km was the biggest win. Is there a second ring for slow options? Report `won_ring`, `late_ring`. |
| S14 | `open` | `lab sweep -g price_target_win=0.35,0.40 -g min_supply=20,30` | 0.45 was unsafe three times; 0.40 and the looser gate are untested on v2. The (0.35, 30) cell is the champion and must show Δ = 0.00. |
| S15 | `open` | `lab sweep -g long_drive_min=480,0 -g slack_per_drive=0.25,0.5` | Steering went in as a bundle. Which rule earns its keep at v2 (38 and 24 options dropped a world)? The jury asks for "with and without". |
| S16 | `open` | `lab eval --seeds-from smoke -s step_min=3 --name live-parity` | Not an improvement: a check. The final has no 10-minute steps. Margin and on-time share should stay within noise; if not, tell the lead at once. |
| S17 | `open` | `lab eval --seeds dev-07,dev-10,dev-14,dev-01,dev-13,dev-02 -s guard_target=0.95 -s guard_band=0.02 --name guard-low` | The old guard at 0.97 cost €905. Does a guard that only wakes near the edge lift dev's six weakest worlds, and what does it cost? (It can only close the gate: idea 10 is the real brake. The lead checks hold-10 and hold-14.) |

## Tier 1: new mechanisms, ordered by expected gain per hour of work

### 15. `open` Late-order triage: a car that cannot be on time is a cost to cut, not a rescue to pay for
- **Mechanism.** A fee can save an order only until `lastPickupAt`. After it the car is late whatever we pay,
  and the refund table pays little for speed: 10% up to 2 h, 25% up to 24 h, 50% up to two business days.
- **Evidence.** Point 9. `repost()` gives an expired gig the steep schedule (`steep()` also climbs at
  night). 8.7 expired gigs a world; €132 more fee with each, between worlds.
- **Change.** `late_fee_open` (default 0 = off, the champion's steep schedule): an order that can no longer be
  on time (unstaffed with `now > lastPickupAt`, or its gig expired) is *lost*; its gigs open at this multiple
  of the typical fee (try 1.0) and climb in daytime steps to `late_fee_max` (1.3) by the next tier boundary
  minus the drive, never steeply. In the world's last 36 hours they do go to `steep_max`: an undelivered car
  costs twice its price. `late_repost` (default off): in `tick()`, a lost order whose gig is still open is
  withdrawn and posted again without stop windows at once, instead of standing unbookable until
  `gig_expired`. Rebuild the lost set in `rejoin()` from the snapshot.
- **Measure.** dev. `stats`: fees paid on lost orders and on warned orders that were saved (cents and
  counts), reposts, late orders by tier. The on-time share should not move at all.
- **Risk.** A cheap late car waits longer and may slip a tier: the climb to the boundary guards it.
- **Guess.** **+€0.5–1.0k**, no risk to the 90%. Brief: `prompts/gemini-triage.md`.

### 16. `open` The fee clock runs only when it can matter
- **Mechanism.** A raise sends no notification, and an old gig is one that drivers wait on. A climb that runs
  through the evening, the night's edges and the weekend meets the morning's drivers at a high fee.
- **Evidence.** Points 4 and 10. The `night_hold` of wave 2 held only gigs posted after 17:00.
- **Change.** `ramp_hours` (default 0 = climb from the post, as today): the climb from `fee_open` to
  `fee_warn` takes only the last this-many daytime hours before the warning point; until then the fee holds
  at the opening fee. Try 4 and 6. `ramp_skip_closed` (default off): Sunday is never daytime for a schedule,
  Saturday only when every site of the gig has Saturday hours. And the other end: `fee_open_near` (default 0
  = `fee_open`) with `near_slack_min` (240): a gig posted with less than this to `lastPickupAt` opens higher
  (try 1.0), because there a drop or a slow booking is a late car (drops grew when the opening fee fell).
- **Measure.** dev, the three flags apart. `stats`: booked fee ÷ typical fee (sum and count) by option and by
  "booked on the post day or later"; drops by slack class; `deadline_close`.
- **Risk.** A fee that holds uses up slack: watch the warnings.
- **Guess.** **+€0.3–0.6k**. Brief: `prompts/gemini-feeclock.md`.

### 17. `open` Slack by opening hours: measure slack as the world does
- **Mechanism.** The desk's slack is deadline − ready − drive. The world's `lastPickupAt` counts the sites'
  stated hours; a car left at a closed site is delivered when it next opens (rule 4), and drivers plan inside
  the hours. Every request carries `hours` for both sites, and Saturday hours.
- **Evidence.** Point 15, and slack is the strongest safety lever we have (worst world 90.3% at 120 minutes,
  94.4% at 180). **Check first, in ten minutes on one reveal:** when do delivery sites close? If nearly all
  close at 20:00 or later, drop this idea and write that down.
- **Change.** `slack_by_hours` (default off): per option, `earliest` = the first minute from max(now + 15,
  the note's ready time) at which the pickup site is open; `last_pickup` = the last minute t with the pickup
  site open at t, the delivery site open at t + drive, and t + drive ≤ the deadline (search back over days:
  Saturday hours, Sunday closed; a private address uses its window). Slack = `last_pickup` − `earliest`. The
  slack rule and the long-drive rule use it. Prove it: for won orders without a note, `last_pickup` must
  equal the order's `lastPickupAt` (`stats`: count and summed absolute error).
- **Measure.** dev; then give the tax back on top: `-s min_slack_min=150` and `120`.
- **Guess.** Removes late orders that look safe today, and lets the 180 minutes come down: **+€0.3–0.8k**.
  Brief: `prompts/gemini-hours.md`.

### 18. `open` A price that knows the cost: undo the adverse selection
- **Mechanism.** The competitor's lane factor "follows how hard the lane is for drivers" and is "almost the
  same in every world". The typical fee is the cost of the lane to a typical driver. One multiplier on the
  list price therefore wins the lanes where the competitor is dear, "often the difficult lanes" (handbook),
  and loses the easy ones: we are left with the cars that cost most and run late most.
- **Evidence.** Points 5 and 13.
- **Change.** `fee_weight` w (default 0): the base of the price is list × (typical fee ÷ (`fee_ratio_mid` ×
  the request's highest list price))^w, clipped to ±25%, with `fee_ratio_mid` 0.9 (the median ratio); then
  the tracker's multiplier and the dealer factor as today. Try w = 0.25, 0.5, 0.75. Easy lanes get cheaper,
  so we win more of the cheap, safe cars; hard lanes get dearer. `learn_from_floor` (default off): a floor
  quote that *wins* moves the tracker up like any win; one that loses teaches nothing.
- **Measure.** dev. `stats`: quotes and wins by third of typical fee ÷ list; driver fees ÷ revenue (1 point is
  €280 a week); late orders by third.
- **Risk.** The typical fee has noise per request: hence the clip.
- **Guess.** **+€0.5–1.5k**. R8 gives the exact weight and the lane table. Brief: `prompts/gemini-costprice.md`.

### 19. `open` The thermostat: one load number per pool sets the price and the opening fee
- **Mechanism.** "The competitor knows nothing about your drivers, your other orders or your timing. That is
  your advantage." A fixed 35% target taxes Monday's empty board to protect Wednesday's full one. The
  backlog gate knows the load but only as on/off.
- **Evidence.** Points 8 and 12; principle 1.
- **Change.** Load L (0 to 1) = (orders near the pickup still unstaffed `load_stale_min` (20) daytime
  minutes after their post + `price_target_win` × quotes in flight near the pickup) ÷ the backlog gate's
  limit; at 1 the gate declines, as today. `load_tilt` (default 0): price × exp(tilt × (L − `load_mid`)),
  try tilt 0.2 with mid 0.25: 5% cheaper on a clear board, 15% dearer just under the gate. `load_fee_tilt`
  (default 0): the opening fee × (1 + this × L), try 0.3: when the pool is slow, pay for speed and charge
  for it. The tracker learns from tilted quotes as from any (also try: they do not teach).
- **Measure.** dev; report the worst world. `stats`: mean L at the quote, wins and late orders by band of L.
- **Guess.** **+€0.5–1.5k**, and a better worst world. Brief: `prompts/gemini-thermostat.md`.

### 20. `open` A same-day quota per pool instead of a threshold
- **Mechanism.** Capacity for `same_day` is drivers free today near the car. A threshold of 100 drivers gives
  the capital no limit and every other town nothing.
- **Evidence.** Points 7 and 14.
- **Change.** `same_day_quota` q (default 0 = off): a pool takes at most max(1, q × its drivers within 30 km)
  `same_day` orders a day, counting today's wins plus `price_target_win` × quotes in flight; with it,
  `same_day` is quoted from `same_day_quota_min_supply` (40) drivers up, not from 100. Try q = 0.04 and
  0.06. The capital gets a daily cap for the first time (about 16–24 at 400 drivers).
- **Measure.** dev; report dev-02, dev-10 and dev-15 (three of point 14's worlds) apart. `stats`:
  `dropped_same_day_quota`, `same_day` wins and late orders by pool size (≥ 200, 100–199, 40–99).
- **Risk.** Uncapped, `same_day` in pools of 30–200 was 24% late (set B).
- **Guess.** **+€0.3–0.8k** in the worlds the threshold starves, safety in the rich ones.
  Brief: `prompts/gemini-quota.md`.

### 21. `open` Friday has two days of drivers, and by Thursday we know what we can afford
- **Mechanism.** Friday's `next_day` and Thursday's and Friday's `within_3_days` are due on the last Monday
  at 20:00: Saturday's weekend drivers and a whole Monday with no new requests. Trust, satisfaction and the
  competitor's reaction are worth nothing after Friday 18:00. And the 90% is a share of the week: on
  Thursday noon most of the week's late orders are known.
- **Evidence.** Principle 1; v2 ends at 96.5% on average.
- **Change.** (a) `fri_gate_min_supply` (default = `min_supply`): on Friday, an option due on the last Monday
  passes the supply gate from this many drivers (try 10), slow options only. (b) `fri_slow_discount`
  (default 0): those options × (1 − d), try 0.05; they do not teach the tracker. (c) `surplus_min` (default
  0 = off) with `surplus_relax` (a comma list): from Thursday 12:00, surplus = the late orders we could
  still take and end at 94% (count known late orders, orders past their deadline, and unstaffed orders past
  their warning as late). While it is at least `surplus_min` (try 6), the named classes open: `slack`
  (`min_slack_min` 120), `midtown` (`same_day` from 60 drivers), `ring` (`same_day` for ring pickups before
  11:00). They close again under half of it. R6 says which class pays most per late order.
- **Measure.** dev, (a)+(b) and (c) apart; report the worst world. `stats`: Friday wins by option; won, late
  and margin of orders that came through an opened gate.
- **Risk.** The surplus is an estimate until Monday. Friday's slow orders are themselves ballast.
- **Guess.** (a)+(b) **+€0.3–0.8k**; (c) **+€0.5–1.5k**. Brief: `prompts/gemini-friday.md`.

### 22. `open` Snow: read the forecast (after R7 confirms it)
- **Mechanism.** In snow, drives are slower, drivers "drop bookings that must start that day", and a car on
  summer tyres cannot be collected: the visit fails as `not_ready` and the dealer moves its deadline. The
  desk ignores `forecast` (`from`, `to`, `placeIds`) and the summer-tyres flag that `notes.py` already reads.
- **Evidence.** Point 11.
- **Change.** `snow_guard` (default off): keep the forecasts. Quoting: when the pickup or the delivery is in
  a forecast place and the option's working time overlaps the snow, no `same_day`, and the slack rule asks
  `snow_slack_min` (120) more. Posting: a car with the summer-tyres flag gets a pickup window from the end
  of the snow at its places (when the deadline allows; else wait for `order_changed`). Gigs that must start
  in the snow open at `fee_open_near` (idea 16).
- **Measure.** The snow worlds that R7 names, then dev. `stats`: forecasts, options dropped, drops in snow.
- **Guess.** Safety on two of the five weakest worlds, if R7 confirms. Brief: `prompts/gemini-snow.md` (R7 first).

### 23. `open` Free signals the desk throws away
- (a) **The won order says the note moved the ready day.** `order_won` carries the moved deadline; the desk
  uses that only after the first failed visit (`retry_from`). `ready_from_deadline` (default off): at the
  first post, move the pickup window by (order deadline − the won option's deadline) when that is a day or
  more, *then* read the note's clock time on that day. Exact to the day in any language and any spelling.
  118 `not_ready` visits in 32 worlds, each half a fee and a lost half-day.
- (b) **Who may drive the car.** `eligible_supply` (default off): for a premium car the gates and the
  `same_day` rule count experienced drivers only (rating ≥ 4.8 and ≥ 50 gigs), for a note that says manual,
  manual licences only. `stats`: premium orders won and late.
- (c) **`release`** says when a car held for payment can be collected: keep it, and never plan a pickup
  before it when posting again.
- (d) **The note's delivery side at quote time** (this is 11c): closing hours and a tighter deadline in the
  note shorten the option's slack before we price it, not only the stop window after we won.
- **Guess.** **+€0.1–0.3k** and a few late orders; an hour of work. Brief: `prompts/gemini-signals.md`.

## Tier 2: bigger bets
### 24. `open` Inbound: a car that goes where drivers live
- **Mechanism.** "A driver who lives near the delivery place ... needs much less"; the handbook's first sign of
  a good request is that "it goes towards towns where drivers live". The gate looks at the pickup only.
- **Evidence.** 100–131 requests a week come to the capital from other towns, mostly from towns we decline;
  6–10% of bookers live within 30 km of the delivery although the app never notifies them. Free cut first:
  in the set-B reveals, the late share of thin pickup → capital delivery, by option.
- **Change.** `inbound_min_supply` (default 0 = off): a pickup that fails the supply gate passes for slow
  options when this many drivers (try 200) live within 30 km of the delivery and the drive is under
  `inbound_max_drive` (240 minutes); price × (1 + `inbound_markup`) (0.05); the gig opens at
  `fee_open_inbound` (1.0): the driver pays a ticket out. Second step: at the post, direct offers to up to
  three drivers who live near the delivery and viewed a gig of ours today. That uses offers as the
  notification the app does not send, not as a rescue.
- **Guess.** 20–30 orders at €30: **+€0.6–0.9k**. **Risk.** Thin `next_day` was 16% late in set B.

### 25. `open` Price what we decline
- **Mechanism.** A decline quotes 4× list and never wins: 350 quotes a world. But on the outage day the
  dealers of a region pay a backup about 30% dearer than the competitor, a dealer with 25 counts of trust
  accepts 25% more, and "a driver goes as far as the fee pays".
- **Change.** `thin_fee_mult` (default 0 = decline): a pickup under the supply gate is quoted for its slow
  options at max(the tracker's price × `thin_markup` (1.25), `thin_fee_mult` (1.8) × typical fee ÷ (1 −
  `min_margin_frac`)): the price that pays a driver from far away. A won order opens at `thin_fee_open`
  (1.3). At most `thin_cap_day` (4) such wins a day. They do not teach the tracker.
- **Measure.** dev: won, late and margin of these orders; how many fall on the outage day.
- **Guess.** 10–20 orders a world: **+€0.3–1.0k**. Best together with 21(c): only with a surplus.

### 26. `open` Hitch: a stuck car rides with the next car going its way
- **Mechanism.** The app notifies by a gig's *first* pickup, and for a driver with one of our cars a second
  one "costs only the extra time and tickets". Capital → Hyvinkää followed by Hyvinkää → capital is a round
  trip without a ticket, notified to 330–440 drivers instead of 5–22. Hyvinkää is the top pickup town and
  the top delivery town. The desk posts multi-car gigs for trade-ins only.
- **Change.** A policy subclass, `policies/hitch.py`. When an order is won, or a gig has waited
  `hitch_after_min` (20) daytime minutes, look among our open, unbooked single-car gigs for a partner: A then
  B, with B's pickup within `hitch_km` (15) of A's delivery, B's site open on arrival, both on time with
  `min_slack_min` to spare, at most 12 hours of driving; the first pickup at the end with more drivers.
  Withdraw both, post one gig at `hitch_fee` (0.85) × the sum of what they would open at. If it is unbooked
  after `hitch_patience_min` (30), or at a warning, split it again. Then `hitch_discount`: a request that
  would pair with a waiting gig is quoted lower. Care: fees per gig not per order, `order_cancelled` with
  `shortened`, a failed visit in a two-car gig, `rejoin()`.
- **Measure.** R11 first (how many pairs were there to make?). Then dev: pairs posted, booked, split; the
  pair's fee against the two typical fees; late orders in pairs.
- **Guess.** Unknown; the creative entry for the jury. Supersedes 12(c).

### 27. `open` Answer the view: a private raise for the driver who is looking now
- **Mechanism.** A view is a driver with the app open. An offer is read by a driver who has the app open, and
  "saves most on gigs whose fee drivers expect to rise": the offer pays the waiting driver now, and the fee
  on the board does not move for everyone else. The 218 offers of v0 went out after the warning, to drivers
  who had looked hours before.
- **Change.** `view_offer_mult` (default 0 = off): when a driver views a gig that has been open for
  `view_offer_after_min` (15) minutes and has not booked it within 2 minutes, offer them the gig at the
  board's fee × this (try 1.10). Three offers a driver a day, three open a gig.
- **Measure.** R10's waiting cut first. It depends on speed: the final answers each event, practice answers
  every 10 minutes, so measure with `-s step_min=3` on smoke for both arms. `stats`: offers by answer.
- **Guess.** Unknown; a cheap probe with a clear answer (accepted share against 3 of 218).

### 28. `open` The lane table (after R8)
The part of the competitor's lane factor that "is almost the same in every world", fitted once over all our
reveals as a pickup effect plus a delivery effect, shipped as a small JSON file, used as price × exp(effect ×
`lane_prior_weight`) (default 0). Idea 18 is its one-number form.

### 29. `open` A share band per dealer (after R12)
The competitor cuts its prices each morning for a dealer "where you won most", and raises them "where you
won few". If R12 finds the thresholds: `dealer_share_cap` (default 0 = off) prices a dealer up for the rest
of the day once we hold more than this share of its requests today, so that it never starts cutting at D01.

### 30. `open` Monday's price from the driver list (after R9)
"The competitor has the same problem: it pays its own drivers more." If the world's price level follows the
size of its roster, which we hold before the first request, the Monday prior (1.35 for every world, against
levels of 1.26–1.54) can be read off it: `prior_from_roster` (default off).

## Still open from round 1
### 10. `open` **The brake.** Insurance for the final; do the cheap form before Sunday
- **Mechanism.** The minimum is a share: nine on-time orders pay for one late one. One world of 32 is at
  91.8%, and it is the richest (point 12). `guard_target` can only close the gate, and at full tightening it
  declines everything: a share that takes no orders cannot recover.
- **Change (cheap form).** `brake_at` (default 0 = off; try 0.935): while the projected on-time share (known
  late, past the deadline, and unstaffed past the warning at weight 0.7) is under it, quote only *ballast*
  (a pickup with 200 drivers or a ring pickup, `next_day` or `within_3_days`, a drive under 120 minutes, no
  time in the note) at `brake_discount` (0.08) under the tracker's price, and decline the rest, until the
  projection is 1 point above `brake_at`. Ballast adds on-time orders; the old guard only stopped orders.
- **Measure.** First show that it works: `brake_at` 0.96 on `--seeds dev-07,dev-10,dev-14,dev-01` (it must
  wake and lift them). Then 0.935 on dev for the cost (it should almost never wake). `stats`: minutes
  braked, ballast orders won and late. The lead checks hold-10 and hold-14: agents never tune on holdout.
- **Round 1's full form** (project late orders from the class table, Friday as the repair day) is idea 21(c)
  turned around. Brief: `prompts/gemini-brake.md`.

### 8. `open` An early staffing alarm instead of the deadline warning
`alarm_after_min` (default 0 = off): an order with no driver this many daytime minutes after its post (45 for
`same_day`; 10:00 on the deadline day for the others) jumps to `alarm_fee` (1.4) and then climbs. Second
signal: fewer than 2 viewers in 15 minutes. *Round 3 adds:* write the jump into the schedule at post time
(a flat part, then a step), so it needs no timer and survives a restart; and it is the same-day half of
idea 16. Do them in one branch if 16 is taken first.

### 9. `open` Give drivers an earlier deadline than the dealer's
`delivery_buffer_min` (default 0) and `buffer_per_drive` (0): the delivery stop's window ends that much
before the deadline (try 45 + 0.1 × drive); a repost after expiry uses the order's own window. 11 of 41 late
orders at v0 had a driver. R3 first. *Round 3 adds:* withdraw and repost with the full window at the
buffered window's own last pickup time, not at its expiry (point 9: a gig is dead before it expires).

### 11. `open` Notes: score the reader on the truth we already hold, then price out what we cannot read
*Round 3 adds:* no harvest worlds are needed for a first pass. Every champion world holds about 95 won
orders with a note and its truth (`readyAt`, `releasedAt`, real hours, `needsPlates`, `noteDeadline`). (b)
Score `notes.py` field by field on them and fix it: `not_ready` 118, `no_plates` 38 and `closed` 19 failed
visits say where. (c) Use the reader when quoting (23d), and `note_unsure` (default `quote`) = `decline`
when a note has a time the reader cannot place. (a) The harvest policy stays for a second pass.
Brief: `prompts/gemini-notes.md`.

### 12. `open` Supply follows our cars: return offers, return-aware quotes
(a) `return_offer_mult` (default 0): when one of our drivers will deliver within 30 km of an open gig's
pickup in time, offer them that gig at 0.8× the typical fee as they deliver: the only drivers we *know* work
today are the ones carrying our cars. (b) Only if (a) is accepted one time in five: `return_gate` lets a
thin-town request pass when such a driver is on the way and the car goes towards their home. (c) is now
idea 26.

### 5. `open` The twin ladder: let batches bracket the competitor
`ladder_spread` (default 0): the cars of a batch are quoted at the estimate × exp(±spread), evenly spread.
A batch that both wins and loses brackets the dealer's price in one step. *Round 3:* low priority after
wave 2; worth it only as the measuring half of R8 (it gives the slope of acceptance for free).

### 13. `open` Release a late driver · 14. `open` Flu day
13: on `driver_late`, release (free until they leave) when `pickupAt` makes the car late and a fresh post can
still be on time. 14: distinct viewers per town by 10:00 against earlier days; a fall of a quarter means the
flu: that day lower the `same_day` quota (idea 20) or raise `same_day_min_supply`. R13 says if views can
carry it.

## Research (no policy change; results feed the ideas above)
First, once, for everyone: reveal the champion's worlds (ids in `champion/results/*.jsonl`, one request
each) into one folder outside the repo and share its path: agents the 16 dev worlds, the lead the holdout
ones. Briefs: `prompts/gemini-research3.md` (R6 and R8), `prompts/gemini-snow.md` (R7).

- R6. `open` **The class table at v2, and the loose run.** R2 on the champion's worlds, with new cuts: premium car;
  private pickup or delivery; trade-in; a time in the note; the delivery site's closing hour; drive band;
  pickup pool (capital, ring, 100+, 30–99, under 30) × delivery pool; booked on the post day or later; drops;
  weekday. Per class: orders, late, margin an order, booked fee ÷ typical. Then one *loose* dev run that is
  never promoted (`min_supply` 10, `same_day_min_supply` 0, `far_options` all, `min_slack_min` 120,
  `long_drive_min` 0) and its reveals, for the classes v2 never wins. Output: **margin per late order by
  class**, the order in which ideas 20, 21(c), 24 and 25 should open gates.
- R7. `open` **Snow.** `forecast` events per world; drops and `not_ready` visits inside snow windows at snow
  places; late orders touched by snow. Is point 11 snow? Names the worlds for idea 22.
- R8. `open` **What predicts a win beyond price ÷ list.** One logistic fit over every quote that was not a
  decline (about 11,000 on the 16 dev worlds) with a level per world and day: log(quote ÷ list), log(typical fee ÷
  list), log km, pickup place, delivery place, option, weekday, hour, batch size, and the dealer's trust
  count at that minute (from the account). Gives the slope of acceptance, the weight for idea 18, the lane
  table for idea 28, and whether +1% per count of trust is visible as the rules state it.
- R9. `open` **The world's price level against its roster** (drivers in all, in the capital ring). For idea 30.
- R10. `open` **Do we bid against ourselves, and do drivers learn to wait?** Drops followed within 30 minutes
  by the same driver booking a dearer gig of ours; steep gigs booked by drivers who held another booking of
  ours. Booked fee ÷ first viewed fee by weekday (does it creep up from Monday to Friday?). Bookers who had
  viewed the order earlier at a lower fee: how many, how much more they got, how long they waited: the size
  of idea 27, and the case for a calm board (no gig of ours far above the others in the same pool).
- R11. `open` **Pairs.** Among won orders: pairs open at the same time that one driver could chain (delivery of
  one within 15 km of the pickup of the other, windows fit, at most 12 hours). And among all requests, had
  we priced to pair. For idea 26.
- R12. `open` **The competitor's morning reaction, from reveals we hold.** Per world, dealer and day: our share
  of the dealer's requests (declines count as lost), against the change in what that dealer accepted the
  next morning. Where does it start to cut, where to raise? No forks needed (R4 asked for them). For idea 29.
- R13. `open` **Views as a census.** Distinct viewers per pool by 10:00 against that day's minutes-to-book and
  late share in the pool. Can the morning's views size the day's capacity (ideas 19, 20, 14)?
- R14. `open` **The value of speed.** When we quoted two or three options, which one did the dealer take, by
  the price gap between them? Margin and late share per won option. For S10 and a `within_3_days` discount
  (13 orders a world, none late: the cheapest ballast there is).
- R1 `open` (X-ray by fork; needs the lead) · R2 → R6 · R3 `open` (how late is late; with idea 15 it also
  gives the tiers) · R4 → R12 · R5 `open` (the capital's daily ceiling; idea 20 needs its number).

## For the lead: the next waves and the instrument (agents: propose, don't touch)
- **Waves of four**, merged to `main` first so that the worktrees see this file and the briefs:
  `TURNS=120 scripts/wave.sh <model> triage feeclock costprice sweeps2`, then `brake thermostat quota
  research3`, then `friday hours signals sweeps3`, then `snow notes`. The first wave is the money that
  cannot hurt the 90%; the second is the worst world and the tables the third needs.
- **More seeds for small effects.** A second dev set of 32 (`dev-17` … `dev-48`) brings one standard error
  from about €250 to €150. Wave 2's four results (+46, +104, +215, −98) cannot be told from zero today.
- **Stack the positives once.** One dev run with wave 2's positive flags together on v2 (`trust_invest`
  0.1, `fee_open_dense` with `night_hold`, `morning_reset`), after merging those branches' flags (all
  default to off). S1–S6 were individually unsafe or small and together +€2,644.
- **Quieter secondary numbers in `summary.json`**: driver fees ÷ typical fees of the won orders, price ÷
  list of the wins, late orders by class. A fee idea shows there long before it shows in the week's margin.
- **Insurance.** v2 was promoted as an exception to the 92% rule. Idea 10's brake, S17 and idea 15 (which
  cannot hurt the share) are the three things worth having in the final desk whatever else lands.
- **Holdout is a little less blind now.** Points 8–15 read all 32 result lines, hold-10 and hold-14 among
  them, to find mechanisms (no parameter was set on them). Ideas 15, 20 and 22 owe something to those two
  worlds: when one of them is claimed, weigh its holdout gain on the other 14 worlds too.

## Finished
| # | Idea | Result (dev, paired) | Note |
|---|---|---|---|
| 1 | The ring: gate on who can reach the car | +€1,587 ± 257 against v0; in v1 | `20261113-2358-gemini-ring.md` |
| 2 | Option steering | +€336 ± 196 with `min_supply` 20; safer; in v1 | `20261114-0010-gemini-option-steering.md` |
| S1–S6 | Tier 0 sweeps | together +€2,644 ± 306 against v0; four of them in v2 | `20261114-0017-gemini-tier0-sweeps.md` |
| 3 | Two clocks for the price | +€46 ± 204 against v1; not merged | branch `exp/gemini-clocks` |
| 4 | Trust is capital | invest +€215 ± 157; gain −€285 ± 117; guard −€711 (smoke); not merged | branch `exp/gemini-trust` |
| 6 | The fee floor (dense towns, night hold) | +€104 ± 196 against v1; not merged; 16 and S7 follow it | branch `exp/gemini-feefloor` |
| 7 | Bulk orders: the yard budget | −€98 ± 220; the bulk world safer; not merged; 19 and 20 count quotes in flight | branch `exp/gemini-bulk` |

## For the jury (collect as you go)
Each idea is one sentence, one reason and one paired number. Candidates for the story, beyond the ring:
*a late car is a cost to cut, not a rescue to pay for* (15); *the fee clock only runs when a driver can
act* (16); *one load number moves both sides of the spread* (19); *the 90% is a budget, and Friday is when
we know what is left of it* (21, 10); *a stuck car rides with the next car going its way* (26). What did
not work counts too: the ledger guard, direct offers after the warning, a trust gain on top of a tracker
that had already learned it, and four ideas we could not tell from zero on 16 weeks.
