# Co-play on dev-12: Claude steers the champion desk through one week, with forks as a what-if oracle

- **Agent / branch:** Claude (the laptop lead) · `exp/claude-coplay` · `scripts/coplay.py` (the harness) + three neutral
  pricing flags in `policy.py` (`dense_supply`, `dense_fee_mult`, `dense_mult_cap`, `dense_cap_max_drive`)
- **World:** dev-12, the dev world closest to the champion's median (v4: €10,418, 254 won, 96.5% on time)

## The harness
`scripts/coplay.py serve --seed dev-12` keeps the world and the desk in memory and steps exactly as
`play_practice`, pausing between turns; `coplay.py do '<json>'` plays a turn. A turn can change Params live, override
the quotes waiting to be sent, raise fees on an order, or run a **what-if**. A what-if forks the world, deep-copies
the desk into the fork, and plays the unchanged desk and each variant to the end of the week on the same future
draws. The state shows this turn's requests (route, our multiple of list, the outcome), the unstaffed orders, the
bookings (fee ÷ reference fee) and the P&L by order class.

**Method note.** A fork made before the first action reproduces the champion to the cent. A fork made mid-week
drifts by about ±€300 from the main line (the copied desk's sets iterate in another order, and the week is chaotic).
**On one world, only effects above ~€300 mean anything.**

## What I saw, and what the forks said
1. **The margin floor carries the desk.** 341 of 837 quotes on this world are floored (raised to 1.25 × the reference
   fee ÷ 0.92), and most of them lose. Lowering the floor everywhere (`expected_fee_mult` 1.1 / 1.0 / 0.9) won 32–53 more
   orders and lost €700–1,330. Pricing the dense hub's pickups cheaper lost €700 (fee 0.9) to €4,950 (cap 1.1 × list).
   Long trips out of the hub need dear drivers.
2. **Short hub-to-hub trips earn the best rate (58% of revenue)**, but pricing them under the competitor (cap
   1.05–1.25 × list) won only 2–4 more orders and lost €250–560. Cheaper prices don't buy volume there. The single
   global multiplier also spreads a local change everywhere: wins at a capped price push the multiplier up for all
   other quotes. **Idea: one tracker per class (hub-short, hub-out, thin), so classes stop moving each other's
   prices.**
3. **Drivers are the ceiling.** Driver fees are 64% of revenue (€20.1k of €31.3k). Win target 0.45 gave 280 orders,
   +€416 and better on-time; 0.55 gave 319 orders but 95.3% on time and less margin. Past ~280 orders a week, each
   extra order costs more in fees and lateness than it earns.
4. **The week is decided Monday to Wednesday.** By Friday 07:46 the desk had won 257 orders; every Friday lever
   (same-day drive limit off / 100 / 150, win target 0.35 / 0.55) changed the week by ≤ 2 orders and ≤ €150.

## Result
Picking the best lever every game morning from forks (an oracle: the forks see the future) gave **€10,834, 280 won,
97.9% on time** against the champion's €10,418 on the same world. All of the gain came from Monday's pick, win target
0.45; nothing later beat the fork noise. **Generalised: `price_target_win=0.45` on v4 over 16 dev worlds: +€212 ±
136 (t 1.56), 9/7 better, worst world 93.5%. Promising, not proven.** It needs 32 fresh worlds before it can be
promoted.

## Verdict
Insight more than a winner: the floor and the driver ceiling are the binding constraints, price is not. The next
structural ideas are per-class trackers (item 2) and cheaper staffing (fees are 64% of revenue), not cheaper quotes.
