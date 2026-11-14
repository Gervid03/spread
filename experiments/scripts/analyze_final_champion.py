"""Analyze the 96-world final-champion study (dev 16 + holdout 16 + night32 + final32) for arms v3, E, T, ET."""
from __future__ import annotations

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VAL_D_NIGHT32 = Path("/home/lab/spread-wt/val-D/runs/20261114-060206-night32/results.jsonl")


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["seed"]] = r
    return rows


def paired_stats(arm_rows: dict[str, dict], base_rows: dict[str, dict], seeds: list[str]) -> dict:
    margins = [arm_rows[s]["margin"] for s in seeds]
    deltas = [arm_rows[s]["margin"] - base_rows[s]["margin"] for s in seeds]
    ot_deltas = [arm_rows[s]["on_time"] - base_rows[s]["on_time"] for s in seeds]
    n = len(seeds)
    mean_m = sum(margins) / n
    mean_d = sum(deltas) / n
    mean_ot_d = sum(ot_deltas) / n
    if n > 1 and any(d != 0 for d in deltas):
        var = sum((d - mean_d) ** 2 for d in deltas) / (n - 1)
        se = math.sqrt(var / n)
        t = mean_d / se if se > 0 else 0.0
    else:
        se = 0.0
        t = 0.0
    better = sum(1 for d in deltas if d > 0)
    worse = sum(1 for d in deltas if d < 0)
    return {
        "n": n,
        "mean": mean_m,
        "delta": mean_d,
        "se": se,
        "t": t,
        "better": better,
        "worse": worse,
        "ot_delta": mean_ot_d,
    }


def main() -> None:
    dev_seeds = [f"dev-{i:02d}" for i in range(1, 17)]
    hold_seeds = [f"hold-{i:02d}" for i in range(1, 17)]
    night_seeds = [f"night-{i:02d}" for i in range(1, 33)]
    final_seeds = [f"final-{i:02d}" for i in range(1, 33)]
    fresh_80 = hold_seeds + night_seeds + final_seeds
    all_96 = dev_seeds + fresh_80

    arms_files = {
        "v3": {
            "dev": REPO / "champion/results/dev-L8.jsonl",
            "holdout": REPO / "champion/results/holdout-L8.jsonl",
            "night32": VAL_D_NIGHT32,
            "final32": REPO / "runs/20261114-070833-fc-v3-final32/results.jsonl",
        },
        "E (v3 + A safety)": {
            "dev": REPO / "runs/20261114-071146-fc-v3A-dev/results.jsonl",
            "holdout": REPO / "runs/20261114-071347-fc-v3A-holdout/results.jsonl",
            "night32": REPO / "runs/20261114-071547-fc-v3A-night32/results.jsonl",
            "final32": REPO / "runs/20261114-071752-fc-v3A-final32/results.jsonl",
        },
        "T (v3 + triage)": {
            "dev": REPO / "runs/20261114-071948-fc-v3T-dev/results.jsonl",
            "holdout": REPO / "runs/20261114-073047-fc-v3T-holdout/results.jsonl",
            "night32": REPO / "runs/20261114-073207-fc-v3T-night32/results.jsonl",
            "final32": REPO / "runs/20261114-073349-fc-v3T-final32/results.jsonl",
        },
        "ET (v3 + E + T)": {
            "dev": REPO / "runs/20261114-073541-fc-v3ET-dev/results.jsonl",
            "holdout": REPO / "runs/20261114-073617-fc-v3ET-holdout/results.jsonl",
            "night32": REPO / "runs/20261114-073707-fc-v3ET-night32/results.jsonl",
            "final32": REPO / "runs/20261114-073823-fc-v3ET-final32/results.jsonl",
        },
    }

    data: dict[str, dict[str, dict]] = {}
    for arm, paths in arms_files.items():
        merged = {}
        for subset, p in paths.items():
            rows = load_jsonl(p)
            merged.update(rows)
        assert len(merged) == 96, f"{arm} has {len(merged)} seeds, expected 96"
        data[arm] = merged

    v3_rows = data["v3"]

    print("=== SUBSET BREAKDOWN ===")
    for arm, rows in data.items():
        print(f"--- {arm} ---")
        for name, seeds in [
            ("dev (16)", dev_seeds),
            ("holdout (16)", hold_seeds),
            ("night32 (32)", night_seeds),
            ("final32 (32)", final_seeds),
            ("fresh80 (80)", fresh_80),
            ("all96 (96)", all_96),
        ]:
            st = paired_stats(rows, v3_rows, seeds)
            ots = [rows[s]["on_time"] for s in seeds]
            ranked = sum(1 for s in seeds if rows[s]["ranked"])
            u92 = [s for s in seeds if rows[s]["on_time"] < 0.92]
            u91 = [s for s in seeds if rows[s]["on_time"] < 0.91]
            u90 = [s for s in seeds if rows[s]["on_time"] < 0.90]
            print(
                f"  {name:<14}: mean €{st['mean']:>9,.2f} | Δ €{st['delta']:>+8,.2f} ± {st['se']:>6,.2f} (t={st['t']:>+5.2f}, {st['better']}W/{st['worse']}L) "
                f"| ranked {ranked}/{len(seeds)} | min OT {min(ots)*100:6.2f}% (mean {sum(ots)/len(ots)*100:5.2f}%) "
                f"| <92%: {len(u92)} {u92} | <91%: {len(u91)} {u91} | <90%: {len(u90)}"
            )

    print("=== LOWEST 5 WORLDS PER ARM (OVER 80 FRESH WORLDS) ===")
    for arm, rows in data.items():
        by_ot = sorted(fresh_80, key=lambda s: (rows[s]["on_time"], rows[s]["margin"]))
        lowest5 = ", ".join(f"{s} ({rows[s]['on_time']*100:.2f}%, €{rows[s]['margin']:,.0f})" for s in by_ot[:5])
        print(f"  {arm:<20}: {lowest5}")

    print("=== LOWEST 5 WORLDS PER ARM (OVER ALL 96 WORLDS) ===")
    for arm, rows in data.items():
        by_ot = sorted(all_96, key=lambda s: (rows[s]["on_time"], rows[s]["margin"]))
        lowest5 = ", ".join(f"{s} ({rows[s]['on_time']*100:.2f}%, €{rows[s]['margin']:,.0f})" for s in by_ot[:5])
        print(f"  {arm:<20}: {lowest5}")


if __name__ == "__main__":
    main()
