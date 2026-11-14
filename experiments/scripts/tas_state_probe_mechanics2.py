"""Part 2 of controlled fork probes on dev-12 (~25s):
1. Exact competitor win-share thresholds on D01 Monday (30%, 35%, 40%, 55%, 65%, 75%).
2. Exact cumulative competitor step cap by Friday morning (0% Mon..Thu vs 100% Mon..Thu).
3. Exact Late-Car Satisfaction + Trust-Halving penalty on D01 (7 on-time vs 6 on-time + 1 delivered <2h late vs 6 on-time + 1 undelivered past deadline).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import tas  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402
from spread_lab.runner import DAY  # noqa: E402


def pick_probe_option(req: dict) -> str:
    kinds = [o["kind"] for o in req["options"]]
    return "next_day" if "next_day" in kinds else kinds[0]


def probe_d01_share(target_wins: int, probe_day: int = 1) -> dict:
    """Win exactly `target_wins` slow requests of D01 (and D02) per day before probe_day, hold gigs, probe at 08:00..09:30."""
    probe_start = probe_day * DAY + 8 * 60
    probe_end = probe_day * DAY + 9 * 60 + 30
    day_dlr_won = Counter()
    probed = {}
    with tas.Tas("dev-12", name=f"tas-state-sh{target_wins}-d{probe_day}", forks=True) as g:
        g.desk.post = lambda *a, **kw: None  # type: ignore[method-assign]

        def hook(game: tas.Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            now = game.desk.now
            d = now // DAY
            if now < probe_start:
                for i in fresh:
                    rid = out[i]["requestId"]
                    req = game.desk.requests[rid]
                    dlr = req["dealerId"]
                    opts = {o["kind"]: o["listPriceCents"] for o in req["options"]}
                    # Keep deadline after probe_end! On Mon..Wed use within_3_days or Fri-due if probe_day==4
                    if probe_day == 1:
                        slow_k = "within_3_days" if "within_3_days" in opts else ("next_day" if "next_day" in opts else None)
                    else:
                        # For probe_day=4 (Fri), we can even let normal Desk staff them if needed, or check if held orders past deadline change anything!
                        slow_k = "within_3_days" if "within_3_days" in opts else ("next_day" if "next_day" in opts else list(opts)[0])
                    if dlr in ("D01", "D02") and slow_k and day_dlr_won[(d, dlr)] < target_wins:
                        day_dlr_won[(d, dlr)] += 1
                        out[i] = {"type": "quote", "requestId": rid, "prices": {slow_k: int(opts[slow_k] * 0.45)}}
                    else:
                        k0 = req["options"][0]["kind"]
                        out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                return out
            if probe_start <= now <= probe_end:
                quotes = [out[i] for i in fresh]
                targets = {a["requestId"]: pick_probe_option(game.desk.requests[a["requestId"]]) for a in quotes}
                res = tas.probe_prices(game, quotes, targets, lo_x=0.45, hi_x=2.8, iters=11, tol=10)
                for rid, st in res.items():
                    req = game.desk.requests[rid]
                    probed[rid] = {"dealer": req["dealerId"], "trust": game.desk.dealer_trust.get(req["dealerId"], 0), **st}
                for i in fresh:
                    rid = out[i]["requestId"]
                    k0 = game.desk.requests[rid]["options"][0]["kind"]
                    out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(game.desk.requests[rid]["options"][0]["listPriceCents"] * 4.0)}}
            return out

        g.hook = hook
        g.play_to(probe_end + 5)
        won = sum(1 for rid, req in g.desk.requests.items() if req["dealerId"] == "D01" and req["arrivedAt"] < probe_start and g.outcome.get(rid, ("?",))[0] == "won")
        tot = sum(1 for rid, req in g.desk.requests.items() if req["dealerId"] == "D01" and req["arrivedAt"] < probe_start)
        return {"won": won, "tot": tot, "forks": g.forks, "probed": probed}


def probe_late_satisfaction(mode: str) -> dict:
    """On D01 Monday: win exact same 7 Mon-20:00 same_day cars:
    - 'all_ontime': deliver all 7 on time (trust=7)
    - 'last_late_1h': deliver first 6 on time (trust=6), hold 7th ('R00111') until 19:50 Mon so it delivers ~20:45 Mon (<2h late! trust 6->3 + satisfaction hit!)
    - 'first_late_1h': hold 1st ('R00065') until 19:50 Mon, deliver other 6 before it -> wait: R00065 delivers ~20:45 Mon AFTER the other 6 delivered! Wait: to isolate satisfaction WITHOUT trust diff, deliver R00065 late (~20:45 Mon) when trust=0 (NO other cars won, just 1/46 won and delivered 45m late!!)!
    - 'one_ontime': win ONLY R00065 (1/46) and deliver on time (trust=1)!
    - 'one_late_1h': win ONLY R00065 (1/46) and deliver ~20:45 Mon (<2h late, trust=0)!
    - 'one_undeliv': win ONLY R00065 (1/46) and never post gig (still undelivered at Tue 08:30, past Mon 20:00 deadline, trust=0)!
    """
    probe_start = 1 * DAY + 8 * 60
    probe_end = 1 * DAY + 9 * 60 + 30
    delayed: list[tuple[int, dict]] = []
    probed = {}

    with tas.Tas("dev-12", name=f"tas-state-sat-{mode}", forks=True) as g:
        orig_post = g.desk.post

        def custom_post(order, legs, retry=None, allow_pair=True):
            if mode == "one_undeliv":
                return
            if mode == "one_late_1h" and order["id"] == "R00065":
                delayed.append((19 * 60 + 50, order))
                return
            if retry is None:
                orig_post(order, legs, allow_pair=allow_pair)
            else:
                orig_post(order, legs, retry, allow_pair=allow_pair)

        g.desk.post = custom_post  # type: ignore[method-assign]
        orig_tick = g.desk.tick

        def custom_tick():
            orig_tick()
            for at_m, o in list(delayed):
                if g.desk.now >= at_m:
                    delayed.remove((at_m, o))
                    g.desk.urgent.add(o["id"])
                    orig_post(o, [0], allow_pair=False)

        g.desk.tick = custom_tick  # type: ignore[method-assign]

        def hook(game: tas.Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            now = game.desk.now
            if now < probe_start:
                for i in fresh:
                    rid = out[i]["requestId"]
                    req = game.desk.requests[rid]
                    opts = {o["kind"]: o["listPriceCents"] for o in req["options"]}
                    if rid == "R00065":
                        out[i] = {"type": "quote", "requestId": rid, "prices": {"same_day": int(opts["same_day"] * 0.55)}}
                    else:
                        k0 = req["options"][0]["kind"]
                        out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                return out
            if probe_start <= now <= probe_end:
                quotes = [out[i] for i in fresh]
                targets = {a["requestId"]: pick_probe_option(game.desk.requests[a["requestId"]]) for a in quotes}
                res = tas.probe_prices(game, quotes, targets, lo_x=0.45, hi_x=2.8, iters=11, tol=10)
                for rid, st in res.items():
                    req = game.desk.requests[rid]
                    probed[rid] = {"dealer": req["dealerId"], "trust": game.desk.dealer_trust.get(req["dealerId"], 0), **st}
                for i in fresh:
                    rid = out[i]["requestId"]
                    k0 = game.desk.requests[rid]["options"][0]["kind"]
                    out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(game.desk.requests[rid]["options"][0]["listPriceCents"] * 4.0)}}
            return out

        g.hook = hook
        g.play_to(probe_end + 5)
        o65 = g.desk.orders.get("R00065", {})
        return {
            "mode": mode,
            "deliveredAt": o65.get("deliveredAt"),
            "deadline": o65.get("deadline"),
            "ledger": dict(g.ledger),
            "trust_d01": g.desk.dealer_trust.get("D01", 0),
            "probed": probed,
        }


def probe_fri_cap(win_all: bool) -> dict:
    """Play Mon..Thu normal desk staffing with 0% quotes vs ~95% quotes on D01/D02, probe Fri 08:00..09:30."""
    probe_start = 4 * DAY + 8 * 60
    probe_end = 4 * DAY + 9 * 60 + 30
    probed = {}
    with tas.Tas("dev-12", name=f"tas-state-fricap-{int(win_all)}", forks=True) as g:
        # Hold gigs AND shift won orders? Wait: if we hold gigs past Mon..Thu deadlines, undelivered orders might affect satisfaction!
        # Let's check `one_undeliv` first; here let's ONLY win Friday-deadline orders? No, slow options on Mon..Wed expire before Fri!
        # Instead, let's test Wed->Thu (3 days: Mon+Tue+Wed -> Thu 08:00..09:30) using normal staffing on ultra-safe hub next_day/3day, OR check `one_undeliv`!
        g.desk.post = lambda *a, **kw: None  # type: ignore[method-assign]

        def hook(game: tas.Tas, actions: list, fresh: list) -> list:
            out = list(actions)
            now = game.desk.now
            if now < probe_start:
                for i in fresh:
                    rid = out[i]["requestId"]
                    req = game.desk.requests[rid]
                    opts = {o["kind"]: o["listPriceCents"] for o in req["options"]}
                    if win_all and req["dealerId"] in ("D01", "D02"):
                        slow_k = "within_3_days" if "within_3_days" in opts else ("next_day" if "next_day" in opts else list(opts)[0])
                        out[i] = {"type": "quote", "requestId": rid, "prices": {slow_k: int(opts[slow_k] * 0.40)}}
                    else:
                        k0 = req["options"][0]["kind"]
                        out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(opts[k0] * 4.0)}}
                return out
            if probe_start <= now <= probe_end:
                quotes = [out[i] for i in fresh]
                targets = {a["requestId"]: pick_probe_option(game.desk.requests[a["requestId"]]) for a in quotes}
                res = tas.probe_prices(game, quotes, targets, lo_x=0.35, hi_x=2.8, iters=11, tol=10)
                for rid, st in res.items():
                    req = game.desk.requests[rid]
                    probed[rid] = {"dealer": req["dealerId"], **st}
                for i in fresh:
                    rid = out[i]["requestId"]
                    k0 = game.desk.requests[rid]["options"][0]["kind"]
                    out[i] = {"type": "quote", "requestId": rid, "prices": {k0: int(game.desk.requests[rid]["options"][0]["listPriceCents"] * 4.0)}}
            return out

        g.hook = hook
        g.play_to(probe_end + 5)
        return {"probed": probed, "forks": g.forks}


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    d12 = lab_home() / "tas" / "dev-12"
    base = json.loads((d12 / "tas-state-mechanics-probe.json").read_text(encoding="utf-8"))["tue_decline_4x"]["probed"]

    print("=== A. EXACT MONDAY WIN-SHARE CUTOFFS ON D01 (46 Mon reqs) ===")
    # Test 14/46 (30.4%), 16/46 (34.8%), 19/46 (41.3%), 26/46 (56.5%), 30/46 (65.2%), 34/46 (73.9%)
    share_res = {}
    for w in (14, 16, 19, 26, 30, 34):
        r = probe_d01_share(w, probe_day=1)
        share_res[w] = r
        r220 = r["probed"]["R00220"]["lo"] / base["R00220"]["lo"]
        r224 = r["probed"]["R00224"]["lo"] / base["R00224"]["lo"]
        print(f"  target={w:>2}: D01 won {r['won']:>2}/{r['tot']} ({r['won']/r['tot']:5.1%}) -> R00220={r220:.4f}, R00224={r224:.4f}")

    print("=== B. SINGLE-CAR ON-TIME vs LATE (<2h) vs UNDELIVERED PAST DEADLINE ON D01 ===")
    sat_res = {}
    for m in ("one_ontime", "one_late_1h", "one_undeliv"):
        r = probe_late_satisfaction(m)
        sat_res[m] = r
        r220 = r["probed"]["R00220"]["lo"] / base["R00220"]["lo"]
        r224 = r["probed"]["R00224"]["lo"] / base["R00224"]["lo"]
        print(
            f"  {m:<14}: deliv={r['deliveredAt']} dl={r['deadline']} trust={r['trust_d01']} "
            f"ledger={r['ledger']} -> R00220={r220:.4f} ({r['probed']['R00220']['lo']}), R00224={r224:.4f} ({r['probed']['R00224']['lo']})"
        )

    print("=== C. 4-MORNING CUMULATIVE COMPETITOR SPREAD ON FRIDAY MORNING ===")
    f0 = probe_fri_cap(False)
    f1 = probe_fri_cap(True)
    for rid in sorted(f0["probed"]):
        b = f0["probed"][rid]
        c = f1["probed"].get(rid)
        if b.get("lo") and c and c.get("lo") and b["dealer"] in ("D01", "D02"):
            print(f"  {rid} {b['dealer']}: 0%_lo={b['lo']} vs 100%_lo={c['lo']} -> ratio={c['lo']/b['lo']:.4f}")

    (d12 / "tas-state-mechanics-probe2.json").write_text(
        json.dumps({"shares": share_res, "satisfaction": sat_res, "fri_0": f0, "fri_1": f1}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
