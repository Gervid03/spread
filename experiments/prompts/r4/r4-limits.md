## Your direction: `r4-limits`, the oracle's prices as a live rule
Branch `exp/gemini-r4-limits`. The TAS price oracle found that at each dealer's true limit, the champion's week is
worth +33.6% (dev-12), with the same orders and the same driver fees. Live there is no oracle, so the question is how
much of it a desk can take from what it sees.
- Read `~/.spread-lab/tas/STATUS.md` and the limit files the `tas-price` agent writes under `~/.spread-lab/tas/<seed>/`
  (`limits-won-apply.jsonl`, later `limits-all.jsonl`): limit ÷ list by dealer, lane, option, hour, day, trust count,
  and the events (price war, outage, snow).
- Build a pricing rule from it: a table fitted on some worlds and **checked on others** (holdout, night-01..32), or a
  model of the limit (dealer factor × trust × the competitor's morning step × event), plus the competitor's deadband
  (keep busy dealers between 30% and 69% won). It must decide in milliseconds.
- Measure the share of the oracle's gain you get: Δ on 16 dev worlds, and what it does to orders and on-time.
- Watch for the trap: a dearer quote that loses is a lost car; a rule that prices close to the limit must not lose more
  cars than it gains in margin. Co-play `probe` shows you the real limit of any waiting quote, to check your estimate.
