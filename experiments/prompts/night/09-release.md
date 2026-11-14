Idea #13 of experiments/IDEAS.md, "Release a late driver". On `driver_late` (or whenever a booked driver's pickupAt makes
the car late), if a fresh post at the steep schedule can still be on time, release the driver (see the rules for the
release fee) and repost. Flag `release_late` (default False), plus `release_min_slack` (minutes a repost needs, 120).
Stats: releases, late among released, release fees. Smoke then dev.
