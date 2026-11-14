"""Read-only status check of ~/.spread-lab/tas/ and champion v5 world IDs on the 4 TAS seeds."""
from __future__ import annotations

import json
import pathlib
import subprocess

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")


def main() -> None:
    tas_dir = pathlib.Path.home() / ".spread-lab" / "tas"
    status_file = tas_dir / "STATUS.md"
    print("=== STATUS.md ===")
    if status_file.exists():
        print(status_file.read_text(encoding="utf-8"))

    print("=== TAS FILES ===")
    if tas_dir.exists():
        for p in sorted(tas_dir.rglob("*")):
            if p.is_file():
                print(f"  {p.relative_to(tas_dir)}  ({p.stat().st_size:,} bytes)")

    print("=== ACTIVE WORLDS ===")
    worlds_dir = pathlib.Path.home() / ".spread-lab" / "worlds"
    if worlds_dir.exists():
        for p in sorted(worlds_dir.glob("*.json")):
            print(" ", p.name, p.read_text(encoding="utf-8").strip())

    print("=== LOCAL GIT BRANCHES ===")
    out = subprocess.check_output(["git", "branch", "-v"], text=True)
    for line in out.splitlines():
        if "tas" in line or "main" in line:
            print(" ", line)

    print("=== CHAMPION V5 WORLD IDS ===")
    for line in pathlib.Path("champion/results/dev-L8.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["seed"] in TAS_SEEDS:
            print(
                f"  {r['seed']}: world={r.get('world_id')} margin=€{r['margin']:,.2f} "
                f"rev=€{r['revenue']:,.2f} won={r['won']} on_time={r['on_time']:.4f}"
            )


if __name__ == "__main__":
    main()
