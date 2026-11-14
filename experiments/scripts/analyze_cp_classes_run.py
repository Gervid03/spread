"""Analyze seed-by-seed and class-by-class differences between a cp-classes run and champion."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from scout_cp_classes import drv_cls, hav, rd, sup_cls


def load_champ_class_stats(reveals_root: Path) -> dict[str, tuple[int, dict[str, int], dict[str, float]]]:
    out = {}
    if not reveals_root.exists():
        return out
    for folder in sorted(reveals_root.iterdir()):
        if not (folder / "requests.csv").exists():
            continue
        seed = folder.name[:6]
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in rd(folder, "places")}
        line = {(a, b): hav(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in rd(folder, "roads")}
        drivers = rd(folder, "drivers")
        homes = collections.Counter(x["homePlaceId"] for x in drivers)
        supply = {p: sum(n for h, n in homes.items() if line[(p, h)] <= 30.0) for p in places}
        legs_by_req = collections.defaultdict(list)
        for l in rd(folder, "legs"):
            legs_by_req[l["requestId"]].append(l)
        for rid in legs_by_req:
            legs_by_req[rid].sort(key=lambda x: int(x["leg"]))
        won = collections.Counter()
        mrg_cents = collections.Counter()
        req_cls = {}
        for r in rd(folder, "requests"):
            rid = r["id"]
            rlegs = legs_by_req[rid]
            drive = sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in rlegs)
            if len(rlegs) == 2:
                drive += roads[(rlegs[0]["delivery.placeId"], rlegs[1]["pickup.placeId"])][1]
            c = f"{sup_cls(supply[rlegs[0]['pickup.placeId']])}_{drv_cls(drive)}"
            req_cls[rid] = c
            if r["outcome"] == "won":
                won[c] += 1
        for e in rd(folder, "events"):
            if e["kind"] == "ledger" and e.get("line.orderId") in req_cls:
                mrg_cents[req_cls[e["line.orderId"]]] += int(e["line.cents"])
        out[seed] = (len(drivers), dict(won), {k: v / 100.0 for k, v in mrg_cents.items()})
    return out


def main() -> None:
    run_dir = Path(sys.argv[1])
    champ_rows = {
        r["seed"]: r
        for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }
    run_rows = {
        r["seed"]: r
        for line in (run_dir / "results.jsonl").read_text().splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }
    classes = [f"{sc}_{dc}" for sc in ("hub", "mid", "thin") for dc in ("short", "mid", "long")]
    champ_cls = load_champ_class_stats(Path("runs/reveals/dev16"))

    print(f"{'Seed':<8} {'Drv':>4} {'ChMrg':>7} {'RnMrg':>7} {'ΔMrg':>7} {'ChWon':>5} {'RnWon':>5} {'ChOT':>6} {'RnOT':>6} {'ChWarn':>6} {'RnWarn':>6}")
    print("-" * 82)
    for s in sorted(run_rows):
        c, r = champ_rows[s], run_rows[s]
        ndrv = champ_cls.get(s, (0, {}, {}))[0]
        dm = r["margin"] - c["margin"]
        print(
            f"{s:<8} {ndrv:4d} {c['margin']:7.0f} {r['margin']:7.0f} {dm:+7.0f} "
            f"{c['won']:5d} {r['won']:5d} {c['on_time']*100:5.1f}% {r['on_time']*100:5.1f}% "
            f"{c['stats'].get('deadline_close',0):6d} {r['stats'].get('deadline_close',0):6d}"
        )

    if champ_cls:
        print()
        print("--- Paired class deltas across all 16 dev worlds (mean / wk) ---")
        print(f"{'Class':<12} {'ChWon':>7} {'RnWon':>7} {'ΔWon':>7} {'ChMrg':>8} {'RnMrg':>8} {'ΔMrg':>8} {'Ch€/o':>7} {'Rn€/o':>7}")
        for cls in classes:
            cw = sum(champ_cls[s][1].get(cls, 0) for s in run_rows) / len(run_rows)
            rw = sum(r["stats"].get(f"cls_won_{cls}", 0) for r in run_rows.values()) / len(run_rows)
            cm = sum(champ_cls[s][2].get(cls, 0.0) for s in run_rows) / len(run_rows)
            rm = sum(r["stats"].get(f"cls_mrg_{cls}_cents", 0) for r in run_rows.values()) / 100 / len(run_rows)
            print(
                f"{cls:<12} {cw:7.1f} {rw:7.1f} {rw-cw:+7.1f} {cm:8.1f} {rm:8.1f} {rm-cm:+8.1f} "
                f"{cm/max(1e-6,cw):7.1f} {rm/max(1e-6,rw):7.1f}"
            )

        for s in ["dev-14", "dev-05", "dev-09", "dev-11", "dev-07"]:
            if s not in champ_cls or s not in run_rows:
                continue
            ndrv, cwon, cmrg = champ_cls[s]
            r = run_rows[s]
            print()
            print(f"=== {s} (drivers={ndrv}, ΔMrg={r['margin']-champ_rows[s]['margin']:+.0f}) ===")
            for cls in classes:
                cw, cm = cwon.get(cls, 0), cmrg.get(cls, 0.0)
                rw = r["stats"].get(f"cls_won_{cls}", 0)
                rm = r["stats"].get(f"cls_mrg_{cls}_cents", 0) / 100.0
                if cw or rw:
                    print(f"  {cls:<11} Ch:{cw:3d}w €{cm:6.0f} | Rn:{rw:3d}w €{rm:6.0f} | ΔW={rw-cw:+3d} Δ€={rm-cm:+6.0f}")


if __name__ == "__main__":
    main()
