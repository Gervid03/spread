"""Summarizes all TAS runs across `dev-12`, `dev-01`, `dev-08`, and `dev-07` for the final waterfall & ablation tables."""
from __future__ import annotations

import json
from pathlib import Path
from spread_lab.env import lab_home

SEEDS = ["dev-12", "dev-01", "dev-08", "dev-07"]


def load_champ() -> dict[str, dict]:
    out = {}
    for line in Path("champion/results/dev-L8.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["seed"]] = r
    return out


def load_seed_runs(seed: str) -> dict[str, dict]:
    p = lab_home() / "tas" / seed / "runs.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("until") == "Wed+ 22:00":
                out[r["name"]] = r
    return out


def main() -> None:
    champ = load_champ()
    for seed in SEEDS:
        c = champ[seed]
        c_margin = c["margin"]
        c_fee = abs(c["ledger"].get("driver_fee", 0))
        c_won = c["won"]
        runs = load_seed_runs(seed)
        bp = lab_home() / "tas" / seed / "tas-routes-bound.json"
        bound = json.loads(bp.read_text(encoding="utf-8")) if bp.exists() else {}

        print(f"==================== {seed} (Bound UB: €{bound.get('lagrangian_dual_upper_bound_eur', 0):,.2f}) ====================")
        print(f"{'Run Name':<38} {'Margin':>10} {'Δ vs v5':>10} {'Won':>5} {'OnTime':>7} {'Rev€':>10} {'DrvFee€':>10} {'Fee/Car':>8} {'Forks':>6}")
        print(f"{'champion-v5':<38} {c_margin:>10.2f} {0.0:>+10.2f} {c_won:>5} {c['on_time']*100:>6.1f}% {c['revenue']:>10.2f} {-c_fee:>10.2f} {c_fee/max(1,c_won):>8.2f} {0:>6}")
        for name, r in runs.items():
            led = r.get("ledger", {})
            df = led.get("driver_fee", 0.0)
            won = r["won"]
            fpc = abs(df) / max(1, won)
            print(
                f"{name:<38} {r['margin']:>10.2f} {r['margin']-c_margin:>+10.2f} "
                f"{won:>5} {r['on_time']*100:>6.1f}% {r['revenue']:>10.2f} {df:>10.2f} {fpc:>8.2f} {r.get('forks',0):>6}"
            )


if __name__ == "__main__":
    main()
