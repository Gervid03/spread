"""Analyze the combo-lane-inbound-hours study across dev-8 screens, dev-16 ablations, and night-32 validation."""
from __future__ import annotations

import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INDEX_PATH = Path.home() / ".spread-lab" / "index.jsonl"


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["seed"]] = r
    return rows


def find_v3t_night32() -> dict[str, dict] | None:
    if not INDEX_PATH.exists():
        return None
    for line in reversed(INDEX_PATH.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("name") == "fc-v3T-night32":
            p = Path(rec["dir"]) / "results.jsonl"
            if p.exists():
                return load_jsonl(p)
    return None


def paired_summary(arm: dict[str, dict], base: dict[str, dict] | None, seeds: list[str]) -> dict:
    n = len(seeds)
    margins = [arm[s]["margin"] for s in seeds]
    ots = [arm[s]["on_time"] for s in seeds]
    wons = [arm[s]["won"] for s in seeds]
    ranked = sum(1 for s in seeds if arm[s]["ranked"])
    worst_ot_seed = min(seeds, key=lambda s: (arm[s]["on_time"], arm[s]["margin"]))
    worst_m_seed = min(seeds, key=lambda s: arm[s]["margin"])
    u92 = [s for s in seeds if arm[s]["on_time"] < 0.92]
    u91 = [s for s in seeds if arm[s]["on_time"] < 0.91]
    u90 = [s for s in seeds if arm[s]["on_time"] < 0.90]
    out: dict = {
        "n": n,
        "ranked": ranked,
        "safe": ranked == n and len(u92) == 0,
        "margin_mean": sum(margins) / n,
        "margin_min": arm[worst_m_seed]["margin"],
        "margin_min_seed": worst_m_seed,
        "ot_mean": sum(ots) / n,
        "ot_min": arm[worst_ot_seed]["on_time"],
        "ot_min_seed": worst_ot_seed,
        "won_mean": sum(wons) / n,
        "u92": u92,
        "u91": u91,
        "u90": u90,
    }
    if base is not None and all(s in base for s in seeds):
        deltas = [arm[s]["margin"] - base[s]["margin"] for s in seeds]
        ot_deltas = [arm[s]["on_time"] - base[s]["on_time"] for s in seeds]
        md = sum(deltas) / n
        if n > 1 and any(d != 0 for d in deltas):
            se = math.sqrt(sum((d - md) ** 2 for d in deltas) / (n - 1) / n)
            t = md / se if se > 0 else 0.0
        else:
            se, t = 0.0, 0.0
        out.update({
            "delta": md,
            "se": se,
            "t": t,
            "better": sum(1 for d in deltas if d > 0),
            "worse": sum(1 for d in deltas if d < 0),
            "ot_delta": sum(ot_deltas) / n,
        })
    return out


def mean_stat(rows: dict[str, dict], seeds: list[str], key: str) -> float:
    return sum(rows[s]["stats"].get(key, 0) for s in seeds) / len(seeds)


def mean_ledger(rows: dict[str, dict], seeds: list[str], key: str) -> float:
    return sum(rows[s]["ledger"].get(key, 0.0) for s in seeds) / len(seeds)


def main() -> None:
    champ_dev = load_jsonl(REPO / "champion" / "results" / "dev-L8.jsonl")
    v3t_night32 = find_v3t_night32()

    runs_dir = REPO / "runs"
    run_folders = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    print("=== RUN SUMMARIES (WORST WORLD FIRST) ===")
    loaded_runs: dict[str, tuple[Path, dict[str, dict]]] = {}
    for folder in run_folders:
        res_path = folder / "results.jsonl"
        if not res_path.exists():
            continue
        rows = load_jsonl(res_path)
        seeds = sorted(rows.keys())
        base = champ_dev if all(s.startswith("dev-") for s in seeds) else v3t_night32
        st = paired_summary(rows, base, seeds)
        loaded_runs[folder.name] = (folder, rows)
        delta_str = (
            f"Δ €{st['delta']:+8.2f} ± {st['se']:6.2f} (t={st['t']:+5.2f}, {st['better']}W/{st['worse']}L) ΔOT {st['ot_delta']*100:+.2f}%"
            if "delta" in st else "no paired base"
        )
        print(
            f"{folder.name:<38} n={st['n']:2d} | min OT {st['ot_min']*100:6.2f}% ({st['ot_min_seed']}) "
            f"<92%:{len(st['u92'])} <91%:{len(st['u91'])} | min €{st['margin_min']:8.2f} ({st['margin_min_seed']}) "
            f"| mean €{st['margin_mean']:9.2f} | mean OT {st['ot_mean']*100:5.2f}% | won {st['won_mean']:5.1f} "
            f"| {'SAFE' if st['safe'] else 'NOT_SAFE'} | {delta_str}"
        )

    if v3t_night32 is not None:
        night_seeds = [f"night-{i:02d}" for i in range(1, 33)]
        st_base = paired_summary(v3t_night32, None, night_seeds)
        print(
            f"{'fc-v3T-night32 (baseline)':<38} n=32 | min OT {st_base['ot_min']*100:6.2f}% ({st_base['ot_min_seed']}) "
            f"<92%:{len(st_base['u92'])} {st_base['u92']} <91%:{len(st_base['u91'])} {st_base['u91']} "
            f"| min €{st_base['margin_min']:8.2f} ({st_base['margin_min_seed']}) | mean €{st_base['margin_mean']:9.2f} "
            f"| mean OT {st_base['ot_mean']*100:5.2f}% | won {st_base['won_mean']:5.1f}"
        )
        for name, (_, rows) in loaded_runs.items():
            if "night32" in name:
                by_ot = sorted(night_seeds, key=lambda s: (rows[s]["on_time"], rows[s]["margin"]))
                print("Lowest 5 night32 worlds (combo-stack):")
                for s in by_ot[:5]:
                    b = v3t_night32[s]
                    r = rows[s]
                    print(
                        f"  {s}: OT {r['on_time']*100:5.2f}% (v3T {b['on_time']*100:5.2f}%, { (r['on_time']-b['on_time'])*100:+.2f}pp) "
                        f"| margin €{r['margin']:9.2f} (v3T €{b['margin']:9.2f}, Δ €{r['margin']-b['margin']:+8.2f}) "
                        f"| gated={r['stats'].get('lane_proj_gated', 0)} drop_hr={r['stats'].get('dropped_hours', 0)}"
                    )

    dev16 = [f"dev-{i:02d}" for i in range(1, 17)]
    print()
    print("=== 16-SEED DEV TELEMETRY & LEDGER BREAKDOWN ===")
    arms_16: list[tuple[str, dict[str, dict]]] = [("Champion v3T", champ_dev)]
    for name, (_, rows) in loaded_runs.items():
        if len(rows) == 16 and all(s in rows for s in dev16):
            arms_16.append((name, rows))

    stat_keys = [
        "quote_quote", "quote_floor", "quote_decline",
        "lane_quotes_low", "lane_quotes_mid", "lane_quotes_high",
        "lane_wins_low", "lane_wins_mid", "lane_wins_high",
        "lane_late_low", "lane_late_mid", "lane_late_high",
        "lane_margin_low_cents", "lane_margin_mid_cents", "lane_margin_high_cents",
        "lane_floor_unblocked", "lane_floor_lowered", "lane_proj_gated",
        "dropped_slack", "dropped_hours", "deadline_close", "gig_expired",
        "lastpickup_n", "lastpickup_err",
    ]
    ledger_keys = ["revenue", "driver_fee", "late_refund", "undelivered_penalty", "failed_visit", "release_fee", "waiting"]

    for label, rows in arms_16:
        print(f"--- {label} ---")
        for k in ledger_keys:
            print(f"  ledger.{k:<20}: €{mean_ledger(rows, dev16, k):9.2f}")
        for k in stat_keys:
            print(f"  stats.{k:<21}: {mean_stat(rows, dev16, k):9.2f}")

    print()
    print("=== PER-SEED DEV-16 COMPARISON (CHAMPION v3T vs COMBO-STACK-DEV) ===")
    stack_rows = next((rows for name, (_, rows) in loaded_runs.items() if name.endswith("combo-stack-dev")), None)
    if stack_rows is not None:
        for s in dev16:
            c = champ_dev[s]
            r = stack_rows[s]
            st = r["stats"]
            print(
                f"  {s}: champ €{c['margin']:8.2f} ({c['on_time']*100:5.2f}%) -> stack €{r['margin']:8.2f} ({r['on_time']*100:5.2f}%) "
                f"| Δ €{r['margin']-c['margin']:+8.2f} ({(r['on_time']-c['on_time'])*100:+.2f}pp) "
                f"| won {c['won']:3d}->{r['won']:3d} | unblk={st.get('lane_floor_unblocked',0):3d} "
                f"gated={st.get('lane_proj_gated',0):2d} drop_hr={st.get('dropped_hours',0):2d}"
            )


if __name__ == "__main__":
    main()
