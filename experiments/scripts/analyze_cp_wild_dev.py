"""Analyze paired per-seed deltas and counters of cp-wild dev run vs Champion."""
from __future__ import annotations

import json
import pathlib
import statistics


def main() -> None:
    champ = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    run_dir = sorted(pathlib.Path("runs").glob("*-cp-wild-ret35-300-futsd50-dev"))[-1]
    cand = {r["seed"]: r for r in (json.loads(l) for l in open(run_dir / "results.jsonl"))}

    print(f"Run: {run_dir}")
    print("SEED     CHAMP_M   CAND_M    DELTA   C_WON -> WON   C_OT -> OT    Q_RET W_RET  Q_FSD W_FSD  M_FSD€ L_FSD  M_EXT€ L_EXT")
    deltas = []
    tot_s = {k: 0 for k in ("quoted_return_hub", "won_return_hub", "quoted_fut_sd", "won_fut_sd", "margin_fut_sd_cents", "late_fut_sd", "margin_ext_ring_cents", "late_ext_ring")}
    tot_c_ext_m = 0
    for seed in sorted(champ.keys(), key=lambda s: int(s.split("-")[1])):
        c, x = champ[seed], cand[seed]
        dm = x["margin"] - c["margin"]
        deltas.append(dm)
        xs = x["stats"]
        cs = c["stats"]
        for k in tot_s:
            tot_s[k] += xs.get(k, 0)
        tot_c_ext_m += cs.get("margin_ext_ring_cents", 0)
        print(
            f"{seed:7s} {c['margin']:8.1f} {x['margin']:8.1f} {dm:+8.1f}   "
            f"{c['won']:3d} -> {x['won']:3d}   {c['on_time']:.3f}->{x['on_time']:.3f}   "
            f"{xs.get('quoted_return_hub',0):4d}  {xs.get('won_return_hub',0):4d}   "
            f"{xs.get('quoted_fut_sd',0):4d}  {xs.get('won_fut_sd',0):4d}   "
            f"{xs.get('margin_fut_sd_cents',0)/100:6.0f}    {xs.get('late_fut_sd',0):2d}  "
            f"{xs.get('margin_ext_ring_cents',0)/100:6.0f}    {xs.get('late_ext_ring',0):2d}"
        )
    mean_d = statistics.mean(deltas)
    se_d = statistics.stdev(deltas) / (len(deltas) ** 0.5)
    print("")
    print(f"Paired Δmargin: €{mean_d:+.2f} ± {se_d:.2f} (t = {mean_d/se_d:.2f})")
    print("Totals across 16 worlds (and /wk):")
    for k, v in tot_s.items():
        if k.endswith("_cents"):
            print(f"  {k:24s}: €{v/100:8.1f} (€{v/1600:6.1f}/wk)")
        else:
            print(f"  {k:24s}: {v:8d} ({v/16:6.2f}/wk)")
    print(f"  champ margin_ext_ring   : €{tot_c_ext_m/100:8.1f} (€{tot_c_ext_m/1600:6.1f}/wk)")


if __name__ == "__main__":
    main()
