"""Controlled fork experiments on dev-12 to measure exact hidden state equations:
1. Competitor morning reaction vs Monday win share (0%, 25%, 50%, 75%, 100%) with trust=0 isolated.
2. Lose-close (2.2x list) vs Decline (4.0x list) on Monday -> Tuesday limits.
3. Multi-day cumulative competitor reaction (0% Mon+Tue vs 100% Mon+Tue -> Wednesday limits).
4. Trust (+1% per delivered car) and Satisfaction penalty of 1 late car (delivered ~20:45 Mon vs undelivered past Mon 20:00).
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import tas  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402
from spread_lab.runner import DAY  # noqa: E402


def pick_probe_option(req: dict) -> str:
    kinds = [o["kind"] for o in req["options"]]
    return "next_day" if "next_day" in kinds else kinds[0]


def run_arm(
    arm_name: str,
    probe_day: int,
    monday_mode: str,
    hold_all_gigs: bool = True,
    late_test_dealers: tuple[str, str] = ("D04", "D07"),
) -> dict:
    """Plays dev-12 to probe_day 09:30, bisecting limits of requests arriving 08:00..09:30 on probe_day."""
    probe_start = probe_day * DAY + 8 * 60
    probe_end = probe_day * DAY + 9 * 60 + 30
    dealer_seen = Counter()
    probed: dict[str, dict] = {}
    delayed_orders: list[tuple[int, dict]] = []

    with tas.Tas("dev-12", name=f"tas-state-{arm_name}", forks=True) as g:
        if hold_all_gigs:
            g.desk.post = lambda *a, **kw: None  # type: ignore[method-assign]
        elif monday_mode == "trust_and_late":
            orig_post = g.desk.post

            def custom_post(order, legs, retry=None, allow_pair=True):
                dlr = g.desk.requests[order["id"]]["dealerId"]
                # Hold first D04 same_day car until 19:40 Mon so it delivers ~20:30 Mon (late <= 2h!)
                if dlr == late_test_dealers[0] and order["option"] == "same_day" and not any(
                    g.desk.requests[o["id"]]["dealerId"] == late_test_dealers[0] for _, o in delayed_orders
                ):
                    delayed_orders.append((19 * 60 + 40, order))
                    return
                # Hold first D07 same_day car completely (undelivered past Mon 20:00 deadline!)
                if dlr == late_test_dealers[1] and order["option"] == "same_day":
                    return
                if retry is None:
                    orig_post(order, legs, allow_pair=allow_pair)
                else:
                    orig_post(order, legs, retry, allow_pair=allow_pair)

            g.desk.post = custom_post  # type: ignore[method-assign]

            orig_tick = g.desk.tick

            def custom_tick():
                orig_tick()
                for post_at, order in list(delayed_orders):
                    if g.desk.now >= post_at:
                        delayed_orders.remove((post_at, order))
                        g.desk.urgent.add(order["id"])
                        orig_post(order, [0], allow_pair=False)

            g.desk.tick = custom_tick  # type: ignore[method-assign]

        def hook(game: tas.Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            now = game.desk.now
            if now < probe_start:
                for i in fresh:
                    rid = out[i]["requestId"]
                    req = game.desk.requests[rid]
                    dlr = req["dealerId"]
                    dealer_seen[dlr] += 1
                    idx = dealer_seen[dlr]
                    opts = {o["kind"]: o["listPriceCents"] for o in req["options"]}

                    if monday_mode == "decline_4x":
                        k0 = req["options"][0]["kind"]
                        out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                    elif monday_mode == "lose_2.3x":
                        k0 = req["options"][0]["kind"]
                        out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 2.3)}}
                    elif monday_mode.startswith("win_"):
                        pct = int(monday_mode.split("_")[1])
                        # Pick slow option so deadline is Tue 20:00+ (not late at Tue 09:30!)
                        slow_k = "within_3_days" if "within_3_days" in opts else ("next_day" if "next_day" in opts else None)
                        want_win = slow_k is not None and ((idx * pct) % 100 < pct or pct == 100)
                        if want_win and slow_k is not None:
                            out[i] = {"type": "quote", "requestId": rid, "prices": {slow_k: int(opts[slow_k] * 0.55)}}
                        else:
                            k0 = req["options"][0]["kind"]
                            out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                    elif monday_mode == "trust_and_late":
                        # For D01: win hub same_day cars on Monday to build trust; for D04/D07: win 1 same_day car
                        pick_id = req["legs"][0]["pickup"]["placeId"]
                        sup = game.desk.supply.get(pick_id, 0)
                        if dlr == "D01" and "same_day" in opts and sup >= 200 and not req.get("note") and idx <= 25:
                            out[i] = {"type": "quote", "requestId": rid, "prices": {"same_day": int(opts["same_day"] * 0.60)}}
                        elif dlr in late_test_dealers and "same_day" in opts and sup >= 200 and not req.get("note") and idx <= 4:
                            out[i] = {"type": "quote", "requestId": rid, "prices": {"same_day": int(opts["same_day"] * 0.60)}}
                        else:
                            k0 = req["options"][0]["kind"]
                            out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                return out

            if probe_start <= now <= probe_end:
                quotes = [out[i] for i in fresh]
                targets = {a["requestId"]: pick_probe_option(game.desk.requests[a["requestId"]]) for a in quotes}
                res = tas.probe_prices(game, quotes, targets, lo_x=0.5, hi_x=2.8, iters=11, tol=10)
                for rid, st in res.items():
                    req = game.desk.requests[rid]
                    probed[rid] = {
                        "rid": rid,
                        "at": now,
                        "dealer": req["dealerId"],
                        "trust": game.desk.dealer_trust.get(req["dealerId"], 0),
                        "late_count": sum(
                            1 for oid in game.desk.late if game.desk.requests[oid]["dealerId"] == req["dealerId"]
                        ),
                        **st,
                    }
                # Decline probed requests on main line so probe window itself doesn't shift anything
                for i in fresh:
                    rid = out[i]["requestId"]
                    req = game.desk.requests[rid]
                    k0 = req["options"][0]["kind"]
                    out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(req["options"][0]["listPriceCents"] * 4.0)}}
            return out

        g.hook = hook
        g.play_to(probe_end + 5)
        # Count wins per dealer before probe_start
        won_by_dlr = Counter()
        tot_by_dlr = Counter()
        for rid, req in g.desk.requests.items():
            if req["arrivedAt"] < probe_start:
                tot_by_dlr[req["dealerId"]] += 1
                if g.outcome.get(rid, ("?",))[0] == "won":
                    won_by_dlr[req["dealerId"]] += 1
        late_details = []
        for oid in sorted(g.desk.orders):
            o = g.desk.orders[oid]
            dlr = g.desk.requests[oid]["dealerId"]
            late_details.append(
                {
                    "oid": oid,
                    "dealer": dlr,
                    "option": o["option"],
                    "deadline": o["deadline"],
                    "deliveredAt": o["deliveredAt"],
                    "in_late": oid in g.desk.late,
                }
            )
        return {
            "arm": arm_name,
            "probe_day": probe_day,
            "forks": g.forks,
            "won_by_dlr": dict(won_by_dlr),
            "tot_by_dlr": dict(tot_by_dlr),
            "trust_at_probe": dict(g.desk.dealer_trust),
            "probed": probed,
            "orders": late_details if monday_mode == "trust_and_late" else [],
        }


def main() -> None:
    arms = [
        ("tue_decline_4x", 1, "decline_4x", True),
        ("tue_lose_2.3x", 1, "lose_2.3x", True),
        ("tue_win_25", 1, "win_25", True),
        ("tue_win_50", 1, "win_50", True),
        ("tue_win_100", 1, "win_100", True),
        ("tue_trust_and_late", 1, "trust_and_late", False),
        ("wed_decline_4x", 2, "decline_4x", True),
        ("wed_win_100", 2, "win_100", True),
    ]
    results = {}
    for name, pday, mode, hold in arms:
        print(f"Running {name} (probe_day={pday}, mode={mode})...", flush=True)
        r = run_arm(name, pday, mode, hold_all_gigs=hold)
        results[name] = r
        print(f"  done: {len(r['probed'])} probed requests, {r['forks']} forks", flush=True)

    out_path = lab_home() / "tas" / "dev-12" / "tas-state-mechanics-probe.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved raw probe data to {out_path}")

    # Analyze & print clean comparisons against tue_decline_4x!
    base = results["tue_decline_4x"]["probed"]
    print("=" * 95)
    print("1. LOSE CLOSE (2.3x) vs DECLINE (4.0x) on Tuesday morning limits:")
    diffs = [
        results["tue_lose_2.3x"]["probed"][rid]["lo"] - base[rid]["lo"]
        for rid in base
        if rid in results["tue_lose_2.3x"]["probed"] and base[rid]["lo"] and results["tue_lose_2.3x"]["probed"][rid]["lo"]
    ]
    print(f"  Compared {len(diffs)} requests: max abs diff = {max(abs(x) for x in diffs) if diffs else None} cents")

    print("=" * 95)
    print("2. COMPETITOR MORNING REACTION vs MONDAY WIN SHARE (Trust=0 isolated!):")
    for cmp_name in ("tue_win_25", "tue_win_50", "tue_win_100"):
        cmp = results[cmp_name]
        by_dlr = defaultdict(list)
        for rid, b in base.items():
            c = cmp["probed"].get(rid)
            if c and b["lo"] and c["lo"]:
                by_dlr[b["dealer"]].append(c["lo"] / b["lo"])
        print(f"  --- {cmp_name} vs 0% Monday win share ---")
        for dlr in sorted(by_dlr, key=lambda d: -cmp["tot_by_dlr"].get(d, 0)):
            ratios = by_dlr[dlr]
            w = cmp["won_by_dlr"].get(dlr, 0)
            t = cmp["tot_by_dlr"].get(dlr, 0)
            print(
                f"    {dlr}: Mon won {w:>2}/{t:<2} ({(w/t if t else 0):5.1%}) | "
                f"n_tue={len(ratios):>2} | Tue limit ratio = {statistics.mean(ratios):.4f} "
                f"(min {min(ratios):.4f}, max {max(ratios):.4f})"
            )

    print("=" * 95)
    print("3. TWO-DAY CUMULATIVE COMPETITOR REACTION (Wed 08:00-09:30: 100% Mon+Tue vs 0% Mon+Tue):")
    wbase = results["wed_decline_4x"]["probed"]
    wcmp = results["wed_win_100"]
    by_dlr_w = defaultdict(list)
    for rid, b in wbase.items():
        c = wcmp["probed"].get(rid)
        if c and b["lo"] and c["lo"]:
            by_dlr_w[b["dealer"]].append(c["lo"] / b["lo"])
    for dlr in sorted(by_dlr_w, key=lambda d: -wcmp["tot_by_dlr"].get(d, 0)):
        ratios = by_dlr_w[dlr]
        w = wcmp["won_by_dlr"].get(dlr, 0)
        t = wcmp["tot_by_dlr"].get(dlr, 0)
        print(
            f"    {dlr}: Mon+Tue won {w:>2}/{t:<2} ({(w/t if t else 0):5.1%}) | "
            f"n_wed={len(ratios):>2} | Wed limit ratio = {statistics.mean(ratios):.4f}"
        )

    print("=" * 95)
    print("4. TRUST (+1%/car) & LATE SATISFACTION PENALTY (tue_trust_and_late vs tue_decline_4x):")
    tl = results["tue_trust_and_late"]
    print("  Monday orders in trust_and_late:", json.dumps(tl["orders"]))
    by_dlr_t = defaultdict(list)
    for rid, b in base.items():
        c = tl["probed"].get(rid)
        if c and b["lo"] and c["lo"]:
            by_dlr_t[b["dealer"]].append((c["lo"] / b["lo"], c["trust"], c["late_count"]))
    for dlr, items in sorted(by_dlr_t.items()):
        w = tl["won_by_dlr"].get(dlr, 0)
        t = tl["tot_by_dlr"].get(dlr, 0)
        ratios = [x[0] for x in items]
        tr = items[0][1]
        lc = items[0][2]
        print(
            f"    {dlr}: Mon won {w:>2}/{t:<2}, Tue trust={tr}, late={lc} | "
            f"n_tue={len(ratios):>2} | Tue limit ratio = {statistics.mean(ratios):.4f}"
        )


if __name__ == "__main__":
    main()
