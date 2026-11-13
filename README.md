# Swarm Dispatch

Our entry for **[Spread](https://spread.bahnexpress.com)**, the Bahn Express challenge at Junction 2026: a
system that runs a car-transport dispatcher for one simulated week in Finland. It quotes car dealers
against an unseen competitor, posts each won car as a gig for freelance drivers, and sets the fees. The
score is gross margin, and at least 90% of the cars it wins must arrive on time.

The system is built and improved by a **swarm of coding agents** around one shared measuring instrument:
every idea is a flag, every flag is measured on the same deterministic worlds, and every measurement is
written down (`experiments/`). The table below is the history of what moved the margin.

## Results
Level 8 (the final's level), our 16 development worlds, mean per week. Ranked = ≥ 90% on time.

| Version | Mean margin | On time (min) | Ranked | What changed |
|---|---|---|---|---|
| Kit starter | −€72.6k on `spread-1` | 45% | 0 | quotes the list price, posts at the typical fee |
| Baseline v0 | see `champion/` | | | supply-aware selection, learned price multiplier, rising daytime fees, steep escalation |

## How it works (baseline)
- **Selection.** Declines (a deliberately losing quote) when few drivers live within 30 km of the pickup,
  when the deadline leaves too little slack, or when unstaffed orders already pile up near the pickup.
- **Pricing.** List price × a multiplier that starts from the level's prior and tracks a target win rate,
  globally and per dealer; a long losing streak (the price war) freezes it instead of chasing it down.
- **Fees.** A schedule rising over daytime half-hours to the deadline warning, then steep, plus direct
  offers to drivers who were recently active near the pickup.
- **Rules.** Premium cars go to experienced drivers, EVs get charging stops on long routes, notes set
  windows, manual-licence and plate requirements; failed visits, expiries, changes and cancellations are
  handled as the rules require (these mechanics follow the organisers' starter kit).

## Run it
```sh
uv sync
cp .env.example .env            # put the team key in SPREAD_KEY
uv run lab eval --seeds-from smoke   # 4 practice worlds, compared with the champion
uv run lab final                # the live final: start it before 08:00, it waits and rejoins by itself
```
`uv run lab --help` lists everything. [`AGENTS.md`](AGENTS.md) is the working manual (for people too),
[`docs/GAME.md`](docs/GAME.md) a condensed summary of the game.

## Credits
The organisers' Python kit (`spread`) is the API client; our desk's rule-handling mechanics (rejoin,
reposting, retries after failed visits, trade-in splitting) follow the kit's starter. MIT licence.
