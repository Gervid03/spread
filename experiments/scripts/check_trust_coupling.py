"""Verify whether high-trust dealers pull global self.mult up on Wed-Fri and crowd out low-trust high-ticket dealers."""
from __future__ import annotations

import csv
import json
import pathlib
from collections import Counter, defaultdict

from spread_lab.geo import Geo

DAY = 1440


def main() -> None:
    rev_root = pathlib.Path("/tmp/cp-wild-rev")
    champ_rows = {r["seed"]: r for r in (json.loads(l) for l in open("champion/results/dev-L8.jsonl"))}
    map_data = json.loads(pathlib.Path("/home/lab/.spread-lab/map.json").read_text())
    geo = Geo(map_data)

    # Track exact dealer trust at the arrival minute of each request (from delivered on-time orders before arr)
    buckets = defaultdict(lambda: [0, 0, 0.0, 0.0])  # quotes, wins, sum_list, sum_q_over_list
    d11_buckets = defaultdict(lambda: [0, 0, 0.0, 0.0])

    for seed, rr in champ_rows.items():
        dd = rev_root / f"reveal-{rr['world']}"
        rqs = {row["id"]: row for row in csv.DictReader(open(dd / "requests.csv"))}
        evs = list(csv.DictReader(open(dd / "events.csv")))

        # Replay ledger events in chronological order alongside requests
        trust_events = []
        late_seen = set()
        for e in evs:
            if e["kind"] == "ledger" and e["line.orderId"] in rqs:
                oid = e["line.orderId"]
                dealer = rqs[oid]["dealerId"]
                at = int(e["at"])
                if e["line.kind"] in ("late_refund", "undelivered_penalty"):
                    trust_events.append((at, 0, oid, dealer, "late"))
                elif e["line.kind"] == "revenue":
                    trust_events.append((at, 1, oid, dealer, "rev"))
        trust_events.sort()

        req_list = sorted(rqs.values(), key=lambda r: int(r["arrivedAt"]))
        trust = Counter()
        ti = 0
        for row in req_list:
            arr = int(row["arrivedAt"])
            while ti < len(trust_events) and trust_events[ti][0] <= arr:
                _, _, oid, dlr, kind = trust_events[ti]
                if kind == "late":
                    late_seen.add(oid)
                    trust[dlr] //= 2
                elif kind == "rev" and oid not in late_seen:
                    trust[dlr] = min(25, trust[dlr] + 1)
                ti += 1

            day = arr // DAY
            if day < 2 or day > 4:
                continue
            avail = [o for o in ("same_day", "next_day", "within_3_days") if row[f"{o}.listPriceCents"]]
            opts = [
                (o, int(row[f"{o}.listPriceCents"]), int(row[f"{o}.quoteCents"]))
                for o in avail
                if row[f"{o}.quoteCents"]
            ]
            if not opts or min(qc / lc for _, lc, qc in opts) >= 3.5:
                continue
            ref = int(row["referenceFeeCents"])
            flr_c = int(ref * 1.25 / 0.92 + 0.5)
            is_flr = any(abs(qc - flr_c) <= 2 for _, _, qc in opts)
            if is_flr:
                continue

            t = trust[row["dealerId"]]
            tb = "trust_0_3" if t <= 3 else ("trust_4_14" if t <= 14 else "trust_15_25")
            lc_eur = opts[0][1] / 100
            m = opts[0][2] / opts[0][1]
            won = row["outcome"] == "won"
            buckets[tb][0] += 1
            buckets[tb][1] += int(won)
            buckets[tb][2] += lc_eur
            buckets[tb][3] += m
            if seed == "dev-11":
                d11_buckets[tb][0] += 1
                d11_buckets[tb][1] += int(won)
                d11_buckets[tb][2] += lc_eur
                d11_buckets[tb][3] += m

    print("=== WED-FRI NORMAL ('quote') WIN RATE & TICKET SIZE BY DEALER TRUST (16 DEV WORLDS) ===")
    for tb in ("trust_0_3", "trust_4_14", "trust_15_25"):
        q, w, sl, sm = buckets[tb]
        print(
            f"  {tb:12s}: quotes={q:4d} ({q/16:5.1f}/wk)  win={w:4d} ({100*w/max(1,q):5.1f}%)  "
            f"avg_list=€{sl/max(1,q):5.1f}  avg_q/list={sm/max(1,q):.3f}"
        )
    print("")
    print("=== DEV-11 WED-FRI BY DEALER TRUST ===")
    for tb in ("trust_0_3", "trust_4_14", "trust_15_25"):
        q, w, sl, sm = d11_buckets[tb]
        print(
            f"  {tb:12s}: quotes={q:4d}  win={w:4d} ({100*w/max(1,q):5.1f}%)  "
            f"avg_list=€{sl/max(1,q):5.1f}  avg_q/list={sm/max(1,q):.3f}"
        )


if __name__ == "__main__":
    main()
