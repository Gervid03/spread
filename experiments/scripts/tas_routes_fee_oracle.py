"""Full-stack Tour + Exact Flat-Fee Oracle (`tas-routes` + `tas-price` + `tas-fees` [+ `tas-state`]).

Replays a quote book (`book-*.json`) with `spread_lab.policies.tas_routes:Desk` and `tours-*.json`,
and intercepts every `post` action to fork-bisect the exact minimum drop-proof flat fee (`f_chosen`)
that books and stays booked (no `gig_dropped` / `no_show`) over the next `horizon_min` minutes!
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from spread_lab.env import lab_home
from spread_lab.policy import order_ids_of
from tas import Tas, book_hook, on_fork, price_oracle, report


def bisect_post_fees(
    g: Tas,
    other_actions: list[dict[str, Any]],
    post_actions: list[dict[str, Any]],
    iters: int = 6,
    horizon_min: int = 330,
) -> list[dict[str, Any]]:
    """Bisects flat fee [0.30 * ref_sum, 1.15 * ref_sum] in `iters` fork rounds for `post_actions`."""
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
    lo = [int(rs * (0.30 if len(order_ids_of(pa)) >= 2 else 0.58)) for rs, pa in zip(ref_sums, post_actions)]
    hi = [int(rs * (0.85 if len(order_ids_of(pa)) >= 2 else 1.25)) for rs, pa in zip(ref_sums, post_actions)]
    seen_ok = [False] * n

    def try_fees(fees: list[int]) -> set[int]:
        trial_posts = [{**pa, "schedule": [{"at": now, "feeCents": max(100, f)}]} for pa, f in zip(post_actions, fees)]
        step = on_fork(g, [*other_actions, *trial_posts], eval_to)
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

    # Check top of bracket first so unbookable posts keep safe fallback schedule
    top_ok = try_fees(hi)
    for i in top_ok:
        seen_ok[i] = True

    for _ in range(iters):
        if not any(seen_ok[i] and hi[i] - lo[i] > 250 for i in range(n)):
            break
        mids = [((lo[i] + hi[i]) // 2) if (seen_ok[i] and hi[i] - lo[i] > 250) else hi[i] for i in range(n)]
        ok_set = try_fees(mids)
        for i in range(n):
            if not seen_ok[i] or hi[i] - lo[i] <= 250:
                continue
            if i in ok_set:
                hi[i] = mids[i]
            else:
                lo[i] = mids[i]

    out_posts = []
    for i, pa in enumerate(post_actions):
        if seen_ok[i]:
            # Add +2% safety cushion above minimum fork-bisected fee so tiny downstream drift never causes a drop
            safe_cents = int(hi[i] * 1.02 + 50)
            out_posts.append({**pa, "schedule": [{"at": now, "feeCents": safe_cents}]})
            desk.stats["oracle_fee_applied"] += 1
        else:
            out_posts.append(pa)
            desk.stats["oracle_fee_fallback"] += 1
    return out_posts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="dev-12")
    ap.add_argument("--book", required=True)
    ap.add_argument("--tours", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--iters", type=int, default=6)
    args = ap.parse_args()

    book_path = Path(args.book)
    plan_candidate = book_path.parent / book_path.name.replace("book-", "plan-")
    use_plan_oracle = plan_candidate.exists()
    src_book_path = plan_candidate if use_plan_oracle else book_path
    book_data = json.loads(src_book_path.read_text(encoding="utf-8"))
    by_book = book_hook(book_data, open_x=0.50)
    params = {
        "tour_plan_file": str(Path(args.tours).resolve()),
        "tour_flat_mode": True,
        "tour_step_interval_min": 90,
    }

    with Tas(args.seed, params, "spread_lab.policies.tas_routes:Desk", args.name, forks=True) as g:
        p_oracle = price_oracle("won", True, 0.48, 2.50, 8, lambda _line: None) if use_plan_oracle else None

        def combined_hook(game: Tas, actions: list[dict[str, Any]], fresh: list[int]) -> list[dict[str, Any]]:
            acts = by_book(game, actions, fresh)
            if p_oracle is not None and fresh:
                acts = p_oracle(game, acts, fresh)
            post_idxs = [idx for idx, a in enumerate(acts) if a["type"] == "post"]
            if not post_idxs:
                return acts
            others = [a for idx, a in enumerate(acts) if idx not in post_idxs]
            posts = [acts[idx] for idx in post_idxs]
            tuned_posts = bisect_post_fees(game, others, posts, iters=args.iters)
            res = list(acts)
            for idx, tp in zip(post_idxs, tuned_posts):
                res[idx] = tp
            return res

        g.hook = combined_hook
        result = g.finish()

    report(args.seed, args.name, result, {"book": args.book, "tours": args.tours, "stats": dict(g.desk.stats)})


if __name__ == "__main__":
    main()
