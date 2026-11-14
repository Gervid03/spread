"""Inspect exact candidate hitch pairs (A -> B) in Champion v3 reveals (/tmp/reveals-v3)."""
from __future__ import annotations

import collections
import csv
import json
import math
from pathlib import Path

csv.field_size_limit(10**9)
HOUR, DAY = 60, 24 * 60


def read_csv(folder: Path, name: str) -> list[dict[str, str]]:
    with open(folder / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def pool_tag(s30: int, s55: int) -> str:
    if s30 >= 100:
        return "Cap"
    if s30 >= 30:
        return "Mid"
    if s55 >= 22:
        return "Ring"
    return "Thin"


def main() -> None:
    root = Path("/tmp/reveals-v3")
    for folder in sorted(root.iterdir()):
        if not (folder.is_dir() and folder.name.startswith("reveal-")):
            continue
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in read_csv(folder, "places")}
        line_km = {(a, b): haversine_km(places[a], places[b]) for a in places for b in places}
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in read_csv(folder, "roads")}
        drivers = read_csv(folder, "drivers")
        homes = collections.Counter(d["homePlaceId"] for d in drivers)
        s30 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 30.0) for p in places}
        s55 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 55.0) for p in places}
        s70 = {p: sum(n for h, n in homes.items() if line_km[(p, h)] <= 70.0) for p in places}

        requests = {r["id"]: r for r in read_csv(folder, "requests")}
        legs_by_req = collections.defaultdict(list)
        for l in read_csv(folder, "legs"):
            legs_by_req[l["requestId"]].append(l)
        for rid in legs_by_req:
            legs_by_req[rid].sort(key=lambda x: int(x["leg"]))
        gigs = {g["id"]: g for g in read_csv(folder, "gigs")}
        events = read_csv(folder, "events")

        open_since = {gid: int(g["postedAt"]) for gid, g in gigs.items()}
        gig_intervals = collections.defaultdict(list)
        won_orders = {}
        for e in events:
            k, at = e["kind"], int(e["at"])
            if k == "order_won":
                oid = e["order.id"]
                lrows = legs_by_req[oid]
                won_orders[oid] = {
                    "id": oid,
                    "won_at": at,
                    "option": e["order.option"],
                    "deadline": int(e["order.deadline"]),
                    "legs": lrows,
                    "pickup": lrows[0]["pickup.placeId"],
                    "delivery": lrows[-1]["delivery.placeId"],
                    "ready": max(at, int(lrows[0]["pickup.window.from"])),
                    "drive": sum(roads[(l["pickup.placeId"], l["delivery.placeId"])][1] for l in lrows),
                }
            elif k == "gig_booked":
                gid = e["gigId"]
                if gid in open_since:
                    gig_intervals[gid].append((open_since.pop(gid), at))
            elif k in ("gig_dropped", "no_show"):
                open_since[e["gigId"]] = at
            elif k == "gig_expired":
                gid = e["gigId"]
                if gid in open_since:
                    gig_intervals[gid].append((open_since.pop(gid), at))
        for gid, t0 in open_since.items():
            gig_intervals[gid].append((t0, t0 + 60 if gigs[gid]["status"] == "withdrawn" else 10080))

        single_gig_info = {}
        for gid, g in gigs.items():
            stops = json.loads(g["stops"])
            oids = list(dict.fromkeys(s["orderId"] for s in stops))
            if len(oids) == 1 and len(stops) == 2 and oids[0] in won_orders:
                single_gig_info[gid] = won_orders[oids[0]]

        def open_at(t: int):
            out, seen = [], set()
            for gid, wo in single_gig_info.items():
                for a, b in gig_intervals[gid]:
                    if a <= t < b and wo["id"] not in seen:
                        seen.add(wo["id"])
                        out.append(wo)
                        break
            return out

        pair_patterns = collections.Counter()
        roundtrip_patterns = collections.Counter()
        for oid, wo in sorted(won_orders.items(), key=lambda x: x[1]["won_at"]):
            if len(wo["legs"]) != 1:
                continue
            t = wo["won_at"]
            for other in open_at(t):
                if other["id"] == oid:
                    continue
                # Pick ordering with more drivers at A.pickup
                cands = []
                for A, B in ((other, wo), (wo, other)):
                    if line_km[(A["delivery"], B["pickup"])] <= 15.0:
                        dh = roads[(A["delivery"], B["pickup"])][1]
                        if A["drive"] + dh + B["drive"] <= 12 * HOUR:
                            t1 = max(t, A["ready"]) + A["drive"]
                            t2 = max(B["ready"], t1 + dh) + B["drive"]
                            if t1 + 150 <= A["deadline"] and t2 + 150 <= B["deadline"]:
                                cands.append((s30[A["pickup"]], A, B))
                if not cands:
                    continue
                cands.sort(key=lambda x: x[0], reverse=True)
                _, A, B = cands[0]
                if s30[A["pickup"]] < s30[B["pickup"]]:
                    continue
                pa = pool_tag(s30[A["pickup"]], s55[A["pickup"]])
                da = pool_tag(s30[A["delivery"]], s55[A["delivery"]])
                pb = pool_tag(s30[B["pickup"]], s55[B["pickup"]])
                db = pool_tag(s30[B["delivery"]], s55[B["delivery"]])
                is_rt = line_km[(B["delivery"], A["pickup"])] <= 30.0
                pair_patterns[f"{pa}->{da} + {pb}->{db} (rt={is_rt})"] += 1
                if da != "Cap":
                    roundtrip_patterns[f"{pa}->{da} ({A['option']}) + {pb}->{db} ({B['option']}) rt={is_rt}"] += 1
                break

        print(f"=== {folder.name} ===")
        for k, v in pair_patterns.most_common(12):
            print(f"  {v:>3}  {k}")
        print("  --- Non-Cap middle hub (da != Cap): ---")
        for k, v in roundtrip_patterns.most_common(10):
            print(f"  {v:>3}  {k}")

        # Also check batch multiplicity of hitch_quote!
        ts_counts = collections.Counter()
        partner_load = collections.Counter()
        for rid, req in sorted(requests.items(), key=lambda x: int(x[1]["arrivedAt"])):
            lrows = legs_by_req[rid]
            if len(lrows) != 1:
                continue
            pk, dlv = lrows[0]["pickup.placeId"], lrows[0]["delivery.placeId"]
            drv = roads[(pk, dlv)][1]
            if s55[pk] >= 22 or (s70[pk] >= 30 and drv <= 220) or (s30[dlv] >= 200 and drv <= 180):
                continue
            slow_opts = [int(req[f"{opt}.deadline"]) for opt in ("next_day", "within_3_days") if req.get(f"{opt}.deadline")]
            if not slow_opts:
                continue
            t_arr = int(req["arrivedAt"])
            ready_r = max(t_arr, int(lrows[0]["pickup.window.from"]))
            best_dl = max(slow_opts)
            if best_dl - ready_r - drv < 150 + 0.75 * drv:
                continue
            partners = []
            for other in open_at(t_arr):
                if line_km[(other["delivery"], pk)] <= 15.0 and s30[other["pickup"]] >= s30[pk]:
                    dh = roads[(other["delivery"], pk)][1]
                    if other["drive"] + dh + drv <= 12 * HOUR:
                        t1 = max(t_arr, other["ready"]) + other["drive"]
                        t2 = max(ready_r, t1 + dh) + drv
                        if t1 + 150 <= other["deadline"] and t2 + 150 <= best_dl:
                            partners.append(other["id"])
            if partners:
                ts_counts[t_arr] += 1
                partner_load[partners[0]] += 1
        print(f"  hitch_quote max requests at same timestamp={max(ts_counts.values(), default=0)}, max requests matching same waiting gig={max(partner_load.values(), default=0)}")


if __name__ == "__main__":
    main()
