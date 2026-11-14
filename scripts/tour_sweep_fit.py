"""What sets the fee drivers accept for a closed tour? Reads ~/.spread-lab/coplay/tour-sweep.jsonl (and tas-routes'
dev-12 bisections when present), prints group summaries and a least-squares fit of the lowest booked multiple of the
summed typical fee on the tour's features.      uv run python scripts/tour_sweep_fit.py
"""
import json
import math
from collections import defaultdict
from pathlib import Path

rows = []
p = Path.home() / ".spread-lab/coplay/tour-sweep.jsonl"
for line in p.read_text(encoding="utf-8").splitlines() if p.exists() else []:
    r = json.loads(line)
    m = r["min_mult"]
    if isinstance(m, (int, float)):
        r["y"], r["censored"] = float(m), ""
    elif isinstance(m, str) and m.startswith("<="):
        r["y"], r["censored"] = float(m[2:]), "low"
    elif isinstance(m, str) and m.startswith(">"):
        r["y"], r["censored"] = float(m[1:]), "high"
    else:
        continue
    rows.append(r)
print(f"{len(rows)} probed cycles ({sum(1 for r in rows if r['censored'] == 'high')} not booked even at the top, "
      f"{sum(1 for r in rows if r['censored'] == 'low')} booked at the bottom)")


def summary(key, f):
    g = defaultdict(list)
    for r in rows:
        if r["censored"] != "high":
            g[f(r)].append(r["y"])
    print(f"\n{key}: n · median · mean of the lowest booked multiple")
    for k in sorted(g, key=lambda k: (str(type(k)), k)):
        v = sorted(g[k])
        print(f"  {k!s:<16} {len(v):>3}  {v[len(v) // 2]:.3f}  {sum(v) / len(v):.3f}")


summary("cars", lambda r: r["cars"])
summary("road hours", lambda r: min(12, r["road_min"] // 120 * 2))
summary("start drivers", lambda r: "<40" if r["start_supply"] < 40 else "40-150" if r["start_supply"] < 150 else "150+")
summary("closes within km", lambda r: "<=10" if r["close_km"] <= 10 else "10-30" if r["close_km"] <= 30 else ">30")
summary("deadhead share", lambda r: round(r["deadhead_min"] / max(1, r["road_min"]), 1))
summary("hour", lambda r: r["hour"] // 3 * 3)
summary("weekday", lambda r: "MTWTF"[r["day"]] if r["day"] < 5 else r["day"])
summary("lead hours", lambda r: "<12" if r["lead_h"] < 12 else "12-24" if r["lead_h"] < 24 else "24-48" if r["lead_h"] < 48 else "48+")
summary("all slow options", lambda r: all(o != "same_day" for o in r["options"]))

# least squares: y ~ 1 + road_h + 1/road_h + cars + log(start drivers) + deadhead share + lead_h/24 + hour/24
X, Y = [], []
for r in rows:
    if r["censored"] == "high":
        continue
    rh = max(0.5, r["road_min"] / 60)
    X.append([1.0, rh, 1 / rh, r["cars"], math.log(1 + r["start_supply"]), r["deadhead_min"] / max(1, r["road_min"]),
              min(4, r["lead_h"] / 24), r["hour"] / 24])
    Y.append(r["y"])
names = ["const", "road_h", "1/road_h", "cars", "log(drivers)", "deadhead_share", "lead_days", "hour/24"]
if len(Y) > len(names) + 3:
    k = len(names)
    A = [[sum(x[i] * x[j] for x in X) for j in range(k)] for i in range(k)]
    b = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(k)]
    for i in range(k):  # Gauss-Jordan
        piv = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[piv], b[i], b[piv] = A[piv], A[i], b[piv], b[i]
        d = A[i][i] or 1e-9
        A[i] = [v / d for v in A[i]]
        b[i] /= d
        for r in range(k):
            if r != i:
                f = A[r][i]
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    pred = [sum(bi * xi for bi, xi in zip(b, x)) for x in X]
    ss = sum((y - q) ** 2 for y, q in zip(Y, pred))
    st = sum((y - sum(Y) / len(Y)) ** 2 for y in Y)
    print(f"\nleast squares on {len(Y)} tours (R² {1 - ss / st:.2f}, residual sd {math.sqrt(ss / len(Y)):.3f}):")
    for n_, c in zip(names, b):
        print(f"  {n_:<15} {c:+.4f}")
