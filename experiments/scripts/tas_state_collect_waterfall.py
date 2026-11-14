"""Collects all finished runs across `~/.spread-lab/tas/{dev-12,dev-01,dev-08,dev-07}/runs.jsonl`
and prints clean Markdown waterfall & ablation tables for the experiment note and STATUS.md."""
from __future__ import annotations

import json
from pathlib import Path

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")


def main() -> None:
    tas_dir = Path.home() / ".spread-lab" / "tas"
    for s in TAS_SEEDS:
        rp = tas_dir / s / "runs.jsonl"
        print(f"=== {s} ===")
        if not rp.exists():
            continue
        by_name: dict[str, dict] = {}
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                by_name[r["name"]] = r
        v5 = by_name.get("run-v5-week", {})
        l1 = by_name.get("limits-won-apply", {})
        v5_m = v5.get("margin", 0.0)
        l1_m = l1.get("margin", 0.0)
        for name, r in by_name.items():
            if "tue07" in name or "check" in name:
                continue
            m = r["margin"]
            led = r.get("ledger", {})
            print(
                f"  {name:<42} €{m:>10,.2f}  Δv5={m - v5_m:>+9,.2f}  ΔL1={m - l1_m:>+9,.2f}  "
                f"won={r['won']:>3}  OT={r['on_time']*100:>5.2f}%  forks={r['forks']:>4}  "
                f"rev=€{r.get('revenue', 0):>9,.2f}  fee=€{led.get('driver_fee', 0):>9,.2f}"
            )
        thu_p = tas_dir / s / "tas-state-thu-coldstart.json"
        if thu_p.exists():
            td = json.loads(thu_p.read_text(encoding="utf-8"))
            print("  [Thu 00:00 Cold-Start Probe]:")
            sil_m = {x["rid"]: x for x in td["silent_probe"]["probed"]}
            dec_m = {x["rid"]: x for x in td["declined_probe"]["probed"]}
            for rid, sx in sil_m.items():
                dx = dec_m.get(rid, {})
                if sx.get("lo") and dx.get("lo"):
                    print(
                        f"    {rid} {sx['dealer']}: silent={sx['lo']/sx['list']:.4f}x  "
                        f"declined4x={dx['lo']/dx['list']:.4f}x  ratio={sx['lo']/dx['lo']:.4f}"
                    )
            for bk, bv in td.get("branch", {}).items():
                print(f"    branch {bk:<22}: €{bv['margin']:>9,.2f} (Δ {bv.get('delta', 0):+,.2f}) won={bv['won']} OT={bv['on_time']*100:.2f}%")


if __name__ == "__main__":
    main()
