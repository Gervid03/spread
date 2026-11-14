"""Step 0 validation of scripts/tas.py on the real server (dev-12, champion v5)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import tas  # noqa: E402
from spread_lab.env import load_dotenv  # noqa: E402


def main() -> None:
    load_dotenv()
    seed = "dev-12"

    print("=== 1. Running tape on dev-12 ===", flush=True)
    tas.cmd_tape(argparse.Namespace(seed=seed, force=False))
    tape = json.loads((tas.home(seed) / "tape.json").read_text(encoding="utf-8"))
    tape_reqs = tape["requests"]
    print(f"Tape requests: {len(tape_reqs)}", flush=True)

    print("=== 2. Running full week v5 check on dev-12 ===", flush=True)
    with tas.Tas(seed, name="v5-week") as g:
        res_week = g.finish()
        won = sum(1 for o in g.outcome.values() if o[0] == "won")
        lost = sum(1 for o in g.outcome.values() if o[0] == "lost")
        desk_reqs = dict(g.desk.requests)
    tas.report(seed, "run-v5-week", res_week, {"book": None, "params": [], "quotes_won": won, "quotes_lost": lost})

    champ = tas.champion_line(seed)
    assert champ is not None, "Missing champion dev-12 line"
    print(f"v5 check: margin={res_week['margin']:.2f} vs champ={champ['margin']:.2f}, "
          f"won={res_week['won']} vs {champ['won']}, on_time={res_week['on_time']:.6f} vs {champ['on_time']:.6f}")
    assert round(res_week["margin"], 2) == round(champ["margin"], 2), "Margin mismatch vs v5!"
    assert res_week["won"] == champ["won"], "Won count mismatch vs v5!"

    # Foresight check: compare tape requests vs desk requests
    tape_by_id = {r["id"]: r for r in tape_reqs}
    same_ids = list(tape_by_id.keys()) == list(desk_reqs.keys())
    diffs = []
    for rid, tr in tape_by_id.items():
        dr = desk_reqs.get(rid)
        if dr is None:
            diffs.append((rid, "missing_in_desk"))
            continue
        for k in ("arrivedAt", "respondBy", "dealerId", "referenceFeeCents", "note"):
            if tr[k] != dr[k]:
                diffs.append((rid, k, tr[k], dr[k]))
        if tr["options"] != dr["options"]:
            diffs.append((rid, "options", tr["options"], dr["options"]))
        if tr["legs"] != dr["legs"]:
            diffs.append((rid, "legs"))
    for rid in desk_reqs:
        if rid not in tape_by_id:
            diffs.append((rid, "missing_in_tape"))
    print(f"Foresight check: tape={len(tape_reqs)}, desk={len(desk_reqs)}, same_order_ids={same_ids}, diffs={len(diffs)}")
    if diffs:
        print("FIRST DIFFS:", diffs[:5])
        raise SystemExit("Foresight check failed!")

    print("=== 3. Running plain run --until 'Tue 07:00' ===", flush=True)
    until_min = tas.minute_of("Tue 07:00")
    with tas.Tas(seed, name="v5-tue07") as g:
        res_tue_plain = g.finish(until_min)
        won_p = sum(1 for o in g.outcome.values() if o[0] == "won")
        lost_p = sum(1 for o in g.outcome.values() if o[0] == "lost")
    tas.report(seed, "run-v5-tue07", res_tue_plain, {"book": None, "params": [], "quotes_won": won_p, "quotes_lost": lost_p})

    print("=== 4. Running limits --until 'Tue 07:00' and timing forks ===", flush=True)
    lines: list[dict] = []
    path = tas.home(seed) / "limits-check-tue07.jsonl"
    batch_timings: list[dict] = []

    with open(path, "w", encoding="utf-8") as f, tas.Tas(seed, name="check-tue07", forks=True) as g:
        def sink(line: dict) -> None:
            lines.append(line)
            print(json.dumps(line), file=f, flush=True)

        inner = tas.price_oracle("won", False, 0.7, 2.6, 9, sink)

        def timed_oracle(game: tas.Tas, actions: list, fresh: list) -> list:
            f0, t0 = game.forks, time.perf_counter()
            out = inner(game, actions, fresh)
            dt = time.perf_counter() - t0
            df = game.forks - f0
            if df > 0:
                batch_timings.append({"at": game.desk.now, "forks": df, "sec": round(dt, 3), "sec_per_fork": round(dt / df, 4)})
            return out

        g.hook = timed_oracle
        res_tue_lim = g.finish(until_min)
        (tas.home(seed) / "book-check-tue07.json").write_text(
            json.dumps({"*": "desk", **{rid: {"prices": p} for rid, p in g.quoted.items()}}), encoding="utf-8"
        )
        broken = sorted(rid for rid, kind in g.expect.items() if rid in g.outcome and g.outcome[rid][:2] != ("won", kind))
        mismatch = sorted(
            l["rid"] for l in lines
            if l["rid"] in g.outcome and l["desk"] in ("won", "lost")
            and l["desk"] != g.outcome[l["rid"]][0] and l["rid"] not in broken
        )

    summary = tas.summarize_limits(lines)
    summary.update({"repriced": len(g.expect), "repriced_but_lost": broken, "preview_differs_from_main_line": mismatch})
    tas.report(seed, "limits-check-tue07", res_tue_lim, {"limits": summary, "params": []})
    print(tas.limits_text(summary))

    # Compare plain vs limits to the cent
    print("=== Plain vs Limits at Tue 07:00 ===")
    print("Plain :", res_tue_plain)
    print("Limits:", res_tue_lim)
    assert res_tue_plain["margin"] == res_tue_lim["margin"], "Parent world moved in margin!"
    assert res_tue_plain["revenue"] == res_tue_plain["revenue"] and res_tue_plain["revenue"] == res_tue_lim["revenue"], "Parent world moved in revenue!"
    assert res_tue_plain["won"] == res_tue_lim["won"], "Parent world moved in won orders!"
    assert res_tue_plain["on_time"] == res_tue_lim["on_time"], "Parent world moved in on_time!"
    assert res_tue_plain["ledger"] == res_tue_lim["ledger"], "Parent world moved in ledger!"
    assert not broken and not mismatch, f"CHECK failed: broken={broken}, mismatch={mismatch}"

    # Summarize fork timings: Mon morning (<= 14:00 = 840) vs Mon afternoon/evening (> 840)
    morn = [b for b in batch_timings if b["at"] <= 14 * 60]
    eve = [b for b in batch_timings if b["at"] > 14 * 60]
    morn_f = sum(b["forks"] for b in morn)
    morn_s = sum(b["sec"] for b in morn)
    eve_f = sum(b["forks"] for b in eve)
    eve_s = sum(b["sec"] for b in eve)
    print(f"Fork timing Mon morning (<=14:00): {morn_f} forks in {morn_s:.1f}s = {morn_s / max(1, morn_f):.3f} s/fork ({morn_f / max(1e-9, morn_s) * 60:.0f} forks/min)")
    print(f"Fork timing Mon afternoon (>14:00): {eve_f} forks in {eve_s:.1f}s = {eve_s / max(1, eve_s) * 60:.0f} forks/min | {eve_s / max(1, eve_f):.3f} s/fork ({eve_f / max(1e-9, eve_s) * 60:.0f} forks/min)")
    (tas.home(seed) / "step0-fork-timings.json").write_text(json.dumps(batch_timings, indent=2), encoding="utf-8")
    print("ALL STEP 0 CHECKS PASSED TO THE CENT!")


if __name__ == "__main__":
    main()
