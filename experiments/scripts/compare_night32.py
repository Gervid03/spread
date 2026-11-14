<<<<<<< HEAD
import json
import sys
from pathlib import Path
from spread_lab.lab import compare, load_results, summarize


def main() -> None:
    cand_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("runs/20261114-102117-cp-margin-indisc07-fixslot-night32")
    champ_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/home/lab/spread-wt/n14-06591-final-champion/runs/20261114-073207-fc-v3T-night32")
    cand = load_results(cand_dir)
    champ = load_results(champ_dir)
    print("Champion summary:", json.dumps(summarize(champ), indent=2))
    print("Candidate summary:", json.dumps(summarize(cand), indent=2))
    print("Paired comparison:", json.dumps(compare(cand, champ), indent=2))
    print("Worlds under 92%: candidate=", sum(1 for r in cand if r["on_time"] < 0.92), "champion=", sum(1 for r in champ if r["on_time"] < 0.92))
||||||| f3acbfb
=======
"""Paired comparison of cp-volume runs against Champion v3T on dev-16 and night-32."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def load_map(path: Path) -> dict[str, dict]:
    if path.is_dir():
        path = path / "results.jsonl"
    return {r["seed"]: r for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and (r := json.loads(line))}


def find_index_run(name: str) -> dict[str, dict]:
    idx = Path.home() / ".spread-lab" / "index.jsonl"
    for line in reversed(idx.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            rec = json.loads(line)
            if rec.get("name") == name:
                return load_jsonl_if_exists(Path(rec["dir"]))
    raise FileNotFoundError(name)


def load_jsonl_if_exists(d: Path) -> dict[str, dict]:
    return load_map(d / "results.jsonl")


def main() -> None:
    base_n32 = find_index_run("fc-v3T-night32")
    cand_n32 = load_map(Path(sys.argv[1]))
    seeds = sorted(cand_n32)
    diffs = [cand_n32[s]["margin"] - base_n32[s]["margin"] for s in seeds]
    ot_diffs = [cand_n32[s]["on_time"] - base_n32[s]["on_time"] for s in seeds]
    n = len(diffs)
    mean_d = sum(diffs) / n
    var_d = sum((x - mean_d) ** 2 for x in diffs) / (n - 1)
    se_d = math.sqrt(var_d / n)
    t_val = mean_d / se_d
    better = sum(1 for x in diffs if x > 1e-6)
    worse = sum(1 for x in diffs if x < -1e-6)
    u92_b = sum(1 for s in seeds if base_n32[s]["on_time"] < 0.92)
    u92_c = sum(1 for s in seeds if cand_n32[s]["on_time"] < 0.92)
    min_ot_b = min(base_n32[s]["on_time"] for s in seeds)
    min_ot_c = min(cand_n32[s]["on_time"] for s in seeds)
    print(f"NIGHT-32 PAIRED: Δmargin = €{mean_d:+.2f} ± {se_d:.2f} (t = {t_val:.2f}), better {better} / worse {worse}")
    print(f"  mean margin: {sum(base_n32[s]['margin'] for s in seeds)/n:.2f} -> {sum(cand_n32[s]['margin'] for s in seeds)/n:.2f}")
    print(f"  mean on-time: {sum(base_n32[s]['on_time'] for s in seeds)/n:.4%} -> {sum(cand_n32[s]['on_time'] for s in seeds)/n:.4%} ({sum(ot_diffs)/n:+.4%})")
    print(f"  min on-time: {min_ot_b:.4%} -> {min_ot_c:.4%} | under 92%: {u92_b} -> {u92_c}")
    for s in seeds:
        if base_n32[s]["on_time"] < 0.93 or cand_n32[s]["on_time"] < 0.93:
            st = cand_n32[s]["stats"]
            print(f"  TAIL {s}: ot {base_n32[s]['on_time']:.4f}->{cand_n32[s]['on_time']:.4f}, m {base_n32[s]['margin']:.0f}->{cand_n32[s]['margin']:.0f}, won {base_n32[s]['won']}->{cand_n32[s]['won']}, ti={st.get('won_trade_in',0)}({st.get('late_trade_in',0)}L), ext={st.get('won_ext_ring',0)}({st.get('late_ext_ring',0)}L), pair={st.get('lead_car_booked',0)}")
>>>>>>> origin/exp/gemini-cp-volume


if __name__ == "__main__":
    main()
