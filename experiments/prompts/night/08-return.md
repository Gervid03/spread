Idea #12 (a) of experiments/IDEAS.md, "Supply follows our cars: return offers". Implement `return_offer_mult`
(default 0 = off): when one of our booked drivers will deliver within 30 km of an open gig's pickup in time to do it,
send them a direct offer for that gig at this multiple of the typical fee (try 0.8 and 1.0) as they deliver. Respect the
offer limits in the rules (docs/kit/RULES.md). Stats: return offers sent, accepted, late. The test that matters is the
accepted share (direct offers after deadline warnings were 3 of 218). Stop at (a); report whether (b) is worth building.
