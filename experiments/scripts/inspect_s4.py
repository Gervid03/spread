"""Compare s1, s2, s3, s4 on dev-01..dev-04 to pinpoint why dev-02 dropped in s4."""
from __future__ import annotations

import json
from pathlib import Path


def load_run(p: str) -> dict[str, dict]:
    return {json.loads(l)["seed"]: json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()}


def main() -> None:
    noop = load_run("runs/20261114-142131-r4-volume-noop/results.jsonl")
    s1 = load_run("runs/20261114-142848-r4v-s1-tours/results.jsonl")
    s4 = load_run("runs/20261114-150134-r4v-s4-corridor/results.jsonl")
    for seed in ["dev-01", "dev-02", "dev-03", "dev-04"]:
        a, b1, b4 = noop[seed], s1[seed], s4[seed]
        print(f"=== {seed}: noop={a['margin']:.0f} | s1={b1['margin']:.0f} ({b1['margin']-a['margin']:+.0f}) | s4={b4['margin']:.0f} ({b4['margin']-a['margin']:+.0f}) ===")
        print(f"  noop: won={a['won']} rev={a['ledger'].get('revenue',0):.0f} fee={a['ledger'].get('driver_fee',0):.0f} late={a['ledger'].get('late_refund',0):.0f} pen={a['ledger'].get('undelivered_penalty',0):.0f} fail={a['ledger'].get('failed_visit',0):.0f}")
        print(f"  s4  : won={b4['won']} rev={b4['ledger'].get('revenue',0):.0f} fee={b4['ledger'].get('driver_fee',0):.0f} late={b4['ledger'].get('late_refund',0):.0f} pen={b4['ledger'].get('undelivered_penalty',0):.0f} fail={b4['ledger'].get('failed_visit',0):.0f}")
        print("  s4 r4v:", {k: v for k, v in sorted(b4["stats"].items()) if k.startswith("r4v_") or k in ("deadline_close", "visit_failed", "refused_post")})


if __name__ == "__main__":
    main()
