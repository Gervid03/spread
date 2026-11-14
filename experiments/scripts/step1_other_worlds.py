"""Run Step 1 (tape, v5 check, limits-won-apply, book replay) on dev-01, dev-08, dev-07."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tas  # noqa: E402
from spread_lab.env import load_dotenv  # noqa: E402

SEEDS = ["dev-01", "dev-08", "dev-07"]


def ns(**kwargs) -> argparse.Namespace:
    defaults = dict(
        seed="",
        force=False,
        mode="won",
        apply=False,
        lo=0.7,
        hi=2.6,
        iters=9,
        book=None,
        until=None,
        set=[],
        policy=None,
        name=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def main() -> None:
    load_dotenv()
    for seed in SEEDS:
        print(f"================ {seed} ================", flush=True)
        tas.cmd_tape(ns(seed=seed, force=False))
        tas.cmd_run(ns(seed=seed, name="v5-week"))
        tas.cmd_limits(ns(seed=seed, mode="won", apply=True))
        book_path = str(tas.home(seed) / "book-won-apply.json")
        tas.cmd_run(ns(seed=seed, book=book_path))

        rows = [json.loads(line) for line in (tas.home(seed) / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        by_name = {r["name"]: r for r in rows}
        v5 = by_name["run-v5-week"]
        lim = by_name["limits-won-apply"]
        rep = by_name["run-book-won-apply"]
        print(f"[{seed}] v5={v5['margin']:.2f} -> L1={lim['margin']:.2f} (Δ={lim['margin'] - v5['margin']:+.2f}), replay={rep['margin']:.2f}")
        print(f"[{seed}] v5 ledger : {v5['ledger']}")
        print(f"[{seed}] L1 ledger : {lim['ledger']}")
        print(f"[{seed}] bounds    : {lim['limits']['bounds']}, broken={lim['limits']['repriced_but_lost']}, mismatch={lim['limits']['preview_differs_from_main_line']}")
        assert round(lim["margin"], 2) == round(rep["margin"], 2), f"Book replay mismatch on {seed}!"


if __name__ == "__main__":
    main()
