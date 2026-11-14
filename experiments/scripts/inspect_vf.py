"""Check visit_failed_* and daily price_list_sum_d* across noop, s2, s3, s4 on dev-01 and dev-02."""
from __future__ import annotations

import json
from pathlib import Path


def load_run(p: str) -> dict[str, dict]:
    return {json.loads(l)["seed"]: json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()}


def main() -> None:
    noop = load_run("runs/20261114-142131-r4-volume-noop/results.jsonl")
    s2 = {**load_run("runs/20261114-143338-r4v-s2-full/results.jsonl"), **load_run("runs/20261114-144014-r4v-s2-full-b/results.jsonl")}
    s3 = load_run("runs/20261114-144249-r4v-s3-clean/results.jsonl") if Path("runs/20261114-144249-r4v-s3-clean/results.jsonl").exists() else {}
    import glob
    for p in glob.glob("runs/*r4v-s3-clean*/results.jsonl"):
        s3.update(load_run(p))
    s4 = load_run("runs/20261114-150134-r4v-s4-corridor/results.jsonl")

    for seed in ["dev-01", "dev-02", "dev-03", "dev-04"]:
        print(f"=== {seed} ===")
        for label, d in [("noop", noop), ("s2", s2), ("s3", s3), ("s4", s4)]:
            if seed not in d:
                continue
            r = d[seed]
            st = r["stats"]
            vf = {k: v for k, v in st.items() if "visit_failed" in k or "late_" in k}
            dmult = [round(st.get(f"price_list_sum_d{i}", 0) / max(1, st.get(f"price_list_count_d{i}", 1)), 3) for i in range(5)]
            print(
                f"  {label:<4}: margin={r['margin']:8.2f} won={r['won']:3d} (sd={st.get('won_same_day',0)},nd={st.get('won_next_day',0)},w3={st.get('won_within_3_days',0)}) "
                f"dmult={dmult} trust_d4={st.get('top_dealer_trust_d4',0)} vf={vf}"
            )


if __name__ == "__main__":
    main()
