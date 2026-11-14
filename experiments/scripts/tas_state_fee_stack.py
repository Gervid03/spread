"""Stacks Exact Fork-Bisected Drop-Proof Flat Fees on top of TasStateDesk's `book-tas-state-dp-safe.json` (`Prices + State + Fees`).

Because `book-tas-state-dp-safe.json` already contains exact state-steered dealer limits, zero forks are
needed on quotes; ~500-650 forks (~45s/world) bisect the lowest drop-proof flat fee for every posted gig!
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


def bisect_post_fees(
    tas_mod,
    g: Any,
    other_actions: list[dict[str, Any]],
    post_actions: list[dict[str, Any]],
    iters: int = 6,
    horizon_min: int = 330,
) -> list[dict[str, Any]]:
    from spread_lab.policy import order_ids_of

    desk = g.desk
    now = desk.now
    n = len(post_actions)
    ref_sums = []
    min_lps = []
    for pa in post_actions:
        oids = order_ids_of(pa)
        rs = sum(desk.requests[oid]["referenceFeeCents"] for oid in oids if oid in desk.requests)
        lp = min((desk.orders[oid]["lastPickupAt"] for oid in oids if oid in desk.orders), default=now + 600)
        ref_sums.append(max(1000, rs))
        min_lps.append(lp)

    eval_to = min(g.ends_at, max(now + 60, min(now + horizon_min, min(min_lps) - 90)))
    lo = [int(rs * (0.35 if len(order_ids_of(pa)) >= 2 else 0.56)) for rs, pa in zip(ref_sums, post_actions)]
    hi = [int(rs * (0.90 if len(order_ids_of(pa)) >= 2 else 1.25)) for rs, pa in zip(ref_sums, post_actions)]
    seen_ok = [False] * n

    def try_fees(fees: list[int]) -> set[int]:
        trial_posts = [{**pa, "schedule": [{"at": now, "feeCents": max(100, f)}]} for pa, f in zip(post_actions, fees)]
        step = tas_mod.on_fork(g, [*other_actions, *trial_posts], eval_to)
        offset = len(other_actions)
        gid_to_i = {}
        for i in range(n):
            r = step["results"][offset + i] if offset + i < len(step["results"]) else {}
            if r.get("ok"):
                gid_to_i[r["id"]] = i
        booked: set[int] = set()
        for ev in step["events"]:
            k = ev["kind"]
            gid = ev.get("gigId")
            if k == "gig_booked" and gid in gid_to_i:
                booked.add(gid_to_i[gid])
            elif k in ("gig_dropped", "no_show", "gig_expired") and gid in gid_to_i:
                booked.discard(gid_to_i[gid])
        return booked

    top_ok = try_fees(hi)
    for i in top_ok:
        seen_ok[i] = True

    for _ in range(iters):
        if not any(seen_ok[i] and hi[i] - lo[i] > 200 for i in range(n)):
            break
        mids = [((lo[i] + hi[i]) // 2) if (seen_ok[i] and hi[i] - lo[i] > 200) else hi[i] for i in range(n)]
        ok_set = try_fees(mids)
        for i in range(n):
            if not seen_ok[i] or hi[i] - lo[i] <= 200:
                continue
            if i in ok_set:
                hi[i] = mids[i]
            else:
                lo[i] = mids[i]

    out_posts = []
    for i, pa in enumerate(post_actions):
        if seen_ok[i]:
            safe_cents = int(hi[i] * 1.02 + 50)
            out_posts.append({**pa, "schedule": [{"at": now, "feeCents": safe_cents}]})
            desk.stats["tas_fee_oracle_applied"] += 1
        else:
            out_posts.append(pa)
            desk.stats["tas_fee_oracle_fallback"] += 1
    return out_posts


def run_state_plus_fees(tas_mod, seed: str, book_path: Path, name: str, iters: int = 6) -> dict:
    sdir = tas_mod.home(seed)
    tape_path = str(sdir / "tape.json")
    book_data = json.loads(book_path.read_text(encoding="utf-8"))
    by_book = tas_mod.book_hook(book_data)
    params = {
        "tas_seed": seed,
        "tas_tape_path": tape_path,
        "tas_dp_select": True,
        "tas_trust_farm": True,
        "tas_comp_steer": True,
        "tas_event_plan": True,
    }

    with tas_mod.Tas(seed, params, "spread_lab.policies.tas_state:TasStateDesk", name, forks=True) as g:
        def combined_hook(game: Any, actions: list[dict[str, Any]], fresh: list[int]) -> list[dict[str, Any]]:
            acts = by_book(game, actions, fresh)
            post_idxs = [idx for idx, a in enumerate(acts) if a["type"] == "post"]
            if not post_idxs:
                return acts
            others = [a for idx, a in enumerate(acts) if idx not in post_idxs]
            posts = [acts[idx] for idx in post_idxs]
            tuned_posts = bisect_post_fees(tas_mod, game, others, posts, iters=iters)
            res = list(acts)
            for idx, tp in zip(post_idxs, tuned_posts):
                res[idx] = tp
            return res

        g.hook = combined_hook
        result = g.finish()

    tas_mod.report(seed, f"stack-{name}", result, {"book": str(book_path), "stats": dict(g.desk.stats)})
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="dev-12,dev-01,dev-08,dev-07")
    ap.add_argument("--iters", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        real_home = Path.home() / ".spread-lab"
        tmp = Path(tempfile.mkdtemp(prefix="tas-feestack-test-"))
        os.environ.update(SPREAD_LAB_HOME=str(tmp), SPREAD_KEY="selftest", SPREAD_URL="http://127.0.0.1:9")
        wmap = json.loads((real_home / "map.json").read_text(encoding="utf-8"))
        (tmp / "map.json").write_text(json.dumps(wmap), encoding="utf-8")

        import spread_lab.lab as lab_module
        import coplay
        import tas
        from tas_fakeworld import FakeWorld

        lab_module.quiet_until = lambda: None
        coplay.create_world = lambda client, level, seed, board=False: FakeWorld(seed, wmap)

        seed = "selftest-feestack"
        tas.cmd_tape(Namespace(seed=seed, force=False))
        tape_p = str(tas.home(seed) / "tape.json")
        tas.cmd_limits(
            Namespace(
                seed=seed,
                set=[f"tas_seed={seed}", f"tas_tape_path={tape_p}", "tas_dp_select=true", "tas_trust_farm=true", "tas_comp_steer=true", "tas_event_plan=true"],
                policy="spread_lab.policies.tas_state:TasStateDesk",
                name="tas-state-dp-safe",
                until=None,
                book=None,
                mode="won",
                apply=True,
                iters=5,
                lo=0.72,
                hi=2.60,
            )
        )
        res = run_state_plus_fees(tas, seed, tas.home(seed) / "book-tas-state-dp-safe.json", "tas-state-plus-fees", iters=4)
        print(f"SELFTEST PASSED: stack margin=€{res['margin']:,.2f}, won={res['won']}, OT={res['on_time']:.2%}, forks={res['forks']}")
        return

    import tas
    for seed in [s.strip() for s in args.seeds.split(",") if s.strip()]:
        bpath = tas.home(seed) / "book-tas-state-dp-safe.json"
        if not bpath.exists():
            print(f"[SKIP] {seed}: {bpath} not yet available")
            continue
        run_state_plus_fees(tas, seed, bpath, "tas-state-plus-fees", iters=args.iters)


if __name__ == "__main__":
    main()
