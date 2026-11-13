Idea #3 of experiments/IDEAS.md, "Two clocks for the price: the week's level and today's shift".
Implement exactly the flags that section names, with defaults that keep the champion: `morning_reset` (off),
`price_lr_day0` (step size of the day's first outcomes, falling as 1/sqrt(n) to `price_lr`), `war_shift`
(-0.12: a day whose shift falls under it is a price war and never moves the level), a cap on the shift of
+-0.30, and the outage rule (a region of a town + 80 km that wins 8 quotes in a row gets its own upward
shift for the day, up to +25%) behind its own flag. Keep `rejoin()` working: rebuild the level from the
latest wins as the champion does, and start the shift at 0.
Add `stats` counters: wins by weekday, the detected war day, outage regions. Measure as the section says:
smoke first, then dev; compare the morning after the price war with the champion's.
