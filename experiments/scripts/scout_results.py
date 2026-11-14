"""What a set of result lines says without any reveal: one row per world, the correlations between
the counters, and how much of the driver fees goes with expired and warned gigs.

    uv run python experiments/scripts/scout_results.py                       # the champion's dev and holdout
    uv run python experiments/scripts/scout_results.py runs/<folder>/results.jsonl ...

Standard library only. Read-only: it plays no world."""
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
paths = [Path(p) for p in sys.argv[1:]] or sorted((REPO / "champion" / "results").glob("*-L8.jsonl"))
rows = sorted((json.loads(line) for p in paths for line in p.read_text(encoding="utf-8").splitlines() if line.strip()),
              key=lambda r: r["seed"])
rows = [r for r in rows if r.get("won")]


def g(d, k):
    return d.get(k, 0)


def late(r):
    return round(r["won"] * (1 - r["on_time"]))


print(f"{len(rows)} worlds from {', '.join(p.name for p in paths)}\n")
head = ("seed", "margin", "won", "on_time", "late", "rev/ord", "fee/ord", "fee/rev", "warned", "expired", "drops",
        "ring", "same", "next", "3day", "floor", "quote", "decline", "no_same", "not_ready", "no_plates", "closed", "refund")
print(" ".join(f"{h:>9}" for h in head))
for r in rows:
    s, l, won = r["stats"], r["ledger"], r["won"]
    cells = (r["seed"], round(r["margin"]), won, f"{r['on_time']:.3f}", late(r), round(r["revenue"] / won, 1),
             round(-l["driver_fee"] / won, 1), round(-l["driver_fee"] / r["revenue"], 2), g(s, "deadline_close"),
             g(s, "gig_expired"), g(s, "gig_dropped"), g(s, "won_ring"), g(s, "won_same_day"), g(s, "won_next_day"),
             g(s, "won_within_3_days"), g(s, "quote_floor"), g(s, "quote_quote"), g(s, "quote_decline"),
             g(s, "dropped_same_day_supply"), g(s, "visit_failed_not_ready"), g(s, "visit_failed_no_plates"),
             g(s, "visit_failed_closed"), round(g(l, "late_refund")))
    print(" ".join(f"{c:>9}" for c in cells))

print("\nMeans per world")
for kind in ("revenue", "driver_fee", "late_refund", "undelivered_penalty", "failed_visit", "waiting", "fine", "release_fee"):
    print(f"  {kind:<20} {st.mean(g(r['ledger'], kind) for r in rows):>10,.0f}")
for key in ("deadline_close", "gig_expired", "gig_dropped", "booked"):
    print(f"  {key:<20} {st.mean(g(r['stats'], key) for r in rows):>10.1f}")
print(f"  {'late orders':<20} {st.mean(late(r) for r in rows):>10.1f}")
quoted = sum(g(r["stats"], "quote_quote") + g(r["stats"], "quote_floor") for r in rows)
print(f"  wins / (normal + floor quotes) = {sum(r['won'] for r in rows) / quoted:.3f}")

features = {
    "margin": lambda r: r["margin"],
    "won": lambda r: r["won"],
    "late": late,
    "on_time": lambda r: r["on_time"],
    "fee/ord": lambda r: -r["ledger"]["driver_fee"] / r["won"],
    "fee/rev": lambda r: -r["ledger"]["driver_fee"] / r["revenue"],
    "rev/ord": lambda r: r["revenue"] / r["won"],
    "warned": lambda r: g(r["stats"], "deadline_close"),
    "expired": lambda r: g(r["stats"], "gig_expired"),
    "drops": lambda r: g(r["stats"], "gig_dropped"),
    "same": lambda r: g(r["stats"], "won_same_day"),
    "ring": lambda r: g(r["stats"], "won_ring"),
    "floor": lambda r: g(r["stats"], "quote_floor"),
}


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sx, sy = sum((x - mx) ** 2 for x in xs) ** .5, sum((y - my) ** 2 for y in ys) ** .5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else 0.0


if len(rows) >= 8:
    names = list(features)
    cols = {n: [features[n](r) for r in rows] for n in names}
    print("\nCorrelations between worlds")
    print(" " * 8 + " ".join(f"{n:>7}" for n in names))
    for a in names:
        print(f"{a:>7} " + " ".join(f"{corr(cols[a], cols[b]):7.2f}" for b in names))


def ols(X, y):
    """Least squares by the normal equations (a handful of columns)."""
    n = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) for j in range(n)] for i in range(n)]
    b = [sum(r[i] * v for r, v in zip(X, y)) for i in range(n)]
    for i in range(n):
        p = A[i][i]
        A[i] = [v / p for v in A[i]]
        b[i] /= p
        for k in range(n):
            if k != i:
                f = A[k][i]
                A[k] = [v - f * w for v, w in zip(A[k], A[i])]
                b[k] -= f * b[i]
    return b


if len(rows) >= 12:
    X = [[1, r["revenue"] / r["won"], g(r["stats"], "gig_expired") / r["won"],
          (g(r["stats"], "deadline_close") - g(r["stats"], "gig_expired")) / r["won"], g(r["stats"], "gig_dropped") / r["won"]] for r in rows]
    y = [-r["ledger"]["driver_fee"] / r["won"] for r in rows]
    c = ols(X, y)
    expired = st.mean(g(r["stats"], "gig_expired") for r in rows)
    print("\nDriver fee per order, least squares over the worlds (euros):")
    print(f"  {c[0]:.1f} + {c[1]:.3f} x revenue per order + {c[2]:.0f} per expired gig per order"
          f" + {c[3]:.0f} per other warned order per order + {c[4]:.0f} per drop per order")
    print(f"  => {c[2]:.0f} more fee per expired gig; at {expired:.1f} expired gigs a world: {c[2] * expired:,.0f} a world")
    print("  (between worlds, so a lead to confirm with per-order fees from a reveal, not a result)")
