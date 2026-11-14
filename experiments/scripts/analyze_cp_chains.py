import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
vs_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("champion/results/dev-L8.jsonl")

champ = {json.loads(l)["seed"]: json.loads(l) for l in vs_file.read_text().splitlines() if l.strip()}
rows = [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]

tot: dict[str, float] = {}
acct_c: dict[str, float] = {}
acct_r: dict[str, float] = {}

for r in sorted(rows, key=lambda x: x["seed"]):
    s = r["seed"]
    c = champ.get(s)
    if c:
        print(
            f"{s:8s} | champ {c['margin']:8.1f} ({c['on_time']*100:5.2f}%, w={c['won']:3d}) "
            f"-> {r['margin']:8.1f} ({r['on_time']*100:5.2f}%, w={r['won']:3d}) "
            f"| dM={r['margin']-c['margin']:+7.1f} dOT={(r['on_time']-c['on_time'])*100:+5.2f}%"
        )
        for k, v in c.get("account", {}).items():
            acct_c[k] = acct_c.get(k, 0.0) + v
    for k, v in r.get("account", {}).items():
        acct_r[k] = acct_r.get(k, 0.0) + v
    for k, v in r["stats"].items():
        if k.startswith("hitch") or k.startswith("ret_") or k in ("deadline_close", "gig_dropped", "gig_expired", "late_reposts"):
            tot[k] = tot.get(k, 0.0) + v

n = len(rows)
print()
print(f"=== {n}-WORLD LEDGER / WK ===")
for k in sorted(set(acct_c) | set(acct_r)):
    print(f"  {k:22s}: champ {acct_c.get(k,0)/n:9.1f} -> run {acct_r.get(k,0)/n:9.1f} (d={(acct_r.get(k,0)-acct_c.get(k,0))/n:+8.1f})")

print()
print(f"=== {n}-WORLD CHAIN STATS ===")
for k in sorted(tot):
    print(f"  {k:34s}: {tot[k]:10.0f}  ({tot[k]/n:8.2f}/wk)")
