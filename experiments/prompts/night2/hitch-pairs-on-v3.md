Idea 26, the paired-gig form (Fable's design): build on the champion on main (v3), no merge needed, compare with the
champion as usual. A second worker builds the return-offer form at the same time. Different routes to the same
volume, and the better one wins. Read idea 26 in experiments/IDEAS.md (the Change paragraph is your spec) and the R11
table in `experiments/20261114-0635-gemini-snow.md` on `origin/exp/gemini-n14-06263-snow-and-hitch-research`
(94 disjoint chains a week).

Implement `policies/hitch.py` or flags in policy.py (default off, +0.00 noop on every smoke seed). (1) Pairing: when an
order is won, or one of our single-car gigs has waited `hitch_after_min` (20) daytime minutes unbooked, look for a
partner among our open, unbooked single-car gigs: A then B, B's pickup within `hitch_km` (15) of A's delivery, B's
site open on arrival, both on time with `min_slack_min` to spare, at most 12 h of driving in the gig. Put the first
pickup at the end with more drivers. Withdraw both and post one gig at `hitch_fee` (0.85) × the sum of what they
would open at. If it is unbooked after `hitch_patience_min` (30), or at a warning, split it again. (2) Volume: a
request that fails the supply gate but would pair with one of our waiting gigs is quoted for its slow options at the
tracker's price (`hitch_quote` default off), at most `hitch_cap_day` (6) wins a day. Care: fees per gig, not per order;
`order_cancelled` with `shortened`; a failed visit in a two-car gig; `rejoin()` must rebuild the pairs from the snapshot's
multi-car gigs. Counters: pairs posted, booked, split; quoted and won through `hitch_quote`; late orders in pairs;
the pair fee against the two single fees.
Smoke: pairing alone (1), then (1)+(2). Dev: the best one, then with `hitch_cap_day` 12. Every dev world ≥ 92% on time.
Report the worst world first, then won orders a week and margin against the champion.
