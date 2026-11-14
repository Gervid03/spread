## Your task: c3, a learned acceptance model and the lane table (R8, then idea 28)

The user's question (14 Nov): can a fast learned classifier price better than one multiplier? Our inputs are numbers
(places, hours, list price, typical fee, dealer, trust), so the classifier here is a small fitted model, not a
language model. Read docs/GAME.md, R8 and idea 28 in experiments/IDEAS.md, and why idea 18 lost (n14-06042: −€342;
it used the typical fee as a proxy for the lane, and A's margin floor already undid that adverse selection).

**Part 1, slot-free (do this first, it costs no practice worlds).** Reveal every finished level-8 world of v2 and v3
you can find in `runs/` and `champion/results/` (dev, holdout, `night-*`: one request each; many are already in
`/tmp/reveals-*`). From `requests.csv`, take every quote that was not a decline. Fit one logistic model of
won ~ log(quote ÷ list) + pickup place + delivery place + option + weekday + hour + batch size + the dealer's trust
count at that minute (count it from the account lines) + a level per world and day. Standard library or numpy only
(write the fit yourself if numpy isn't there; a few hundred Newton steps are fine). Report:
- the slope of acceptance in log price (what 1% dearer costs in win chance);
- whether the place effects are stable across worlds (fit on half the worlds, check on the other half: the rules say
  part of the lane factor "is almost the same in every world"); if they aren't stable, stop after Part 1 and say so;
- whether +1% per trust count is visible as the rules state;
- a second fit, late ~ the same features + drive minutes + same-day-or-not, over won orders: which classes are late
  under 2% (the user calls these the buffer: easy orders that pad the 90%).
Write the lane effects (pickup and delivery, shrunk towards 0 by their standard errors) to
`src/spread_lab/data/lane_table.json` and the late classes to the note.

**Part 2, only if the place effects held out of sample.** `lane_prior_weight: float = 0.0` (0 = off): price ×
exp(weight × (pickup effect + delivery effect)), clipped to ±15%, before the tracker's multiplier; the tracker then
learns around it. Counters: quotes and wins by third of the lane effect, margin per third. Protocol as usual: noop on
smoke, then weight 0.5 and 1.0 on 8 dev worlds, the 16 only if Δ > 0. Report the worst world first.
