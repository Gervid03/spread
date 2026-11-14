"""Compare cp-wild-tailbrake-dev + cp-wild-tailbrake-night32 against Champion v3T across 16 dev, 32 night, and 48 combined worlds."""
from __future__ import annotations

import json
import pathlib
import statistics


def paired_stats(cand_rows: dict[str, dict], champ_rows: dict[str, dict], label: str) -> None:
    seeds = sorted(champ_rows.keys(), key=lambda s: (s.split("-")[0], int(s.split("-")[1])))
    deltas = [cand_rows[s]["margin"] - champ_rows[s]["margin"] for s in seeds]
    better = sum(d > 0 for d in deltas)
    worse = sum(d < 0 for d in deltas)
    mean_d = statistics.mean(deltas)
    se_d = statistics.stdev(deltas) / (len(deltas) ** 0.5)
    t_val = mean_d / se_d
    c_u92 = sum(champ_rows[s]["on_time"] < 0.92 for s in seeds)
    x_u92 = sum(cand_rows[s]["on_time"] < 0.92 for s in seeds)
    c_min = min(champ_rows[s]["on_time"] for s in seeds)
    x_min = min(cand_rows[s]["on_time"] for s in seeds)
    c_rk = sum(champ_rows[s]["ranked"] for s in seeds)
    x_rk = sum(cand_rows[s]["ranked"] for s in seeds)
    print(f"=== {label} (n={len(seeds)}) ===")
    print(f"  Champ mean: €{statistics.mean(champ_rows[s]['margin'] for s in seeds):,.2f} | ranked {c_rk}/{len(seeds)} | min_ot {c_min:.4f} | <92%: {c_u92}")
    print(f"  Cand  mean: €{statistics.mean(cand_rows[s]['margin'] for s in seeds):,.2f} | ranked {x_rk}/{len(seeds)} | min_ot {x_min:.4f} | <92%: {x_u92}")
    print(f"  Paired Δ  : €{mean_d:+,.2f} ± {se_d:,.2f} (t = {t_val:.2f}) | better {better} / worse {worse}")


def main() -> None:
    champ_dev = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    champ_night = {
        r["seed"]: r
        for r in (json.loads(l) for l in open("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-073207-fc-v3T-night32/results.jsonl"))
    }
    cand_dev = {
        r["seed"]: r
        for r in (json.loads(l) for l in open(sorted(pathlib.Path("runs").glob("*-cp-wild-tailbrake-dev"))[-1] / "results.jsonl"))
    }
    cand_night = {
        r["seed"]: r
        for r in (json.loads(l) for l in open(sorted(pathlib.Path("runs").glob("*-cp-wild-tailbrake-night32"))[-1] / "results.jsonl"))
    }
    paired_stats(cand_dev, champ_dev, "DEV-16 (cp-wild-tailbrake-dev)")
    paired_stats(cand_night, champ_night, "NIGHT-32 (cp-wild-tailbrake-night32)")
    paired_stats({**cand_dev, **cand_night}, {**champ_dev, **champ_night}, "COMBINED 48 WORLDS (DEV-16 + NIGHT-32)")


if __name__ == "__main__":
    main()
