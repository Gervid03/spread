# Swarm Dispatch

**For the jury: [docs/SUBMISSION.md](docs/SUBMISSION.md) — what the desk does, why, what each idea is worth, and what did not work.**

Our entry for **[Spread](https://spread.bahnexpress.com)**, the Bahn Express challenge at Junction 2026: a
system that runs a car-transport dispatcher for one simulated week in Finland. It quotes car dealers
against an unseen competitor, posts each won car as a gig for freelance drivers, and sets the fees. The
score is gross margin, and at least 90% of the cars it wins must arrive on time.

The system is built and improved by a **swarm of coding agents** around one shared measuring instrument:
every idea is a flag, every flag is measured on the same deterministic worlds, and every measurement is
written down (`experiments/`). The table below is the history of what moved the margin.

## Results
Level 8 (the final's level), mean margin per week on our 16 development and 16 holdout worlds. Ranked = ≥ 90% on time.

| Version | Mean margin | On time (worst world) | Ranked | What changed |
|---|---|---|---|---|
| Kit starter | −€72,612 on `spread-1` | 45.5% | 0/1 | quotes the list price, posts at the typical fee |
| First desk | €6,962 (5 worlds) | 83.5% | 2/5 | selection, learned prices, rising fees |
| v0 | €6,447 dev · €6,837 holdout | 93.0% · 93.2% | 32/32 | only pickups with ≥ 30 drivers within 30 km; aim for a 35% win rate |
| v1 | €7,926 dev · €7,942 holdout | 94.9% · 92.7% | 32/32 | the ring (count drivers within 55 km, slow options only there) + quote only the speeds we can staff |
| v2 | €8,990 dev · €9,414 holdout | 94.4% · 91.8% | 32/32 | open fees at 0.85×, a faster price tracker, no direct offers, 3 h of slack |
| v3 | €10,529 · €11,280 | holdout 94.4% | 32/32 | extended ring (70 km), return to a hub, notes, lead-car pairing (+€1,539 dev, +€1,866 holdout) |
| v4 | €10,884 · €11,703 | holdout 94.1% | 32/32 | lost and late cars repost at 1.0× the typical fee (+€355, +€423) |
| v5 | €11,678 · €12,270 | holdout 93.7% | 32/32 | a direct offer at 1.03× to a local driver who viewed and didn't book; steep fees after the warning (+€794, +€567) |
| v6 | €11,873 · €12,457 | holdout 94.8% | 32/32 | a morning supervisor: calm days loosen the gates (+€195, +€187) |
| v7 | €12,122 · €12,868 | holdout 94.4% | 32/32 | closed loops of 2–4 cars as one gig, reposted from each town in turn (+€247, +€410) |
| **v8** (plays the final) | **€12,564** dev · **€13,214** holdout | 93.7% · **92.2%** | **32/32** | quote towns with 8+ drivers within 55 km (was 22) (+€442, +€346) |

Each step is a paired measurement on the same worlds against the step before; the write-up of every idea, why we
tried it and what did not work: [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

How we got there, with every variant we measured (including the ones that failed):
[`experiments/LEDGER.md`](experiments/LEDGER.md); every experiment note of the swarm era is in the git tag `swarm-era`.

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
