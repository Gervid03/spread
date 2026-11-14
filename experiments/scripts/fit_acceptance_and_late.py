"""Part 1 (c3 / R8 / Idea 28): Fit logistic acceptance (won) and lateness (late) models on revealed L8 worlds.

Pure Python implementation using exact block-eliminated (Schur complement) Newton-Raphson / IRLS
for arbitrary numbers of (world, day) fixed effects, giving exact MLE / MAP estimates and exact
asymptotic standard errors for all structural covariates.
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

CACHE_ROOT = Path("/home/lab/.gemini/tmp/d14-02-acceptance-model/reveals")
OPTS = ("same_day", "next_day", "within_3_days")


def solve_spd(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    """Solve A X = B for symmetric positive-definite p x p matrix A and p x m RHS B via Cholesky."""
    p = len(A)
    m = len(B[0])
    L = [[0.0] * p for _ in range(p)]
    for i in range(p):
        Li = L[i]
        Ai = A[i]
        for j in range(i):
            Lj = L[j]
            s = Ai[j]
            for k in range(j):
                s -= Li[k] * Lj[k]
            Li[j] = s / Lj[j]
        s = Ai[i]
        for k in range(i):
            s -= Li[k] * Li[k]
        if s <= 1e-12:
            s = 1e-12
        Li[i] = math.sqrt(s)

    # Forward substitution: L Y = B
    Y = [[0.0] * m for _ in range(p)]
    for i in range(p):
        Li = L[i]
        Lii = Li[i]
        Bi = B[i]
        Yi = Y[i]
        for col in range(m):
            s = Bi[col]
            for k in range(i):
                s -= Li[k] * Y[k][col]
            Yi[col] = s / Lii

    # Backward substitution: L^T X = Y
    X = [[0.0] * m for _ in range(p)]
    for i in range(p - 1, -1, -1):
        Lii = L[i][i]
        Xi = X[i]
        Yi = Y[i]
        for col in range(m):
            s = Yi[col]
            for k in range(i + 1, p):
                s -= L[k][i] * X[k][col]
            Xi[col] = s / Lii
    return X


def invert_spd(A: list[list[float]]) -> list[list[float]]:
    p = len(A)
    I = [[1.0 if i == j else 0.0 for j in range(p)] for i in range(p)]
    return solve_spd(A, I)


def fit_logistic_fe(
    rows_x: list[list[tuple[int, float]]],
    rows_y: list[int],
    rows_g: list[int],
    n_params: int,
    n_groups: int,
    l2_theta: float = 1e-6,
    l2_group: float = 1e-4,
    max_iter: int = 25,
    tol: float = 1e-7,
) -> tuple[list[float], list[float], list[list[float]], float]:
    """Fit logit P(y=1) = x_i^T theta + gamma_{g(i)} via exact Schur-complement IRLS.

    rows_x uses sparse [(col_idx, val), ...] per observation so dot products and Hessian
    accumulation take ~10 ops per row instead of p^2 ops per row!
    Returns (theta, gamma, cov_theta, log_likelihood).
    """
    n = len(rows_y)
    theta = [0.0] * n_params
    gamma = [0.0] * n_groups if n_groups > 0 else []

    # Initialize gamma_g or theta[0] near empirical log-odds
    mean_y = max(1e-4, min(1.0 - 1e-4, sum(rows_y) / max(1, n)))
    init_lo = math.log(mean_y / (1.0 - mean_y))
    if n_groups > 0:
        gamma = [init_lo] * n_groups

    cov_theta = [[0.0] * n_params for _ in range(n_params)]
    ll = 0.0

    for it in range(max_iter):
        A = [[0.0] * n_params for _ in range(n_params)]
        for j in range(n_params):
            A[j][j] = l2_theta
        g_theta = [-l2_theta * theta[j] for j in range(n_params)]

        if n_groups > 0:
            D = [l2_group] * n_groups
            g_gamma = [-l2_group * gamma[g] for g in range(n_groups)]
            B = [[0.0] * n_params for _ in range(n_groups)]
        else:
            D = []
            g_gamma = []
            B = []

        ll = 0.0
        for i in range(n):
            xi = rows_x[i]
            yi = rows_y[i]
            eta = gamma[rows_g[i]] if n_groups > 0 else 0.0
            for c, v in xi:
                eta += theta[c] * v
            if eta > 30.0:
                p = 1.0 - 1e-13
                ll += yi * eta - eta
            elif eta < -30.0:
                p = 1e-13
                ll += yi * eta
            else:
                ep = math.exp(eta)
                p = ep / (1.0 + ep)
                ll += yi * eta - math.log1p(ep)
            r = yi - p
            w = max(p * (1.0 - p), 1e-12)

            if n_groups > 0:
                gi = rows_g[i]
                D[gi] += w
                g_gamma[gi] += r
                Bgi = B[gi]
                for c, v in xi:
                    Bgi[c] += w * v

            for idx1 in range(len(xi)):
                c1, v1 = xi[idx1]
                g_theta[c1] += r * v1
                wv1 = w * v1
                Ac1 = A[c1]
                Ac1[c1] += wv1 * v1
                for idx2 in range(idx1 + 1, len(xi)):
                    c2, v2 = xi[idx2]
                    val = wv1 * v2
                    Ac1[c2] += val
                    A[c2][c1] += val

        if n_groups > 0:
            # Schur complement S = A - B^T D^{-1} B, rhs = g_theta - B^T D^{-1} g_gamma
            S = [row[:] for row in A]
            rhs = g_theta[:]
            for g in range(n_groups):
                inv_dg = 1.0 / D[g]
                Bg = B[g]
                gg = g_gamma[g] * inv_dg
                nz = [(c, Bg[c]) for c in range(n_params) if Bg[c] != 0.0]
                for idx1 in range(len(nz)):
                    c1, b1 = nz[idx1]
                    rhs[c1] -= b1 * gg
                    b1_inv = b1 * inv_dg
                    Sc1 = S[c1]
                    Sc1[c1] -= b1_inv * b1
                    for idx2 in range(idx1 + 1, len(nz)):
                        c2, b2 = nz[idx2]
                        val = b1_inv * b2
                        Sc1[c2] -= val
                        S[c2][c1] -= val
            d_theta_mat = solve_spd(S, [[x] for x in rhs])
            d_theta = [d_theta_mat[j][0] for j in range(n_params)]
            d_gamma = [0.0] * n_groups
            for g in range(n_groups):
                s = g_gamma[g]
                Bg = B[g]
                for c in range(n_params):
                    if Bg[c] != 0.0:
                        s -= Bg[c] * d_theta[c]
                d_gamma[g] = s / D[g]
        else:
            S = A
            d_theta_mat = solve_spd(S, [[x] for x in g_theta])
            d_theta = [d_theta_mat[j][0] for j in range(n_params)]
            d_gamma = []

        max_step = max(max((abs(x) for x in d_theta), default=0.0), max((abs(x) for x in d_gamma), default=0.0))
        # Clamp extreme initial Newton step if > 5.0
        scale = min(1.0, 5.0 / max_step) if max_step > 5.0 else 1.0
        for j in range(n_params):
            theta[j] += scale * d_theta[j]
        for g in range(n_groups):
            gamma[g] += scale * d_gamma[g]

        if max_step < tol:
            cov_theta = invert_spd(S)
            break
    else:
        cov_theta = invert_spd(S)

    return theta, gamma, cov_theta, ll


def load_world_data(entry: dict) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Extract all non-decline quote records and all won order records for one revealed world."""
    d = Path(entry["dir"])
    wid = entry["world"]
    seed = entry["seed"]
    version = entry["version"]

    with open(d / "places.csv", encoding="utf-8", newline="") as f:
        places = {p["id"]: (float(p["lat"]), float(p["lon"])) for p in csv.DictReader(f)}
    with open(d / "roads.csv", encoding="utf-8", newline="") as f:
        roads = {(r["from"], r["to"]): (float(r["km"]), int(r["minutes"])) for r in csv.DictReader(f)}
    with open(d / "drivers.csv", encoding="utf-8", newline="") as f:
        drivers = list(csv.DictReader(f))
    with open(d / "legs.csv", encoding="utf-8", newline="") as f:
        legs_raw = list(csv.DictReader(f))
    with open(d / "requests.csv", encoding="utf-8", newline="") as f:
        reqs = list(csv.DictReader(f))
    with open(d / "events.csv", encoding="utf-8", newline="") as f:
        events = list(csv.DictReader(f))

    # Compute 30km and 55km supply per place for this world
    def hav(a: tuple[float, float], b: tuple[float, float]) -> float:
        la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
        h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
        return 6371.0 * 2.0 * math.asin(math.sqrt(h))

    homes = Counter(dr["homePlaceId"] for dr in drivers)
    supply30 = {p: sum(n for h, n in homes.items() if hav(places[p], places[h]) <= 30.0) for p in places}
    supply55 = {p: sum(n for h, n in homes.items() if hav(places[p], places[h]) <= 55.0) for p in places}

    legs_by_req: dict[str, list[dict]] = defaultdict(list)
    for lg in legs_raw:
        legs_by_req[lg["requestId"]].append(lg)
    for lg_list in legs_by_req.values():
        lg_list.sort(key=lambda x: int(x["leg"]))

    req_dealer = {r["id"]: r["dealerId"] for r in reqs}

    # Parse events for:
    # 1. Cancelled orders (order_cancelled)
    # 2. Ledger lines per order (revenue, late_refund, undelivered_penalty, total margin cents)
    # 3. Trust events sorted by timestamp `at`:
    #    RULES.md L164-165: "An order's revenue line with no late refund is an order on time."
    #    "Each counted order raises the prices that the dealer accepts from you by 1% [up to 25].
    #     An order that arrives late halves that dealer's count, rounded down."
    cancelled_orders: set[str] = set()
    order_ledger: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    order_won_info: dict[str, dict] = {}

    for e in events:
        kind = e["kind"]
        if kind == "order_cancelled":
            oid = e["orderId"] or e["order.id"]
            if oid:
                cancelled_orders.add(oid)
        elif kind == "order_won":
            oid = e["order.id"]
            if oid:
                order_won_info[oid] = e
        elif kind == "ledger":
            oid = e["line.orderId"]
            if oid:
                order_ledger[oid].append((int(e["at"]), e["line.kind"], int(e["line.cents"])))

    # Build chronological trust transitions: (minute, seq_order, dealer_id, action)
    # action = +1 for on-time delivery, -1 for late/undelivered halving
    trust_events: list[tuple[int, str, int]] = []
    late_orders: set[str] = set()
    order_margin_cents: dict[str, int] = {}

    for oid, lines in order_ledger.items():
        order_margin_cents[oid] = sum(c for _, _, c in lines)
        dealer = req_dealer.get(oid, "")
        has_late = any(k in ("late_refund", "undelivered_penalty") for _, k, _ in lines)
        if has_late:
            late_orders.add(oid)
            late_at = min(at for at, k, _ in lines if k in ("late_refund", "undelivered_penalty"))
            if dealer:
                trust_events.append((late_at, dealer, -1))
        else:
            rev_ats = [at for at, k, _ in lines if k == "revenue"]
            if rev_ats and dealer:
                trust_events.append((min(rev_ats), dealer, +1))

    # Also check won orders that weren't cancelled and had no revenue line at world end (undelivered)
    for r in reqs:
        if r["outcome"] == "won" and r["id"] not in cancelled_orders:
            oid = r["id"]
            lines = order_ledger.get(oid, [])
            has_rev = any(k == "revenue" for _, k, _ in lines)
            if not has_rev:
                late_orders.add(oid)

    trust_events.sort(key=lambda x: x[0])

    # Batch sizes per batchId in this world
    batch_counts = Counter(r["batchId"] for r in reqs if r["batchId"])

    # Sort requests by respondBy to replay dealer trust accurately at decision minute
    reqs_sorted = sorted(reqs, key=lambda r: (int(r["respondBy"]), int(r["arrivedAt"]), r["id"]))
    ev_idx = 0
    dealer_trust: dict[str, int] = defaultdict(int)
    # Also track prior-days win share per dealer to inspect competitor morning adaptation
    dealer_day_tot: dict[tuple[str, int], int] = defaultdict(int)
    dealer_day_won: dict[tuple[str, int], int] = defaultdict(int)
    for r in reqs:
        dy = int(r["arrivedAt"]) // 1440
        dealer_day_tot[(r["dealerId"], dy)] += 1
        if r["outcome"] == "won":
            dealer_day_won[(r["dealerId"], dy)] += 1

    quote_rows: list[dict] = []
    won_rows: list[dict] = []

    for r in reqs_sorted:
        resp_at = int(r["respondBy"])
        arr_at = int(r["arrivedAt"])
        # Advance trust up to respondBy (inclusive of events strictly before or at respondBy)
        while ev_idx < len(trust_events) and trust_events[ev_idx][0] <= resp_at:
            _, dlr, act = trust_events[ev_idx]
            if act == 1:
                dealer_trust[dlr] = min(25, dealer_trust[dlr] + 1)
            else:
                dealer_trust[dlr] //= 2
            ev_idx += 1

        # Check non-decline quoted options
        q_opts: dict[str, tuple[int, int]] = {}
        all_list: list[int] = []
        for k in OPTS:
            lc_s = r.get(f"{k}.listPriceCents", "")
            qc_s = r.get(f"{k}.quoteCents", "")
            if lc_s:
                all_list.append(int(lc_s))
            if qc_s and lc_s:
                qc, lc = int(qc_s), int(lc_s)
                if 0 < qc < 3 * lc:
                    q_opts[k] = (qc, lc)

        if not q_opts:
            continue

        rid = r["id"]
        r_legs = legs_by_req[rid]
        pickup = r_legs[0]["pickup.placeId"]
        delivery = r_legs[-1]["delivery.placeId"]
        drive_km = sum(roads[(lg["pickup.placeId"], lg["delivery.placeId"])][0] for lg in r_legs)
        drive_min = sum(roads[(lg["pickup.placeId"], lg["delivery.placeId"])][1] for lg in r_legs)
        ref_fee = int(r["referenceFeeCents"])
        max_list = max(all_list)

        # Pre-outcome quote ratio: minimum quote/list across quoted options
        # (for next_day and within_3_days, Desk quotes identical option_mult unless floored;
        #  for same_day + next_day, next_day is option_mult and same_day is 1.05 * option_mult).
        # Using pre-outcome min(quote/list) + exact quoted option combo tuple avoids ANY post-outcome bias!
        ratios = [qc / lc for qc, lc in q_opts.values()]
        min_ratio = min(ratios)
        # Check if all quoted options were at or near margin floor (~1.3587 * ref_fee)
        floor_cents = round(ref_fee * 1.25 / 0.92)
        is_floored = all(abs(qc - floor_cents) <= 2 for qc, _ in q_opts.values())

        day = min(4, max(0, arr_at // 1440))
        hour = min(17, max(8, (arr_at % 1440) // 60))
        bsize = batch_counts[r["batchId"]] if r["batchId"] else 1
        dlr = r["dealerId"]
        trust = dealer_trust[dlr]

        # Prior days win share for this dealer
        prev_tot = sum(dealer_day_tot[(dlr, d0)] for d0 in range(day))
        prev_won = sum(dealer_day_won[(dlr, d0)] for d0 in range(day))
        prev_share = (prev_won / prev_tot) if prev_tot >= 3 else -1.0

        won = 1 if r["outcome"] == "won" else 0
        opt_combo = "+".join(q_opts.keys())

        rec = {
            "world": wid,
            "seed": seed,
            "version": version,
            "world_day": f"{wid}:{day}",
            "id": rid,
            "dealer": dlr,
            "won": won,
            "log_price": math.log(min_ratio),
            "log_typ_list": math.log(ref_fee / max_list),
            "log_km": math.log(max(1.0, drive_km)),
            "drive_min": drive_min,
            "pickup": pickup,
            "delivery": delivery,
            "opt_combo": opt_combo,
            "day": day,
            "hour": hour,
            "bsize": bsize,
            "log_bsize": math.log(bsize),
            "trust": trust,
            "is_floored": is_floored,
            "prev_share": prev_share,
            "pk_sup30": supply30[pickup],
            "pk_sup55": supply55[pickup],
            "dl_sup30": supply30[delivery],
            "premium": r_legs[0]["car.premium"] == "true",
            "priv_pk": r_legs[0]["pickup.privateAddress"] == "true",
            "priv_dl": r_legs[-1]["delivery.privateAddress"] == "true",
            "tradein": len(r_legs) > 1,
            "has_note": bool(r["note"]),
        }
        quote_rows.append(rec)

        if won and rid not in cancelled_orders:
            won_opt = r["option"]
            won_qc, won_lc = q_opts.get(won_opt, next(iter(q_opts.values())))
            won_rec = {
                **rec,
                "won_opt": won_opt,
                "is_same_day": 1 if won_opt == "same_day" else 0,
                "is_w3d": 1 if won_opt == "within_3_days" else 0,
                "won_log_price": math.log(won_qc / won_lc),
                "late": 1 if rid in late_orders else 0,
                "margin_eur": order_margin_cents.get(rid, 0) / 100.0,
            }
            won_rows.append(won_rec)

    return quote_rows, won_rows, supply30


def center_place_effects(
    places: list[str],
    ref_place: str,
    idx_map: dict[str, int],
    theta: list[float],
    cov: list[list[float]],
    weights: dict[str, float],
) -> dict[str, tuple[float, float]]:
    """Transform reference-coded place effects to weighted-mean-zero effects with exact SEs."""
    tot_w = sum(weights.get(p, 0.0) for p in places)
    w = {p: weights.get(p, 0.0) / tot_w for p in places}
    raw = {p: (0.0 if p == ref_place else theta[idx_map[p]]) for p in places}
    mean_eff = sum(w[p] * raw[p] for p in places)

    non_ref = [p for p in places if p != ref_place]
    out: dict[str, tuple[float, float]] = {}
    for p in places:
        eff = raw[p] - mean_eff
        # eff = sum_{q != ref} c_q * theta[idx_map[q]], where c_q = (1 if q==p else 0) - w[q]
        var = 0.0
        for q1 in non_ref:
            c1 = (1.0 if q1 == p else 0.0) - w[q1]
            i1 = idx_map[q1]
            for q2 in non_ref:
                c2 = (1.0 if q2 == p else 0.0) - w[q2]
                i2 = idx_map[q2]
                var += c1 * c2 * cov[i1][i2]
        out[p] = (eff, math.sqrt(max(0.0, var)))
    return out


def shrink_effects(
    centered_log_price: dict[str, tuple[float, float]],
) -> tuple[dict[str, float], float]:
    """Empirical Bayes shrinkage towards 0 using estimated true variance tau^2."""
    vals = list(centered_log_price.values())
    # Estimate tau^2 over places with reasonable precision (SE < 0.10)
    informative = [(est, se) for est, se in vals if se < 0.10]
    if not informative:
        informative = vals
    tau2 = max(1e-6, sum(est * est - se * se for est, se in informative) / len(informative))
    tau = math.sqrt(tau2)
    shrunk = {}
    for p, (est, se) in centered_log_price.items():
        if se <= 0.0:
            shrunk[p] = 0.0
        else:
            factor = tau2 / (tau2 + se * se)
            shrunk[p] = est * factor
    return shrunk, tau


def build_and_fit_won(
    rows: list[dict],
    all_places: list[str],
    include_typ_km: bool = False,
    include_dealer_fe: bool = False,
) -> dict:
    """Fit won ~ log(quote/list) + pickup + delivery + option + hour + batch_size + trust + world*day."""
    ref_place = "helsinki"
    opt_levels = sorted(set(r["opt_combo"] for r in rows))
    ref_opt = "next_day" if "next_day" in opt_levels else opt_levels[0]
    hours = sorted(set(r["hour"] for r in rows))
    ref_hour = 10 if 10 in hours else hours[0]
    dealers = sorted(set(r["dealer"] for r in rows))
    ref_dealer = dealers[0]

    names: list[str] = ["log_price", "trust", "log_bsize"]
    if include_typ_km:
        names.extend(["log_typ_list", "log_km"])

    pk_idx: dict[str, int] = {}
    for p in all_places:
        if p != ref_place:
            pk_idx[p] = len(names)
            names.append(f"pk:{p}")

    dl_idx: dict[str, int] = {}
    for p in all_places:
        if p != ref_place:
            dl_idx[p] = len(names)
            names.append(f"dl:{p}")

    opt_idx: dict[str, int] = {}
    for o in opt_levels:
        if o != ref_opt:
            opt_idx[o] = len(names)
            names.append(f"opt:{o}")

    hr_idx: dict[int, int] = {}
    for h in hours:
        if h != ref_hour:
            hr_idx[h] = len(names)
            names.append(f"hr:{h}")

    dlr_idx: dict[str, int] = {}
    if include_dealer_fe:
        for d in dealers:
            if d != ref_dealer:
                dlr_idx[d] = len(names)
                names.append(f"dlr:{d}")

    wd_list = sorted(set(r["world_day"] for r in rows))
    wd_map = {wd: i for i, wd in enumerate(wd_list)}

    rows_x: list[list[tuple[int, float]]] = []
    rows_y: list[int] = []
    rows_g: list[int] = []

    pk_counts = Counter()
    dl_counts = Counter()

    for r in rows:
        xi: list[tuple[int, float]] = [
            (0, r["log_price"]),
            (1, float(r["trust"])),
            (2, r["log_bsize"]),
        ]
        if include_typ_km:
            xi.append((3, r["log_typ_list"]))
            xi.append((4, r["log_km"]))
        if r["pickup"] in pk_idx:
            xi.append((pk_idx[r["pickup"]], 1.0))
        if r["delivery"] in dl_idx:
            xi.append((dl_idx[r["delivery"]], 1.0))
        if r["opt_combo"] in opt_idx:
            xi.append((opt_idx[r["opt_combo"]], 1.0))
        if r["hour"] in hr_idx:
            xi.append((hr_idx[r["hour"]], 1.0))
        if include_dealer_fe and r["dealer"] in dlr_idx:
            xi.append((dlr_idx[r["dealer"]], 1.0))

        rows_x.append(xi)
        rows_y.append(r["won"])
        rows_g.append(wd_map[r["world_day"]])
        pk_counts[r["pickup"]] += 1
        dl_counts[r["delivery"]] += 1

    theta, gamma, cov, ll = fit_logistic_fe(
        rows_x, rows_y, rows_g, len(names), len(wd_list), l2_theta=1e-4, l2_group=1e-3
    )

    b_price = theta[0]
    se_price = math.sqrt(cov[0][0])
    b_trust = theta[1]
    se_trust = math.sqrt(cov[1][1])

    # Average marginal effect dP/d(log_price) across dataset
    sum_w = 0.0
    for i in range(len(rows)):
        eta = gamma[rows_g[i]]
        for c, v in rows_x[i]:
            eta += theta[c] * v
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, eta))))
        sum_w += p * (1.0 - p)
    mean_dp_dlogp = b_price * (sum_w / len(rows))

    # Centered place effects in log-odds AND in log-price units (alpha = a / (-b_price))
    pk_weights = {p: max(1.0, float(pk_counts[p])) for p in all_places}
    dl_weights = {p: max(1.0, float(dl_counts[p])) for p in all_places}
    pk_lo = center_place_effects(all_places, ref_place, pk_idx, theta, cov, pk_weights)
    dl_lo = center_place_effects(all_places, ref_place, dl_idx, theta, cov, dl_weights)

    neg_b = max(0.1, -b_price)
    pk_lp = {p: (est / neg_b, se / neg_b) for p, (est, se) in pk_lo.items()}
    dl_lp = {p: (est / neg_b, se / neg_b) for p, (est, se) in dl_lo.items()}
    pk_shrunk, pk_tau = shrink_effects(pk_lp)
    dl_shrunk, dl_tau = shrink_effects(dl_lp)

    # Weekday averages of gamma
    by_day: dict[int, list[float]] = defaultdict(list)
    for wd, g_idx in wd_map.items():
        dy = int(wd.split(":")[1])
        by_day[dy].append(gamma[g_idx])
    weekday_means = {dy: st.mean(vals) for dy, vals in sorted(by_day.items())}

    return {
        "n": len(rows),
        "win_rate": sum(rows_y) / len(rows),
        "ll": ll,
        "names": names,
        "theta": theta,
        "cov": cov,
        "b_price": b_price,
        "se_price": se_price,
        "mean_dp_dlogp": mean_dp_dlogp,
        "b_trust": b_trust,
        "se_trust": se_trust,
        "trust_pct_equiv": b_trust / neg_b,
        "pk_counts": pk_counts,
        "dl_counts": dl_counts,
        "pk_lo": pk_lo,
        "dl_lo": dl_lo,
        "pk_lp": pk_lp,
        "dl_lp": dl_lp,
        "pk_shrunk": pk_shrunk,
        "dl_shrunk": dl_shrunk,
        "pk_tau": pk_tau,
        "dl_tau": dl_tau,
        "weekday_means": weekday_means,
    }


def pearson_r(xs: list[float], ys: list[float], ws: list[float] | None = None) -> float:
    if ws is None:
        ws = [1.0] * len(xs)
    tw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, xs)) / tw
    my = sum(w * y for w, y in zip(ws, ys)) / tw
    num = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    dx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    dy = sum(w * (y - my) ** 2 for w, y in zip(ws, ys))
    return num / math.sqrt(max(1e-18, dx * dy))


def main() -> None:
    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    # Load allplaces from first reveal
    with open(Path(manifest[0]["dir"]) / "places.csv", encoding="utf-8", newline="") as f:
        all_places = sorted(p["id"] for p in csv.DictReader(f))
    print(f"Map has {len(all_places)} places: {all_places}")

    # Load v3T (96 unique seeds) and v2 (64 unique seeds)
    v3t_entries = [m for m in manifest if m["version"] == "v3T"]
    v2_entries = [m for m in manifest if m["version"] == "v2"]
    v3_entries = [m for m in manifest if m["version"] == "v3"]

    v3t_quotes, v3t_won = [], []
    for e in v3t_entries:
        qr, wr, _ = load_world_data(e)
        v3t_quotes.extend(qr)
        v3t_won.extend(wr)

    v2_quotes, v2_won = [], []
    for e in v2_entries:
        qr, wr, _ = load_world_data(e)
        v2_quotes.extend(qr)
        v2_won.extend(wr)

    print(f"Loaded v3T: {len(v3t_entries)} worlds, {len(v3t_quotes)} non-decline quotes, {len(v3t_won)} won orders")
    print(f"Loaded v2 : {len(v2_entries)} worlds, {len(v2_quotes)} non-decline quotes, {len(v2_won)} won orders")

    # 1. Fit primary specification on v3T (96 independent worlds)
    print()
    print("=== 1. PRIMARY WON MODEL (v3T, 96 independent worlds) ===")
    res_96 = build_and_fit_won(v3t_quotes, all_places, include_typ_km=False, include_dealer_fe=False)
    res_96_unfl = build_and_fit_won([r for r in v3t_quotes if not r["is_floored"]], all_places, include_typ_km=False, include_dealer_fe=False)
    res_96_typ = build_and_fit_won(v3t_quotes, all_places, include_typ_km=True, include_dealer_fe=False)
    res_96_dlr = build_and_fit_won(v3t_quotes, all_places, include_typ_km=False, include_dealer_fe=True)
    res_pool = build_and_fit_won(v2_quotes + v3t_quotes, all_places, include_typ_km=False, include_dealer_fe=False)
    res_pool_typ = build_and_fit_won(v2_quotes + v3t_quotes, all_places, include_typ_km=True, include_dealer_fe=False)

    for label, res in [
        ("v3T 96w (primary)", res_96),
        ("v3T 96w (unfloored only)", res_96_unfl),
        ("v3T 96w (+log_typ, +log_km)", res_96_typ),
        ("v3T 96w (+dealer FE)", res_96_dlr),
        ("Pooled v2+v3T 160w", res_pool),
        ("Pooled v2+v3T 160w (+typ,km)", res_pool_typ),
    ]:
        p1_cost = res["mean_dp_dlogp"] * 0.01 * 100.0  # percentage points of win rate per +1% price
        print(
            f"  {label:<28} n={res['n']:<7} win={res['win_rate']:.3f}  "
            f"b_logp={res['b_price']:+.3f}±{res['se_price']:.3f} (1% dearer -> {p1_cost:+.2f} pp win)  "
            f"b_trust={res['b_trust']:+.4f}±{res['se_trust']:.4f} (equiv {res['trust_pct_equiv']*100:+.2f}%/cnt)"
        )
        if "log_typ_list" in res["names"]:
            it = res["names"].index("log_typ_list")
            ik = res["names"].index("log_km")
            bt, set_ = res["theta"][it], math.sqrt(res["cov"][it][it])
            bk, sek = res["theta"][ik], math.sqrt(res["cov"][ik][ik])
            neg_b = -res["b_price"]
            print(f"    -> log(typ/list): {bt:+.3f}±{set_:.3f} (price weight {bt/neg_b:+.3f}); log(km): {bk:+.3f}±{sek:.3f} (price weight {bk/neg_b:+.3f})")

    # Also check trust slope controlling for competitor morning adaptation (prev_share)
    # Filter to days Tue-Fri where prev_share >= 0 is observed, or include prev_share interaction
    tue_fri = [r for r in v3t_quotes if r["prev_share"] >= 0.0]
    print(f"  Weekday mean world-day intercepts (Mon..Fri): {[round(res_96['weekday_means'][d], 3) for d in range(5)]}")
    for nm, val, idx in [(res_96["names"][j], res_96["theta"][j], j) for j in range(len(res_96["names"]))]:
        if nm.startswith(("opt:", "hr:", "log_bsize")):
            se = math.sqrt(res_96["cov"][idx][idx])
            print(f"    {nm:<36} {val:+.4f} ± {se:.4f} (log-price equiv {val/(-res_96['b_price'])*100:+.2f}%)")

    # 2. Out-of-sample stability checks across disjoint seeds!
    print()
    print("=== 2. OUT-OF-SAMPLE PLACE EFFECT STABILITY ACROSS DISJOINT WORLDS ===")
    # Split A/B: odd vs even seed number across all 96 distinct seeds in v3T
    seeds_sorted = sorted(set(r["seed"] for r in v3t_quotes))
    half_a_seeds = set(seeds_sorted[0::2])
    half_b_seeds = set(seeds_sorted[1::2])
    res_a = build_and_fit_won([r for r in v3t_quotes if r["seed"] in half_a_seeds], all_places)
    res_b = build_and_fit_won([r for r in v3t_quotes if r["seed"] in half_b_seeds], all_places)

    # Split 2: dev+hold (32 seeds) vs night+final (64 seeds)
    dh_seeds = {s for s in seeds_sorted if s.startswith(("dev-", "hold-"))}
    nf_seeds = {s for s in seeds_sorted if s.startswith(("night-", "final-"))}
    res_dh = build_and_fit_won([r for r in v3t_quotes if r["seed"] in dh_seeds], all_places)
    res_nf = build_and_fit_won([r for r in v3t_quotes if r["seed"] in nf_seeds], all_places)

    # Split 3: v2 on night-32 vs v3T on final-32 (completely different policy AND completely disjoint seeds!)
    res_v2_night = build_and_fit_won([r for r in v2_quotes if r["seed"].startswith("night-")], all_places)
    res_v3t_final = build_and_fit_won([r for r in v3t_quotes if r["seed"].startswith("final-")], all_places)

    # Split 4: non-holdout 80 seeds (dev + night + final) vs holdout 16 seeds
    noh_seeds = {s for s in seeds_sorted if not s.startswith("hold-")}
    h_seeds = {s for s in seeds_sorted if s.startswith("hold-")}
    res_noh = build_and_fit_won([r for r in v3t_quotes if r["seed"] in noh_seeds], all_places)
    res_h = build_and_fit_won([r for r in v3t_quotes if r["seed"] in h_seeds], all_places)

    for split_name, r1, r2 in [
        ("Half A (48w) vs Half B (48w) [v3T]", res_a, res_b),
        ("dev+hold (32w) vs night+final (64w)", res_dh, res_nf),
        ("v2 night (32w) vs v3T final (32w)", res_v2_night, res_v3t_final),
        ("non-holdout (80w) vs holdout (16w)", res_noh, res_h),
    ]:
        pk_common = [p for p in all_places if r1["pk_counts"][p] >= 25 and r2["pk_counts"][p] >= 25]
        dl_common = [p for p in all_places if r1["dl_counts"][p] >= 25 and r2["dl_counts"][p] >= 25]
        pk_r_raw = pearson_r([r1["pk_lp"][p][0] for p in pk_common], [r2["pk_lp"][p][0] for p in pk_common])
        pk_r_w = pearson_r(
            [r1["pk_lp"][p][0] for p in pk_common],
            [r2["pk_lp"][p][0] for p in pk_common],
            [min(r1["pk_counts"][p], r2["pk_counts"][p]) for p in pk_common],
        )
        dl_r_raw = pearson_r([r1["dl_lp"][p][0] for p in dl_common], [r2["dl_lp"][p][0] for p in dl_common])
        dl_r_w = pearson_r(
            [r1["dl_lp"][p][0] for p in dl_common],
            [r2["dl_lp"][p][0] for p in dl_common],
            [min(r1["dl_counts"][p], r2["dl_counts"][p]) for p in dl_common],
        )
        # Also lane sum (pickup + delivery) correlation across all observed (pk, dl) pairs in Half B
        lanes_b = Counter((r["pickup"], r["delivery"]) for r in v3t_quotes if r["seed"] in half_b_seeds)
        lane_x = [r1["pk_shrunk"][pk] + r1["dl_shrunk"][dl] for (pk, dl) in lanes_b]
        lane_y = [r2["pk_shrunk"][pk] + r2["dl_shrunk"][dl] for (pk, dl) in lanes_b]
        lane_w = [float(cnt) for cnt in lanes_b.values()]
        lane_r = pearson_r(lane_x, lane_y, lane_w)
        print(
            f"  {split_name:<38} "
            f"pk(n={len(pk_common)}): r={pk_r_raw:+.3f} (wt {pk_r_w:+.3f}) | "
            f"dl(n={len(dl_common)}): r={dl_r_raw:+.3f} (wt {dl_r_w:+.3f}) | "
            f"lane_sum wt_r={lane_r:+.3f}"
        )

    # Print full pickup & delivery tables (from non-holdout 80w AND full 96w)
    print()
    print(f"=== 3. LANE EFFECTS TABLE (non-holdout 80w: pk_tau={res_noh['pk_tau']:.4f}, dl_tau={res_noh['dl_tau']:.4f}; full 96w: pk_tau={res_96['pk_tau']:.4f}, dl_tau={res_96['dl_tau']:.4f}) ===")
    print("  PICKUP PLACES (log-price units: +0.05 means competitor ~5% dearer from this pickup):")
    for p in sorted(all_places, key=lambda x: res_noh["pk_shrunk"][x], reverse=True):
        est80, se80 = res_noh["pk_lp"][p]
        sh80 = res_noh["pk_shrunk"][p]
        sh96 = res_96["pk_shrunk"][p]
        cnt80 = res_noh["pk_counts"][p]
        est_a, _ = res_a["pk_lp"][p]
        est_b, _ = res_b["pk_lp"][p]
        print(f"    {p:<16} n80={cnt80:<5} raw80={est80:+.4f}±{se80:.4f}  shrunk80={sh80:+.4f}  shrunk96={sh96:+.4f}  (halfA={est_a:+.4f}, halfB={est_b:+.4f})")

    print("  DELIVERY PLACES (log-price units: +0.05 means competitor ~5% dearer to this delivery):")
    for p in sorted(all_places, key=lambda x: res_noh["dl_shrunk"][x], reverse=True):
        est80, se80 = res_noh["dl_lp"][p]
        sh80 = res_noh["dl_shrunk"][p]
        sh96 = res_96["dl_shrunk"][p]
        cnt80 = res_noh["dl_counts"][p]
        est_a, _ = res_a["dl_lp"][p]
        est_b, _ = res_b["dl_lp"][p]
        print(f"    {p:<16} n80={cnt80:<5} raw80={est80:+.4f}±{se80:.4f}  shrunk80={sh80:+.4f}  shrunk96={sh96:+.4f}  (halfA={est_a:+.4f}, halfB={est_b:+.4f})")

    # 4. Fit SECOND MODEL: late ~ same features + drive_minutes + same-day-or-not over won orders
    print()
    print("=== 4. LATENESS MODEL OVER WON ORDERS (v3T 96w + v2 64w) ===")
    fit_and_report_late(v3t_won, all_places, label="v3T 96w")
    fit_and_report_late(v2_won + v3t_won, all_places, label="v2+v3T 160w")


def fit_and_report_late(won_rows: list[dict], all_places: list[str], label: str) -> None:
    ref_place = "helsinki"
    hours = sorted(set(r["hour"] for r in won_rows))
    ref_hour = 10 if 10 in hours else hours[0]

    # Build covariates: intercept (for ungrouped/penalized), log_price, trust, log_bsize,
    # drive_hours (drive_min / 60), is_same_day, is_w3d, weekday dummies, hour dummies, pickup, delivery
    names = ["intercept", "won_log_price", "trust", "log_bsize", "drive_hr", "is_same_day", "is_w3d"]
    day_idx = {}
    for d in range(1, 5):
        day_idx[d] = len(names)
        names.append(f"day:{d}")
    hr_idx = {}
    for h in hours:
        if h != ref_hour:
            hr_idx[h] = len(names)
            names.append(f"hr:{h}")
    pk_idx = {}
    for p in all_places:
        if p != ref_place:
            pk_idx[p] = len(names)
            names.append(f"pk:{p}")
    dl_idx = {}
    for p in all_places:
        if p != ref_place:
            dl_idx[p] = len(names)
            names.append(f"dl:{p}")

    wd_list = sorted(set(r["world_day"] for r in won_rows))
    wd_map = {wd: i for i, wd in enumerate(wd_list)}

    rows_x: list[list[tuple[int, float]]] = []
    rows_y: list[int] = []
    rows_g: list[int] = []
    for r in won_rows:
        xi: list[tuple[int, float]] = [
            (0, 1.0),
            (1, r["won_log_price"]),
            (2, float(r["trust"])),
            (3, r["log_bsize"]),
            (4, r["drive_min"] / 60.0),
            (5, float(r["is_same_day"])),
            (6, float(r["is_w3d"])),
        ]
        if r["day"] in day_idx:
            xi.append((day_idx[r["day"]], 1.0))
        if r["hour"] in hr_idx:
            xi.append((hr_idx[r["hour"]], 1.0))
        if r["pickup"] in pk_idx:
            xi.append((pk_idx[r["pickup"]], 1.0))
        if r["delivery"] in dl_idx:
            xi.append((dl_idx[r["delivery"]], 1.0))
        rows_x.append(xi)
        rows_y.append(r["late"])
        rows_g.append(wd_map[r["world_day"]])

    # Fit with penalized world*day random/MAP effects (l2_group=2.0 -> sigma_wd ~= 0.71, avoiding -inf separation!)
    theta_fe, gamma_fe, cov_fe, _ = fit_logistic_fe(
        rows_x, rows_y, rows_g, len(names), len(wd_list), l2_theta=0.1, l2_group=2.0
    )
    # Also fit marginal model (n_groups=0) to predict observable class late probabilities cleanly
    theta_m, _, cov_m, _ = fit_logistic_fe(
        rows_x, rows_y, [], len(names), 0, l2_theta=0.1, l2_group=1.0
    )

    tot_late = sum(rows_y)
    print(f"  [{label}] n_won={len(won_rows)}, n_late={tot_late} ({tot_late/len(won_rows):.2%})")
    for j in range(min(15, len(names))):
        se = math.sqrt(cov_fe[j][j])
        print(f"    {names[j]:<18} FE_fit={theta_fe[j]:+.4f}±{se:.4f}   marginal_fit={theta_m[j]:+.4f}")

    # Score each won order with marginal predicted late probability and tabulate interpretable classes
    preds = []
    for i, r in enumerate(won_rows):
        eta = sum(theta_m[c] * v for c, v in rows_x[i])
        preds.append(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, eta)))))

    # Class breakdown: pickup pool x option x drive band
    capital = {"helsinki", "espoo", "vantaa"}

    def pk_pool(r: dict) -> str:
        if r["pickup"] in capital:
            return "capital"
        if r["pk_sup30"] < 30 and r["pk_sup55"] >= 30:
            return "ring"
        if r["pk_sup30"] >= 100:
            return "hub100+"
        if r["pk_sup30"] >= 50:
            return "reg50-99"
        return "thin<50"

    def dl_pool(r: dict) -> str:
        if r["delivery"] in capital:
            return "to_cap"
        if r["dl_sup30"] >= 100:
            return "to_hub100+"
        if r["dl_sup30"] >= 30:
            return "to_reg30-99"
        return "to_thin<30"

    def drv_band(m: int) -> str:
        if m < 60:
            return "<60m"
        if m < 180:
            return "60-179m"
        if m < 300:
            return "180-299m"
        return "300m+"

    classes: dict[tuple[str, str, str], list[tuple[int, float, float]]] = defaultdict(list)
    for r, pr in zip(won_rows, preds):
        key = (pk_pool(r), r["won_opt"], drv_band(r["drive_min"]))
        classes[key].append((r["late"], pr, r["margin_eur"]))

    print(f"  [{label}] Classes sorted by empirical late rate (showing n >= 40):")
    for key, items in sorted(classes.items(), key=lambda kv: (sum(x[0] for x in kv[1]) / len(kv[1]), -len(kv[1]))):
        if len(items) < 40:
            continue
        n_c = len(items)
        l_c = sum(x[0] for x in items)
        emp = l_c / n_c
        mod = sum(x[1] for x in items) / n_c
        mrg = sum(x[2] for x in items) / n_c
        tag = "BUFFER (<2%)" if emp < 0.02 else ("RISK (>5%)" if emp > 0.05 else "mid")
        print(f"    {str(key):<38} n={n_c:<5} late={l_c:<3} emp={emp:5.2%} mod={mod:5.2%} €/{'ord'}: {mrg:6.2f}  [{tag}]")


if __name__ == "__main__":
    main()
