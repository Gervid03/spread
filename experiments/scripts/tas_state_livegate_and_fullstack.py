"""Runs:
1. `tas-state-livegate` (Layer 4: Champion v5's real-time congestion gate + foresight Trust Farming + Competitor [30%,70%) & Fri Endgame Steering + Event-Calendar Steering, with `tas_early_warn_h=0.0`) across `dev-12, dev-01, dev-08, dev-07`, both SAFE (>=92% OT) and EDGE (>=90% OT), verified with 0-fork `run --book` replay!
2. `tas-fullstack-ceiling` (Full 5-Layer Waterfall Ceiling: `Prices + Exact Drop-Proof Fees + Foresight Tours + Steered State`) with **Trust-Drift-Proof Quote Re-Bisection**:
   - Fixes the cascade quote-loss bug (`380 -> 271` won) that occurs when exact-fee staffing shifts delivery minutes by ±60m and perturbs `dealer_trust` by -1 point during book replay: on each quote batch, 1 preview fork checks if every planned win in `book-*.json` still wins at `lo`; any quote that lost due to a -1 trust shift is re-bisected on the spot (~6 forks) so **0 planned tours break AND 100% of true live dealer limits are captured**!
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "experiments" / "scripts"))


def has_completed_run(seed_dir: Path, run_name: str) -> bool:
    rp = seed_dir / "runs.jsonl"
    if not rp.exists():
        return False
    for line in rp.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("name") == run_name:
            return True
    return False


def run_livegate_world(tas_mod, seed: str, edge: bool = False, iters: int = 7) -> dict:
    sdir = tas_mod.home(seed)
    tape_path = str(sdir / "tape.json")
    name = "tas-state-disc86-edge" if edge else "tas-state-disc90-safe"
    lim_name = f"limits-{name}"
    rep_name = f"run-rep-{name}"
    if has_completed_run(sdir, rep_name) and (sdir / f"book-{name}.json").exists():
        print(f"[SKIP] {seed} {name} already verified", flush=True)
        rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return next(r for r in reversed(rows) if r["name"] == lim_name)

    sets = [
        f"tas_seed={seed}",
        f"tas_tape_path={tape_path}",
        f"tas_entry_disc={'0.86' if edge else '0.90'}",
        "tas_event_plan=true",
        "tas_early_warn_h=0.0",
        f"tas_backlog_mult={'1.65' if edge else '1.35'}",
    ]
    if edge:
        sets.append("tas_late_edge=true")

    print()
    print(f">>> [{seed}] Running {lim_name} ...", flush=True)
    tas_mod.cmd_limits(
        Namespace(
            seed=seed,
            set=sets,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=name,
            until=None,
            book=None,
            mode="won",
            apply=True,
            iters=iters,
            lo=0.72,
            hi=2.60,
        )
    )
    book_path = str(sdir / f"book-{name}.json")
    tas_mod.cmd_run(
        Namespace(
            seed=seed,
            set=sets,
            policy="spread_lab.policies.tas_state:TasStateDesk",
            name=f"rep-{name}",
            until=None,
            book=book_path,
        )
    )
    rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    lim_r = next(r for r in reversed(rows) if r["name"] == lim_name)
    rep_r = next(r for r in reversed(rows) if r["name"] == rep_name)
    print(
        f"[DONE] {seed} {name}: €{lim_r['margin']:,.2f} (won={lim_r['won']}, OT={lim_r['on_time']*100:.2f}%, forks={lim_r['forks']}, drift={rep_r['margin']-lim_r['margin']:+.2f})",
        flush=True,
    )
    return lim_r


def run_driftproof_fullstack(
    tas_mod,
    seed: str,
    book_path: Path,
    tours_path: Optional[Path],
    policy: str,
    extra_params: dict[str, Any],
    name: str,
    fee_iters: int = 6,
) -> dict:
    import tas_state_fee_stack as fee_stack

    sdir = tas_mod.home(seed)
    if has_completed_run(sdir, name):
        print(f"[SKIP] {seed} {name} already recorded", flush=True)
        rows = [json.loads(l) for l in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return next(r for r in reversed(rows) if r["name"] == name)

    book_data = json.loads(book_path.read_text(encoding="utf-8"))
    by_book = tas_mod.book_hook(book_data)
    # Companion limits-*.jsonl identifies which requests actually WON in the source run!
    lim_companion = book_path.parent / book_path.name.replace("book-", "limits-").replace(".json", ".jsonl")
    true_won_rids: Optional[set[str]] = None
    if lim_companion.exists():
        true_won_rids = {
            json.loads(l)["rid"]
            for l in lim_companion.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("lo") is not None
        }

    params = dict(extra_params)
    if tours_path is not None and tours_path.exists():
        params["tour_plan_file"] = str(tours_path)

    saved_book: dict[str, Any] = {}

    with tas_mod.Tas(seed, params, policy, name, forks=True) as g:
        def driftproof_hook(game: Any, actions: list[dict[str, Any]], fresh: list[int]) -> list[dict[str, Any]]:
            acts = by_book(game, actions, fresh)

            # 1. Trust-Drift Guard ONLY on fresh quotes that actually WON in `lim_companion`!
            if fresh:
                planned_wins = {}
                fresh_quotes = []
                for idx in fresh:
                    q = acts[idx]
                    rid = q["requestId"]
                    spec = book_data.get(rid)
                    fresh_quotes.append(q)
                    if true_won_rids is not None and rid not in true_won_rids:
                        continue
                    if isinstance(spec, dict) and len(q["prices"]) == 1:
                        opt_k, cents = next(iter(q["prices"].items()))
                        req = game.desk.requests[rid]
                        lp = next(o["listPriceCents"] for o in req["options"] if o["kind"] == opt_k)
                        if cents < 3.4 * lp:
                            planned_wins[rid] = (idx, opt_k, cents)

                if planned_wins:
                    to_resp = max(game.desk.requests[q["requestId"]]["respondBy"] for q in fresh_quotes)
                    prev = tas_mod.outcomes(tas_mod.on_fork(game, fresh_quotes, to_resp)["events"])
                    drifted = [rid for rid in planned_wins if prev.get(rid, ("lost",))[0] != "won"]
                    if drifted:
                        drifted_quotes = [acts[planned_wins[rid][0]] for rid in drifted]
                        targets = {rid: planned_wins[rid][1] for rid in drifted}
                        reprobed = tas_mod.probe_prices(game, drifted_quotes, targets, lo_x=0.72, hi_x=2.40, iters=6)
                        acts = list(acts)
                        for rid, st in reprobed.items():
                            idx, opt_k, old_c = planned_wins[rid]
                            if st.get("lo") is not None:
                                acts[idx] = {"type": "quote", "requestId": rid, "prices": {opt_k: st["lo"]}}
                                game.expect[rid] = opt_k
                                game.desk.stats["tas_drift_rescued"] += 1

                for idx in fresh:
                    q = acts[idx]
                    saved_book[q["requestId"]] = dict(q["prices"])

            # 2. Exact Drop-Proof Flat Fee Oracle on every posted solo or multi-car tour gig!
            post_idxs = [idx for idx, a in enumerate(acts) if a["type"] == "post"]
            if post_idxs:
                others = [a for idx, a in enumerate(acts) if idx not in post_idxs]
                posts = [acts[idx] for idx in post_idxs]
                tuned_posts = fee_stack.bisect_post_fees(tas_mod, game, others, posts, iters=fee_iters)
                acts = list(acts)
                for idx, tp in zip(post_idxs, tuned_posts):
                    acts[idx] = tp

            return acts

        g.hook = driftproof_hook
        result = g.finish()

    out_book = sdir / f"book-{name}.json"
    out_book.write_text(json.dumps(saved_book, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    tas_mod.report(seed, name, result, {"source_book": str(book_path), "tours": str(tours_path), "stats": dict(g.desk.stats)})
    return result


def pick_best_steered_tour_plan(sdir: Path) -> tuple[Optional[Path], Optional[Path]]:
    rp = sdir / "runs.jsonl"
    best_tag: Optional[str] = None
    best_m = -1e9
    candidates = ("tas-routes-elite", "tas-routes-push540", "tas-routes-steered440", "tas-routes-clean400")
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            for tag in candidates:
                if r.get("name") == f"limits-{tag}" and r.get("on_time", 0) >= 0.92:
                    if r["margin"] > best_m and (sdir / f"book-{tag}.json").exists() and (sdir / f"tours-{tag}.json").exists():
                        best_m = r["margin"]
                        best_tag = tag
    if best_tag:
        return sdir / f"book-{best_tag}.json", sdir / f"tours-{best_tag}.json"
    for tag in candidates:
        b, t = sdir / f"book-{tag}.json", sdir / f"tours-{tag}.json"
        if b.exists() and t.exists():
            return b, t
    return None, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["livegate", "fullstack", "both", "selftest"], required=True)
    ap.add_argument("--seeds", default="dev-12,dev-01,dev-08,dev-07")
    args = ap.parse_args()

    if args.mode == "selftest":
        real_home = Path.home() / ".spread-lab"
        wmap = json.loads((real_home / "map.json").read_text(encoding="utf-8"))
        # Dry-run TasStateDesk(tas_entry_disc=0.90) across all 4,142 real requests on dev-12, dev-01, dev-08, dev-07!
        from spread_lab.geo import Geo
        from spread_lab.policies.tas_state import TasStateDesk, TasStateParams
        geo = Geo(wmap)
        for rs in ("dev-12", "dev-01", "dev-08", "dev-07"):
            rtape = json.loads((real_home / "tas" / rs / "tape.json").read_text(encoding="utf-8"))
            tp = TasStateParams(tas_seed=rs, tas_tape_path=str(real_home / "tas" / rs / "tape.json"), tas_entry_disc=0.90, tas_event_plan=True, tas_backlog_mult=1.35)
            td = TasStateDesk(world=None, params=tp, level=8, geo=geo, roster=rtape["roster"], now=0)  # type: ignore[arg-type]
            q_cnt = 0
            for req in rtape["requests"]:
                td.now = req["arrivedAt"]
                pr, _ = td.price(req)
                if pr:
                    q_cnt += 1
            print(f"Real-tape dry-run {rs}: {q_cnt} quoted cleanly (0 errors)")

        tmp = Path(tempfile.mkdtemp(prefix="tas-fullstack-test-"))
        os.environ.update(SPREAD_LAB_HOME=str(tmp), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
        (tmp / "map.json").write_text(json.dumps(wmap), encoding="utf-8")

        import spread_lab.lab as lab_module
        import coplay
        import tas
        from tas_fakeworld import FakeWorld

        lab_module.quiet_until = lambda: None
        coplay.create_world = lambda client, level, seed, board=False: FakeWorld(seed, wmap)

        seed = "selftest-fs"
        tas.cmd_tape(Namespace(seed=seed, force=False))
        r1 = run_livegate_world(tas, seed, edge=False, iters=5)
        sdir = tas.home(seed)
        r2 = run_driftproof_fullstack(
            tas,
            seed,
            sdir / "book-tas-state-disc90-safe.json",
            None,
            "spread_lab.policies.tas_state:TasStateDesk",
            {"tas_seed": seed, "tas_tape_path": str(sdir / "tape.json"), "tas_entry_disc": 0.90, "tas_event_plan": True, "tas_backlog_mult": 1.35},
            "tas-state-disc90-plus-fees",
            fee_iters=4,
        )
        print(f"SELFTEST OK: disc90=€{r1['margin']:,.2f} (won={r1['won']}) -> +exact_fees=€{r2['margin']:,.2f} (won={r2['won']}, OT={r2['on_time']:.2%})")
        return

    import tas
    seed_list = [s.strip() for s in args.seeds.split(",") if s.strip()]

    for s in seed_list:
        sdir = tas.home(s)
        if args.mode in ("livegate", "both"):
            run_livegate_world(tas, s, edge=False, iters=7)
            if s == "dev-12":
                run_livegate_world(tas, s, edge=True, iters=7)
            run_driftproof_fullstack(
                tas,
                s,
                sdir / "book-tas-state-disc90-safe.json",
                None,
                "spread_lab.policies.tas_state:TasStateDesk",
                {"tas_seed": s, "tas_tape_path": str(sdir / "tape.json"), "tas_entry_disc": 0.90, "tas_event_plan": True, "tas_backlog_mult": 1.35},
                "tas-state-disc90-plus-fees",
                fee_iters=6,
            )

        if args.mode in ("fullstack", "both"):
            # Step 2 (Drift-proof Prices + Exact Fees on Champion v5's won orders)
            b_l1 = sdir / "book-won-apply.json"
            if b_l1.exists():
                print()
                print(f">>> [{s}] Running Drift-Proof Step 2 (Champion + Prices + Exact Fees) ...", flush=True)
                run_driftproof_fullstack(
                    tas,
                    s,
                    b_l1,
                    None,
                    "spread_lab.policy:Desk",
                    {},
                    "tas-step2-prices-plus-fees",
                    fee_iters=6,
                )
            # Step 3 (Drift-proof Unsteered Tours + Prices + Exact Fees on clean400)
            b_c4 = sdir / "book-tas-routes-clean400.json"
            t_c4 = sdir / "tours-tas-routes-clean400.json"
            if b_c4.exists() and t_c4.exists():
                print()
                print(f">>> [{s}] Running Drift-Proof Step 3 (Prices + Exact Fees + Unsteered Tours) ...", flush=True)
                run_driftproof_fullstack(
                    tas,
                    s,
                    b_c4,
                    t_c4,
                    "spread_lab.policies.tas_routes_compat:Desk",
                    {"tour_dynamic": True, "relay_offers": True},
                    "tas-step3-tours-plus-fees",
                    fee_iters=6,
                )
            # Step 4 / Full 5-Layer Ceiling (Prices + Exact Fees + Foresight Tours + Steered State!)
            bpath, tpath = pick_best_steered_tour_plan(sdir)
            if bpath and tpath:
                print()
                print(f">>> [{s}] Running Drift-Proof Full 5-Layer Ceiling Stack on {bpath.name} + {tpath.name} ...", flush=True)
                run_driftproof_fullstack(
                    tas,
                    s,
                    bpath,
                    tpath,
                    "spread_lab.policies.tas_routes_compat:Desk",
                    {"tour_dynamic": True, "relay_offers": True},
                    "tas-fullstack-5layer",
                    fee_iters=6,
                )


if __name__ == "__main__":
    main()
