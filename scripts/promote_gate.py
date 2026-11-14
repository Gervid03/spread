#!/usr/bin/env python3
"""The promotion gates of scripts/promote.sh, checked against the current champion (champion/ in this checkout).
    uv run python scripts/promote_gate.py <dev run folder> <holdout run folder> [<restart log>]
Exit 0 when every gate passes, 7 when one fails. Prints the numbers either way, then one line per failed gate.
Gates (docs/HANDOFF.md, Sat 01:00):
  dev      SAFE (every world ranked and >= 92% on time), and paired Δ vs the champion > 0 with t >= 2 on 16 seeds;
  holdout  every world ranked, paired Δ >= 0, no more worlds under 92% than the champion, and a minimum on-time
           share no more than 0.5 points below the champion's;
  restart  (if a log is given) the restarted world finished ranked.
"""
import json
import sys
from pathlib import Path

from spread_lab.lab import champion_results, compare, load_results, summarize


def under(rows: list, cut: float = 0.92) -> int:
    return sum(1 for r in rows if "error" not in r and r["on_time"] < cut)


def main() -> int:
    dev, hold = Path(sys.argv[1]), Path(sys.argv[2])
    restart = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    champ = champion_results()
    champ_dev = [r for r in champ if r["seed"].startswith("dev-")]
    champ_hold = [r for r in champ if r["seed"].startswith("hold-")]
    d, h = load_results(dev), load_results(hold)
    sd, sh = summarize(d), summarize(h)
    cd, ch = compare(d, champ_dev), compare(h, champ_hold)
    fails = []
    if not sd.get("safe"):
        fails.append(f"dev is not SAFE (on-time min {sd.get('on_time_min')}, ranked {sd.get('ranked')}/{sd.get('n')}, failed {sd.get('failed')})")
    if not cd or cd["n"] < 16:
        fails.append("dev: no paired comparison with the champion on 16 seeds")
    elif not (cd["delta_mean"] > 0 and (cd["t"] or 0) >= 2):
        fails.append(f"dev: Δ {cd['delta_mean']:+,.0f} ± {cd['delta_se']:,.0f} (t {cd['t']}): needs Δ > 0 with t >= 2")
    if sh.get("failed") or sh.get("ranked") != sh.get("n") or sh.get("n", 0) < 16:
        fails.append(f"holdout: {sh.get('ranked')}/{sh.get('n')} ranked, {sh.get('failed')} failed")
    if not ch or ch["n"] < 16:
        fails.append("holdout: no paired comparison with the champion on 16 seeds")
    elif ch["delta_mean"] < 0:
        fails.append(f"holdout: Δ {ch['delta_mean']:+,.0f} ± {ch['delta_se']:,.0f} is below 0")
    if under(h) > under(champ_hold):
        fails.append(f"holdout: {under(h)} worlds under 92%, the champion has {under(champ_hold)}")
    if champ_hold and sh.get("n"):
        cmin = min(r["on_time"] for r in champ_hold if "error" not in r)
        if sh["on_time_min"] < cmin - 0.005:
            fails.append(f"holdout: on-time min {sh['on_time_min']:.1%} is more than 0.5 points below the champion's {cmin:.1%}")
    if restart is not None:
        text = restart.read_text(encoding="utf-8", errors="replace") if restart.exists() else ""
        if "ranked True" not in text:
            fails.append(f"restart: the restarted world did not finish ranked ({restart})")
    print(json.dumps({"dev": sd, "dev_vs_champion": cd, "holdout": sh, "holdout_vs_champion": ch,
                      "under_92": {"candidate_holdout": under(h), "champion_holdout": under(champ_hold),
                                   "candidate_dev": under(d), "champion_dev": under(champ_dev)}}, indent=1))
    if fails:
        print("GATES FAILED:\n  " + "\n  ".join(fails))
        return 7
    print(f"ALL GATES PASSED: dev Δ {cd['delta_mean']:+,.0f} ± {cd['delta_se']:,.0f} (t {cd['t']}), "
          f"holdout Δ {ch['delta_mean']:+,.0f} ± {ch['delta_se']:,.0f}, holdout on-time min {sh['on_time_min']:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
