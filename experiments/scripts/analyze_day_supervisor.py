"""Analyze evening supervisor runs (rule vs llm vs champion) and compare evening dial choices."""
from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

DAYS = ("Mon", "Tue", "Wed", "Thu")


def load_results(path: Path) -> dict[str, dict]:
    return {
        r["seed"]: r
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for r in [json.loads(line)]
    }


def paired_stats(cand: dict[str, dict], base: dict[str, dict], seeds: list[str]) -> dict:
    diffs = [cand[s]["margin"] - base[s]["margin"] for s in seeds]
    ot_diffs = [cand[s]["on_time"] - base[s]["on_time"] for s in seeds]
    n = len(diffs)
    mean_d = st.mean(diffs)
    se_d = st.stdev(diffs) / math.sqrt(n) if n > 1 else 0.0
    t_val = mean_d / se_d if se_d > 0 else 0.0
    ots = [cand[s]["on_time"] for s in seeds]
    margins = [cand[s]["margin"] for s in seeds]
    return {
        "n": n,
        "margin_mean": st.mean(margins),
        "margin_median": st.median(margins),
        "margin_min": min(margins),
        "on_time_min": min(ots),
        "on_time_mean": st.mean(ots),
        "under_92": sum(1 for x in ots if x < 0.92),
        "ranked": sum(1 for s in seeds if cand[s]["ranked"]),
        "won_mean": st.mean(cand[s]["won"] for s in seeds),
        "delta_margin": mean_d,
        "se_margin": se_d,
        "t_stat": t_val,
        "better": sum(1 for d in diffs if d > 1e-6),
        "worse": sum(1 for d in diffs if d < -1e-6),
        "delta_ot_pp": st.mean(ot_diffs) * 100.0,
        "worst_ot_seed": min(seeds, key=lambda s: cand[s]["on_time"]),
        "worst_margin_seed": min(seeds, key=lambda s: cand[s]["margin"]),
    }


def classify_move(prev_dials: tuple[float, int, float], new_dials: tuple[float, int, float]) -> str:
    if new_dials == prev_dials:
        return "keep"
    if new_dials[0] > prev_dials[0] or new_dials[1] < prev_dials[1] or new_dials[2] < prev_dials[2]:
        return "loosen"
    return "tighten"


def main() -> None:
    champ = load_results(Path("champion/results/dev-L8.jsonl"))
    runs = {
        "noop-smoke": Path("runs/20261114-084634-day-supervisor-noop"),
        "rule-v1-8dev": Path("runs/20261114-084806-day-supervisor-rule-8dev"),
        "rule-v2-8dev": Path("runs/20261114-085119-day-supervisor-rule-v2-8dev"),
        "llm-8dev": Path("runs/20261114-085341-day-supervisor-llm-8dev"),
        "llm-16dev": Path("runs/20261114-085603-day-supervisor-llm-dev"),
    }

    print("=== RUN SUMMARIES & PAIRED VS CHAMPION ===")
    for label, folder in runs.items():
        if not folder.exists():
            continue
        res = load_results(folder / "results.jsonl")
        seeds = sorted(res.keys())
        ps = paired_stats(res, champ, seeds)
        base_ps = paired_stats(champ, champ, seeds)
        print(
            f"{label:14s} (n={ps['n']:2d}): mean=€{ps['margin_mean']:8.2f} med=€{ps['margin_median']:8.2f} "
            f"min=€{ps['margin_min']:7.2f} ({ps['worst_margin_seed']}) | "
            f"OT min={ps['on_time_min']*100:5.2f}% ({ps['worst_ot_seed']}, champ min={base_ps['on_time_min']*100:5.2f}%) "
            f"mean={ps['on_time_mean']*100:5.2f}% <92%={ps['under_92']} | "
            f"won={ps['won_mean']:5.1f} | Δ=€{ps['delta_margin']:+7.2f} ± {ps['se_margin']:6.2f} (t={ps['t_stat']:+.2f}) "
            f"W/L={ps['better']}/{ps['worse']} ΔOT={ps['delta_ot_pp']:+.2f}pp"
        )

    r2 = load_results(runs["rule-v2-8dev"] / "results.jsonl")
    l8 = load_results(runs["llm-8dev"] / "results.jsonl")
    ps_l_vs_r = paired_stats(l8, r2, sorted(l8.keys()))
    print(
        f"llm vs rule-v2 (n= 8): Δ=€{ps_l_vs_r['delta_margin']:+7.2f} ± {ps_l_vs_r['se_margin']:6.2f} "
        f"(t={ps_l_vs_r['t_stat']:+.2f}) W/L={ps_l_vs_r['better']}/{ps_l_vs_r['worse']} ΔOT={ps_l_vs_r['delta_ot_pp']:+.2f}pp"
    )

    print()
    print("=== PER-SEED 16-DEV BREAKDOWN (LLM vs CHAMPION) ===")
    l16 = load_results(runs["llm-16dev"] / "results.jsonl")
    for s in sorted(l16.keys()):
        c, l = champ[s], l16[s]
        st_l = l["stats"]
        dials_str = " -> ".join(
            f"({st_l.get(f'sup_win_d{d}',0.4):.2f},{st_l.get(f'sup_supply_d{d}',22)},{st_l.get(f'sup_fee_d{d}',0.85):.2f})"
            for d in range(4)
        )
        print(
            f"{s}: champ €{c['margin']:8.2f} ({c['on_time']*100:5.2f}%, won {c['won']:3d}) -> "
            f"llm €{l['margin']:8.2f} ({l['on_time']*100:5.2f}%, won {l['won']:3d}) | "
            f"Δ=€{l['margin']-c['margin']:+7.2f} ΔOT={(l['on_time']-c['on_time'])*100:+.2f}pp | {dials_str}"
        )

    print()
    print("=== RULE-V2 vs LLM DIRECTIONAL COMPARISON ON DEV-01..08 (32 EVENINGS) ===")
    same_dir, diff_dir = 0, 0
    for i in range(1, 9):
        s = f"dev-0{i}"
        prev_r = (0.40, 22, 0.85)
        prev_l = (0.40, 22, 0.85)
        for d in DAYS:
            rd = json.loads(Path(f"runs/supervisor/rule/{s}-{d}.json").read_text(encoding="utf-8"))
            ld = json.loads(Path(f"runs/supervisor/{s}-{d}.json").read_text(encoding="utf-8"))
            cur_r = (rd["dials"]["price_target_win"], rd["dials"]["min_supply"], rd["dials"]["fee_open"])
            cur_l = (ld["dials"]["price_target_win"], ld["dials"]["min_supply"], ld["dials"]["fee_open"])
            mr = classify_move(prev_r, cur_r)
            ml = classify_move(prev_l, cur_l)
            if mr == ml:
                same_dir += 1
            else:
                diff_dir += 1
                sm_r = rd["summary"]
                sm_l = ld["summary"]
                print(
                    f"  DIFF {s} {d}: rule {mr:7s} {cur_r} (pot={sm_r['projected_on_time']:.3f},unb={sm_r['unbooked_orders_now']},wr={sm_r['win_rate']:.2f},drp={sm_r['drops_today']}) "
                    f"vs llm {ml:7s} {cur_l} (pot={sm_l['projected_on_time']:.3f},unb={sm_l['unbooked_orders_now']},wr={sm_l['win_rate']:.2f},drp={sm_l['drops_today']},wrn={sm_l['warnings_today']}) | why: {ld['why']}"
                )
            prev_r, prev_l = cur_r, cur_l
    print(f"Total 32 evenings: same direction={same_dir}, different direction={diff_dir}")

    print()
    print("=== DEV-09..16 LLM DECISIONS & WHY ===")
    tot_calls = sum(r["stats"].get("sup_calls", 0) for r in l16.values())
    tot_api = sum(r["stats"].get("sup_api_calls", 0) for r in l16.values())
    tot_cache = sum(r["stats"].get("sup_cache_hits", 0) for r in l16.values())
    tot_used = sum(r["stats"].get("sup_answers_used", 0) for r in l16.values())
    tot_fb = sum(r["stats"].get("sup_fallbacks", 0) for r in l16.values())
    print(f"16-dev totals: calls={tot_calls}, api_calls={tot_api}, cache_hits={tot_cache}, answers_used={tot_used}, fallbacks={tot_fb}")
    for i in range(9, 17):
        s = f"dev-{i:02d}"
        for d in DAYS:
            p = Path(f"runs/supervisor/{s}-{d}.json")
            if not p.exists():
                print(f"  {s} {d}: [FALLBACK - timeout/error, kept today's dials]")
                continue
            ld = json.loads(p.read_text(encoding="utf-8"))
            sm, dl = ld["summary"], ld["dials"]
            print(
                f"  {s} {d}: pot={sm['projected_on_time']:.3f} unb={sm['unbooked_orders_now']:2d} "
                f"wr={sm['win_rate']:.2f} drp={sm['drops_today']:2d} wrn={sm['warnings_today']:2d} -> "
                f"({dl['price_target_win']:.2f},{dl['min_supply']},{dl['fee_open']:.2f}) | {ld['why']}"
            )


if __name__ == "__main__":
    main()
