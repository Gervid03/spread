"""X-ray why Champion v5 won only 9/136 of D02 on dev-01 and only 18 Friday cars on dev-12."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from spread_lab.geo import Geo


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))

    for seed, target_dlr in [("dev-01", "D02"), ("dev-12", "D02"), ("dev-12", "D01")]:
        tape = json.loads((home / "tas" / seed / "tape.json").read_text(encoding="utf-8"))
        rev = json.loads((home / "tas" / seed / "reveal-v5.json").read_text(encoding="utf-8"))
        s30 = geo.supply(tape["roster"], 30.0)
        s55 = geo.supply(tape["roster"], 55.0)
        s70 = geo.supply(tape["roster"], 70.0)

        outcomes = Counter()
        pickups = Counter()
        quote_ratios = []
        comp_ratios = []
        for rr in rev["requests"]:
            req = rr["request"]
            if req["dealerId"] != target_dlr:
                continue
            out = rr.get("outcome")
            p0 = req["legs"][0]["pickup"]["placeId"]
            d0 = req["legs"][-1]["delivery"]["placeId"]
            sup_tier = "hub>=100" if s30.get(p0, 0) >= 100 else ("s55>=30" if s55.get(p0, 0) >= 30 else ("s70>=40" if s70.get(p0, 0) >= 40 else ("ret_hub" if s30.get(d0, 0) >= 180 else "remote")))
            q = rr.get("quote") or {}
            prices = q.get("prices", {})
            first_opt = req["options"][0]
            declined = bool(prices and next(iter(prices.values())) >= 3.5 * first_opt["listPriceCents"])
            outcomes[(out, "declined" if declined else "quoted", sup_tier)] += 1
            pickups[p0] += 1
            if not declined and prices:
                k = next(iter(prices))
                lp = next(o["listPriceCents"] for o in req["options"] if o["kind"] == k)
                quote_ratios.append(prices[k] / lp)
                if rr.get("competitorPriceCents"):
                    comp_ratios.append(rr["competitorPriceCents"] / lp)

        print(f"=== {seed} {target_dlr} ===")
        for k, v in outcomes.most_common():
            print(f"  {k}: {v}")
        print(f"  top pickups: {pickups.most_common(5)}")
        if quote_ratios:
            quote_ratios.sort()
            print(f"  quoted n={len(quote_ratios)}, median our quote={quote_ratios[len(quote_ratios)//2]:.3f}x")
        if comp_ratios:
            comp_ratios.sort()
            print(f"  comp n={len(comp_ratios)}, median comp={comp_ratios[len(comp_ratios)//2]:.3f}x")


if __name__ == "__main__":
    main()
