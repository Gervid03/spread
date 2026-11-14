"""X-ray `limits-tas-state-dp-safe.jsonl` vs `limits-won-apply.jsonl` on `dev-12` (0 network calls)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from spread_lab.geo import Geo


def main() -> None:
    home = Path.home() / ".spread-lab"
    geo = Geo(json.loads((home / "map.json").read_text(encoding="utf-8")))
    tape = json.loads((home / "tas" / "dev-12" / "tape.json").read_text(encoding="utf-8"))
    reqs = {r["id"]: r for r in tape["requests"]}
    s30 = geo.supply(tape["roster"], 30.0)

    l1 = [json.loads(l) for l in (home / "tas" / "dev-12" / "limits-won-apply.jsonl").read_text().splitlines() if l.strip()]
    dp = [json.loads(l) for l in (home / "tas" / "dev-12" / "limits-tas-state-dp-safe.jsonl").read_text().splitlines() if l.strip()]

    for label, rows in [("Layer 1 (v5 won)", l1), ("dp-safe v1", dp)]:
        refs = [r["ref"] / 100.0 for r in rows]
        revs = [(r["lo"] or 0) / 100.0 for r in rows]
        drives = [geo.minutes(reqs[r["rid"]]["legs"][0]["pickup"]["placeId"], reqs[r["rid"]]["legs"][-1]["delivery"]["placeId"]) for r in rows]
        s30s = [s30.get(r["pickup"], 0) for r in rows]
        long_n = sum(1 for d in drives if d > 220)
        thin_n = sum(1 for s in s30s if s < 60)
        print(
            f"{label:<18}: n={len(rows)} | sum_rev=€{sum(revs):,.0f} | sum_ref=€{sum(refs):,.0f} | "
            f"mean_drive={statistics.mean(drives):.1f}m (drive>220m: {long_n}) | pickup_s30<60: {thin_n}"
        )


if __name__ == "__main__":
    main()
