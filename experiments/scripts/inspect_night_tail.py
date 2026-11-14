"""Inspect night-11 and night-15 in base vs tail-fix (0 slots)."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    base = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-173231-r4v-v7-night16-base/results.jsonl").read_text().splitlines() if l.strip()}
    fix = {json.loads(l)["seed"]: json.loads(l) for l in Path("runs/20261114-173941-r4v-v7-tail-fix/results.jsonl").read_text().splitlines() if l.strip()}
    for s in ["night-11", "night-15"]:
        b, f = base[s], fix[s]
        print(f"=== {s}: base={b['margin']:.2f}({b['won']}, {b['on_time']*100:.2f}%) -> fix={f['margin']:.2f}({f['won']}, {f['on_time']*100:.2f}%) ===")
        print("  base ledger:", b["ledger"])
        print("  fix  ledger:", f["ledger"])
        keys = ["won_return_hub", "won_ext_ring", "r4v_ret_hub_guarded", "r4v_tradein_quoted", "r4v_tradein_won", "lead_car_booked", "lead_car_paired", "deadline_close", "gig_dropped", "late_le_2h", "late_le_24h", "late_more", "late_ring", "late_ext_ring", "sup_d1_regime", "sup_d2_regime", "sup_d3_regime", "sup_d4_regime"]
        for k in keys:
            if b["stats"].get(k, 0) != f["stats"].get(k, 0):
                print(f"    {k:<22}: {b['stats'].get(k,0)} -> {f['stats'].get(k,0)}")


if __name__ == "__main__":
    main()
