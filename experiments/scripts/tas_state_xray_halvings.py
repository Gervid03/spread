"""Inspect trust halvings, late orders, and dealer revenue on dev-12, dev-01, dev-08, dev-07 from cached files."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from spread_lab.env import lab_home

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")


def main() -> None:
    tas_dir = lab_home() / "tas"
    for s in TAS_SEEDS:
        print(f"=== {s} ===")
        lwa = tas_dir / s / "limits-won-apply.jsonl"
        rev_p = tas_dir / s / "reveal-v5.json"
        tape_p = tas_dir / s / "tape.json"
        tape = json.loads(tape_p.read_text(encoding="utf-8"))
        reqs = {r["id"]: r for r in tape["requests"]}
        rev = json.loads(rev_p.read_text(encoding="utf-8"))

        # Check late orders in reveal-v5
        late_orders = []
        dlr_won = Counter()
        for rr in rev.get("requests", []):
            rid = rr["request"]["id"]
            dlr = rr["request"]["dealerId"]
            if rr.get("outcome") == "won":
                dlr_won[dlr] += 1
        for o in rev.get("orders", []):
            oid = o.get("orderId") or o.get("id") or o.get("order", {}).get("id")
            inner = o.get("order", o)
            if not oid or oid not in reqs:
                continue
            dlr = reqs[oid]["dealerId"]
            dels = [x for x in inner.get("deliveredAt", []) if x is not None]
            dl = inner.get("deadline", 0)
            if len(dels) < len(inner.get("legs", [1])) or (dels and max(dels) > dl):
                late_orders.append((oid, dlr, inner.get("option", "?"), dl, dels, inner.get("priceCents", 0) / 100.0))
        print(f"  v5 won={sum(dlr_won.values())}, late={len(late_orders)}:")
        for lo in late_orders:
            after_won = sum(
                1
                for rr in rev.get("requests", [])
                if rr.get("outcome") == "won"
                and rr["request"]["dealerId"] == lo[1]
                and rr["request"]["arrivedAt"] > (max(lo[4]) if lo[4] else 99999)
            )
            print(f"    {lo[0]} dlr={lo[1]} opt={lo[2]:<10} dl={lo[3]} deliv={lo[4]} price=€{lo[5]:.1f} | won_after_deliv={after_won}")

        if lwa.exists():
            rows = [json.loads(l) for l in lwa.read_text(encoding="utf-8").splitlines() if l.strip()]
            prev = {}
            drops = []
            for r in rows:
                d = r["dealer"]
                t = r["trust"]
                if d in prev and t < prev[d]:
                    drops.append((r["day"], r["at"], d, prev[d], t, r["rid"]))
                prev[d] = t
            print(f"  limits-won-apply rows={len(rows)}, trust drops={drops}")


if __name__ == "__main__":
    main()
