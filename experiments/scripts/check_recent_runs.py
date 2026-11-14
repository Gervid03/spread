"""Compare recent runs in lab_home/runs.jsonl against Champion v6 dev-L8."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, stdev

from spread_lab.env import lab_home


def main() -> None:
    champ = {json.loads(l)["seed"]: json.loads(l) for l in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if l.strip()}
    idx = lab_home() / "runs.jsonl"
    if not idx.exists():
        return
    for line in idx.read_text().splitlines()[-25:]:
        e = json.loads(line)
        p = Path(e["dir"]) / "results.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        common = [r for r in rows if r["seed"] in champ]
        if len(common) < 4:
            continue
        ds = [r["margin"] - champ[r["seed"]]["margin"] for r in common]
        ws = [r["won"] - champ[r["seed"]]["won"] for r in common]
        ots = [r["on_time"] for r in common]
        se = stdev(ds) / (len(ds) ** 0.5) if len(ds) > 1 else 0.0
        t = mean(ds) / se if se > 0 else 0.0
        bw_b = sum(1 for d in ds if d > 0.005)
        bw_w = sum(1 for d in ds if d < -0.005)
        print(f"{e['name']:<28} n={len(common):2d} dMargin={mean(ds):+7.2f}+-{se:6.2f} (t={t:5.2f}, {bw_b}/{bw_w}) dWon={mean(ws):+5.1f} minOT={min(ots)*100:5.2f}%")
        if "sunday-tours-dev" in e["name"]:
            for k in ("sunday_staged", "sunday_stage_released_solo", "sunday_tour_posted", "sunday_thin_quoted", "sunday_thin_won", "tour_booked_2", "tour_booked_3", "tour_split"):
                print(f"    {k}: mean={mean(r['stats'].get(k, 0) for r in common):.2f}")


if __name__ == "__main__":
    main()
