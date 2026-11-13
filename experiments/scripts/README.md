# Scouting scripts

Rough, read-only analyses of reveals, written for `../20261113-2330-fable-research-scouting.md`.
Standard library only.

```sh
mkdir ../reveals && cd ../reveals                      # outside the repo: a reveal is ~1 MB of CSV
uv run --project ../spread lab reveal <world id>       # one request; world ids are in each run's results.jsonl
cd ../spread
uv run python experiments/scripts/scout_overview.py ../reveals    # drivers by town, request mix, dealers, batches
uv run python experiments/scripts/scout_bookings.py ../reveals    # fees, minutes to book, who books, late orders
uv run python experiments/scripts/scout_lanes.py ../reveals       # hub lanes, reverse-lane pairs, margin by lane
uv run python experiments/scripts/scout_signals.py ../reveals     # deadline warnings, offers, wins by 2-hour block
uv run python experiments/scripts/scout_classes.py ../reveals/reveal-*   # late share and margin by pickup class x option
```
