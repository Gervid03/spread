"""Summarize all cp-routes evaluations (v4, v5, and night32) and extract ledger + mechanism counters."""
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    runs = [
        ("v4-noop", "runs/20261114-094600-cp-routes-noop"),
        ("v4-smoke-a-noseed", "runs/20261114-101724-cp-routes-smoke-a-noseed"),
        ("v4-smoke-b-seed03", "runs/20261114-101810-cp-routes-smoke-b-seed03"),
        ("v4-smoke-c-seed04", "runs/20261114-102016-cp-routes-smoke-c-seed04"),
        ("v4-smoke-d-acc105", "runs/20261114-102732-cp-routes-smoke-d-acc105"),
        ("v4-dev-seed04", "runs/20261114-103153-cp-routes-dev-full-seed04"),
        ("v4-dev-noseed", "runs/20261114-103757-cp-routes-dev-noseed"),
        ("v5-noop", "runs/20261114-110019-cp-routes-v5-noop"),
        ("v5-smoke-noseed", "runs/20261114-110111-cp-routes-v5-smoke-noseed"),
        ("v5-smoke-seed04", "runs/20261114-110340-cp-routes-v5-smoke-seed04"),
        ("v5-dev-noseed", "runs/20261114-110549-cp-routes-v5-dev-noseed"),
        ("v5-dev-seed04", "runs/20261114-110828-cp-routes-v5-dev-seed04"),
        ("v5-dev-relay-offer", "runs/20261114-112437-cp-routes-v5-dev-relay-offer"),
        ("v5-dev-rt35", "runs/20261114-113036-cp-routes-v5-dev-rt35"),
        ("v5-night32-seed04", "runs/20261114-111117-cp-routes-v5-night32-seed04"),
        ("v5-night32-noseed", "runs/20261114-112010-cp-routes-v5-night32-noseed"),
        ("v5-night32-relay-offer", "runs/20261114-112604-cp-routes-v5-night32-relay-offer"),
    ]
    for name, rdir in runs:
        p = Path(rdir)
        if not p.exists():
            continue
        s = json.loads((p / "summary.json").read_text())
        rows = [json.loads(line) for line in (p / "results.jsonl").read_text().splitlines() if line.strip()]
        under92 = sum(1 for r in rows if r["on_time"] < 0.92)
        worst_seed = min(rows, key=lambda r: r["on_time"])
        print(
            f"{name:22s} | n={s['n']:2d} | mean={s['margin_mean']:9.2f} | min={s['margin_min']:8.2f} "
            f"| won={s['won_mean']:5.1f} | ot_mean={s['on_time_mean']*100:5.2f}% "
            f"| ot_min={s['on_time_min']*100:5.2f}% ({worst_seed['seed']}) | <92={under92}/{len(rows)} | safe={s['safe']}"
        )

    print("=== DETAILED COUNTERS ON V5-DEV-SEED04 vs V5-DEV-NOSEED vs CHAMPION V5 ===")
    champ_rows = [json.loads(line) for line in Path("champion/results/dev-L8.jsonl").read_text().splitlines() if line.strip()]
    for label, rows in [
        ("champ-v5", champ_rows),
        ("v5-dev-noseed", [json.loads(line) for line in Path("runs/20261114-110549-cp-routes-v5-dev-noseed/results.jsonl").read_text().splitlines() if line.strip()]),
        ("v5-dev-seed04", [json.loads(line) for line in Path("runs/20261114-110828-cp-routes-v5-dev-seed04/results.jsonl").read_text().splitlines() if line.strip()]),
    ]:
        st: Counter = Counter()
        led: Counter = Counter()
        for r in rows:
            for k, v in r.get("stats", {}).items():
                st[k] += v
            for k, v in r.get("ledger", {}).items():
                led[k] += v
        n = len(rows)
        print(f"--- {label} (mean/wk, n={n}) ---")
        print("  ledger (€):", {k: round(v / n, 2) for k, v in sorted(led.items())})
        for k in [
            "won", "booked", "deadline_close", "gig_expired", "gig_dropped",
            "relay_paired", "relay_paired_thin_b", "relay_paired_roundtrip", "relay_booked", "relay_booked_thin_b",
            "relay_split", "relay_split_patience", "relay_quote_quoted", "relay_quote_won", "relay_quote_late",
            "relay_late", "relay_late_booked", "relay_paid_gigs", "relay_paid_fee_cents", "relay_paid_ref_cents",
            "net_quoted", "net_quoted_thin", "net_won", "net_won_thin", "net_thin_late", "margin_net_thin_cents",
            "net_offers", "net_offers_prestart", "net_offers_prefinish", "net_home_offers",
            "net_accepted", "net_home_accepted", "net_declined", "net_expired",
            "seed_quoted", "seed_won", "seed_late", "margin_seed_cents",
            "view_offers_sent", "view_offer_accepted", "driver_days_2plus",
        ]:
            if st[k]:
                print(f"    {k}: {st[k]/n:.2f}")


if __name__ == "__main__":
    main()
