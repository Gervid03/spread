"""Run the remaining TAS Price Layer 2 and v7-Cycles Stacked Waterfall runs sequentially (one at a time)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = str(ROOT / "experiments" / "scripts" / "run_layer2_oracle.py")

JOBS = [
    # 1. Complete 4-world Pure Layer 2 (v5 staffing + OracleDesk selection + exact limit prices)
    ["--seed", "dev-01", "--name", "tas-price-layer2", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    ["--seed", "dev-08", "--name", "tas-price-layer2", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    ["--seed", "dev-07", "--name", "tas-price-layer2", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    # 2. Stacked TAS Layer (Champion v7 Closed Cycles + Supervisor + OracleCyclesDesk + <68% Deadband + Limit Prices)
    ["--seed", "dev-12", "--name", "tas-price-stack-v7cycles", "--stack-v7", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    ["--seed", "dev-01", "--name", "tas-price-stack-v7cycles", "--stack-v7", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    ["--seed", "dev-08", "--name", "tas-price-stack-v7cycles", "--stack-v7", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    ["--seed", "dev-07", "--name", "tas-price-stack-v7cycles", "--stack-v7", "-s", "max_next_day_drive_min=360", "--iters", "7", "--replay"],
    # 3. Ranked-edge (>=90% target) push on dev-12
    [
        "--seed", "dev-12",
        "--name", "tas-price-layer2-edge90",
        "-s", "max_next_day_drive_min=360",
        "-s", "oracle_backlog_mult=1.65",
        "-s", "oracle_min_yield=8.5",
        "-s", "oracle_load_yield_slope=13.0",
        "-s", "oracle_max_week_orders=395",
        "--iters", "7",
        "--replay",
    ],
]


def main() -> None:
    only = set(sys.argv[1:])
    for args in JOBS:
        tag = f"{args[1]}:{args[3]}"
        if only and tag not in only and args[3] not in only:
            continue
        print(f"================ STARTING {tag} ================", flush=True)
        cmd = [sys.executable, "-u", SCRIPT, *args]
        rc = subprocess.call(cmd, cwd=str(ROOT))
        print(f"================ FINISHED {tag} (rc={rc}) ================", flush=True)
        if rc != 0:
            raise SystemExit(rc)


if __name__ == "__main__":
    main()
