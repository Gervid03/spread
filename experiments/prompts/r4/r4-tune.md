## Your direction: `r4-tune`, the stacked desk's interactions
Branch `exp/gemini-r4-tune`. The lead is merging six winners onto v6 in `exp/stack-v7`; each was measured alone, and
several touch the same thing (cp-routes and cp-chains both use returning drivers; cp-margin and cp-demand both price
inbound). Until the stack exists (`git fetch && git log origin/exp/stack-v7`), study the public board's worlds: the
five ranked runs of round 7 (`runs/board.log`, the world ids there) against our dev worlds: do they differ in volume,
events, dealers? Then:
- ablate the stack: each flag off in turn (and on in pairs), on a few dev worlds first, then 16;
- retune the parameters the merge made interact (supply gates, slack, the win target, fee levels) with short sweeps or
  co-play `whatif` on forks;
- find the best combination and run `promote.sh` with its flags.
