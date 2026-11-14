"""Fetch events, reveal, roster and snapshot of finished practice worlds (reads only: no slot, ~4 requests a world).

    uv run python experiments/scripts/signals_fetch.py champion/results/dev-L8.jsonl <out folder>

The other signals_*.py scripts read the folder this writes (one JSON per seed)."""
import json, sys
from pathlib import Path
from spread_lab.env import load_dotenv
load_dotenv()
from spread.client import Client

out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
c = Client()
for line in open(sys.argv[1]):
    r = json.loads(line)
    f = out / f"{r['seed']}.json"
    if f.exists():
        continue
    w = c.world(r["world"])
    data = {"seed": r["seed"], "world": r["world"], "events": w.events(-1), "reveal": w.reveal(), "roster": w.roster(), "snapshot": w.snapshot()}
    f.write_text(json.dumps(data))
    print(r["seed"], len(data["events"]), "events", flush=True)
