"""Append tas-state Phase 1 & 2 findings to ~/.spread-lab/tas/STATUS.md and inspect runs.jsonl across all 4 TAS seeds."""
from __future__ import annotations

import json
from spread_lab.env import lab_home

TAS_SEEDS = ("dev-12", "dev-01", "dev-08", "dev-07")

UPDATE_BLOCK = """
---

## Sat 14 Nov 13:37 Helsinki (`tas-state`, branch `exp/gemini-tas-state`): Exact Hidden-State Equations Measured!
- **Reveals of v5 cached** (`~/.spread-lab/tas/<seed>/reveal-v5.json`, 0 slots) for all 4 TAS worlds (`dev-12`, `dev-01`, `dev-08`, `dev-07`).
- **Controlled fork probes on `dev-12`** (`tas-state-mechanics-probe.json`, `tas-state-mechanics-probe2.json`):
  1. **Lose-close (`2.3x`) vs Decline (`4.0x`)**: `0 cents` max diff across all probed Tuesday limits. Competitor & dealers only see `won` vs `lost`.
  2. **Competitor Morning Reaction Law (with `trust=0` isolated)**:
     - **Small-dealer immunity**: Dealers with `< 10` recent requests (`D09` at 8/9, `D10` at 7/7) NEVER trigger competitor reaction (`ratio = 1.0000` even at 100% win share!).
     - **Exact deadband `[30%, 70%)` on busy dealers (`D01`, `D02`, `D03`)**:
       - Win share `< 30%` (tested `0%`, `23.9%`): competitor **RAISES** next morning by **+1 step (`+3.5%` to `+4.3%`)**!
       - Win share `30% .. 69%` (tested `30.4%`, `34.8%`, `39.1%`, `47.8%`, `52.2%`, `58.7%`, `67.4%`): **0 step (identical to the cent across the entire `[30%, 69%]` band!)**!
       - Win share `>= 70%` (tested `89.1%`, `93.8%`): competitor **CUTS** next morning by **-1 step (`-3.4%` to `-4.3%`)**!
     - **Multi-day accumulation**: 2 days (`0%` vs `100%`) = `0.848` (`~18%` swing); 4 days (`Mon..Thu -> Fri`) = `0.789` (`~27%` swing).
     - **Friday endgame**: Friday is the last request day, so Friday `100%` win share incurs **zero** future competitor penalty!
     - **Stacking tip for `tas-routes`**: Keeping `D01, D02, D03` at `< 30%` on Monday (`<=13/46` D01, `<=9/32` D02, `<=8/27` D03) earns `+4%` on Tue..Fri, and staying `< 70%` Tue..Thu avoids ALL competitor price cuts while nearly doubling volume!
  3. **Trust & Late-Delivery Timing**:
     - 1 on-time delivery raises next-day limits by `+1.1%..+1.5%` (`+1%` trust + satisfaction); 7 on-time Monday `same_day` cars on `D01` (`17%` Mon share) gave **`+9.7%` over `+1`-step Tuesday (`+14.0%` over normal Tuesday!)**.
     - An order past its deadline does **not** halve trust or drop satisfaction until `deliveredAt` (or world end); in `v5` on `dev-12`, a late `D01` car halved `D01` trust `25 -> 12` before Friday!
- **Event Calendar across the 4 TAS worlds**:
  - `dev-12`: Outage **Tue** (Lahti/Hyvinkää/Porvoo 80km, `~1.8x`), Snow **Wed** (Oulu/Kokkola/Ylivieska), Price War **Fri** (`~1.16x`).
  - `dev-01`: Snow **Tue** (East), Outage **Tue** (Helsinki 80km, `70%` v5 win vs `0%` rest!), Price War + Flu **Thu** (viewers `-52%`), Snow **Fri** (North).
  - `dev-08`: Snow **Tue** (North), Price War **Tue** (`1.23x`), Outage **Wed/Thu** (Capital).
  - `dev-07`: Snow **Tue** (East), Price War + Flu **Tue** (morn viewers `-47%`), Snow **Thu** (Central/Tampere/Lahti), Outage **Fri** (`1.89x`).
"""


def main() -> None:
    tas_dir = lab_home() / "tas"
    status_path = tas_dir / "STATUS.md"
    cur = status_path.read_text(encoding="utf-8") if status_path.exists() else ""
    if "Exact Hidden-State Equations Measured" not in cur:
        status_path.write_text(cur.rstrip() + chr(10) + chr(10) + UPDATE_BLOCK.strip() + chr(10), encoding="utf-8")
        print("Appended tas-state update to STATUS.md")

    for s in TAS_SEEDS:
        rp = tas_dir / s / "runs.jsonl"
        if rp.exists():
            print(f"=== {s}/runs.jsonl ===")
            for line in rp.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                print(f"  {r['name']:<26} margin=€{r['margin']:>10,.2f} won={r['won']:>3} on_time={r['on_time']:.2%} forks={r['forks']}")
        lall = tas_dir / s / "limits-all.jsonl"
        if lall.exists():
            print(f"  {s}/limits-all.jsonl: {lall.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
