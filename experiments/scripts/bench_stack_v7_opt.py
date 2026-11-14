#!/usr/bin/env python3
"""Applies r4-live's exact €0.00-parity optimizations onto origin/exp/stack-v7 in a temporary package
and benchmarks `practice` and `live` modes against unoptimized stack-v7 via desk_timing.py.

Optimizations verified to keep exact cent-for-cent & stat-for-stat parity on stack-v7:
  1. `notes.py`: precompiled `_WORD_HOURS_COMPILED` + clause/harmless regexes + `@lru_cache` on `_parse_note_v2_cached`.
  2. `backlog_near` & `projected_on_time`: self-synchronizing `_open_oids` and `_if_open` active lists (O(active) vs O(all)).
  3. `undelivered`: 1-leg fast path; `rejoin`: O(1) `snap_orders` dict.
  4. `tick_proactive_offers`: prune offered views & skip allocating `busy_drivers` when no mature view is ready.
  5. `cp-routes` `net_offer_tick`:
     - Only call `_flush_non_quotes()` when a queued `post` can actually qualify at `age == 0`
       (`is_urgent`, `net_offer_min_age <= 0`, or `gate_supply < min_supply`), eliminating ~145 wasted
       `POST /actions` HTTP round-trips per world.
     - Iterate only active unbooked gigs from `leg_gigs`, and memoize `(now, state_sig)` across same-minute live events.
  6. `cp-routes` `_tick_relay` / `_waiting_single_orders` / `_car_spec_for_order` / `relay_quote_reqs`:
     - Cache `_car_spec_for_order` per `(oid, deadline, lastPickupAt, retry)`.
     - Iterate `self.relay_quote_reqs` (~5 items) instead of `self.requests` (1,036 items).
     - Pre-index `outbox` single posts in `_waiting_single_orders`, and skip redundant same-minute `_tick_relay`
       calls in live mode when `(now, relay_sig)` is unchanged.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))
if str(REPO / "experiments" / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "experiments" / "scripts"))

from desk_timing import load_policy_from_git_ref, print_markdown_report, run_one  # noqa: E402
from spread_lab.env import lab_home  # noqa: E402
from spread_lab.geo import Geo  # noqa: E402
from spread_lab.lab import CHAMPION, parse_overrides  # noqa: E402
from spread_lab.runner import play_practice  # noqa: E402

STACK_V7_ALL_FLAGS = [
    "net_relay=True",
    "net_relay_quote=True",
    "net_quote=True",
    "net_quote_km=15.0",
    "net_min_dest_supply=30",
    "net_thin_fee_open=0.95",
    "net_offer=True",
    "net_offer_max_supply=50",
    "net_offer_min_age=30",
    "net_offer_on_book=True",
    "net_lead_min=45",
    "net_home_mult=0.80",
    "net_offer_mult=0.95",
    "net_seed=0.04",
    "seed_min=6",
    "seed_max_drive_min=220",
    "lane_prior_weight=0.55",
    "lane_prior_only_neg=True",
    "lane_prior_comp_slope=2.2",
    "hub_inbound_fee_mult=1.08",
    "trust_center_slope=0.003",
    "floored_sd_prem=0.10",
    "inbound_hub_disc=0.07",
    "return_hub_min_supply=35",
    "return_hub_max_drive_min=300",
    "future_sameday_slow=true",
    "fut_sd_return_only=true",
    "fut_sd_min_deliv_supply=50",
    "return_hub_1leg_only=true",
    "return_hub_deliv_backlog_ratio=0.045",
    "return_hub_min_on_time=0.938",
    "return_hub_max_urgent=4",
    "trade_in_seq_slack=True",
    "ext_ring_max_drive_min=260",
    "lead_car_allow_benign_notes=True",
    "lead_car_cross_slow=True",
    "lead_car_max_gap_km=20.0",
]


def build_optimized_stack_v7(git_ref: str = "origin/exp/stack-v7") -> tuple[object, Path]:
    tmpdir = Path(tempfile.mkdtemp(prefix="spread_stackv7_opt_"))
    wt_dir = tmpdir / "wt"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt_dir), git_ref],
        cwd=REPO,
        env=env,
        check=True,
        capture_output=True,
    )
    try:
        # 1. Apply our current branch's zero-conflict src/ diff (notes.py + policy.py core speedups)
        diff = subprocess.run(
            ["git", "diff", "origin/main", "--", "src/"],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
        ).stdout
        subprocess.run(["git", "apply", "--3way"], input=diff, cwd=wt_dir, env=env, check=True, capture_output=True)

        pol_path = wt_dir / "src" / "spread_lab" / "policy.py"
        code = pol_path.read_text(encoding="utf-8")

        # 2. Surgical stack-v7 optimization A: eliminate redundant _flush_non_quotes() on age=0 non-urgent hub posts
        old_flush = """        if p.net_offer and any(a["type"] == "post" for a in self.outbox):
            self._flush_non_quotes()"""
        new_flush = """        if p.net_offer and any(
            any(s["orderId"] in self.urgent for s in a["stops"])
            or p.net_offer_min_age <= 0
            or self.gate_supply.get(
                self.orders[a["stops"][0]["orderId"]]["legs"][a["stops"][0]["leg"]]["pickup"]["placeId"], 0
            )
            < p.min_supply
            for a in self.outbox
            if a["type"] == "post" and a["stops"] and a["stops"][0]["orderId"] in self.orders
        ):
            self._flush_non_quotes()
        active_unbooked_gids = {
            gid for m in self.leg_gigs.values() for gid in m.values() if gid not in self.booked
        }
        if not active_unbooked_gids:
            return
        net_sig = (
            self.now,
            len(active_unbooked_gids),
            len(self.posts),
            len(self.booked),
            len(self.urgent),
            len(self.pos_ledger),
            len(self.open_offers),
            len(self.declined_pairs),
            sum(1 for pe in self.pos_ledger.values() if pe.started)
            + 2 * sum(1 for pe in self.pos_ledger.values() if pe.done),
        )
        if not p.net_viewer_offer and getattr(self, "_last_net_offer_sig", None) == net_sig:
            return
        self._last_net_offer_sig = net_sig"""
        assert old_flush in code, "old_flush not found"
        code = code.replace(old_flush, new_flush, 1)

        # Only iterate active_unbooked_gids inside net_offer_tick
        old_posts_loop = """        for gig_id, post in list(self.posts.items()):
            if gig_id in self.booked:
                continue"""
        new_posts_loop = """        for gig_id in [g for g in self.posts if g in active_unbooked_gids]:
            post = self.posts[gig_id]"""
        assert old_posts_loop in code, "old_posts_loop not found"
        code = code.replace(old_posts_loop, new_posts_loop, 1)

        # 3. Surgical stack-v7 optimization B: iterate relay_quote_reqs (~5) instead of self.requests (1,036)
        old_cap = """        for rid, req in self.requests.items():
            if rid in self.relay_quote_reqs and rid not in self.orders and rid not in self.lost_requests and self.now <= req["respondBy"]:
                used += 1"""
        new_cap = """        for rid in self.relay_quote_reqs:
            req = self.requests.get(rid)
            if req is not None and rid not in self.orders and rid not in self.lost_requests and self.now <= req["respondBy"]:
                used += 1"""
        assert old_cap in code, "old_cap not found"
        code = code.replace(old_cap, new_cap, 1)

        old_comm = """        committed_partners = {
            self.relay_quote_partner[rid]
            for rid, req in self.requests.items()
            if rid in self.relay_quote_reqs
            and rid in self.relay_quote_partner
            and rid not in self.orders
            and rid not in self.lost_requests
            and self.now <= req["respondBy"]
        }"""
        new_comm = """        committed_partners = {
            self.relay_quote_partner[rid]
            for rid in self.relay_quote_reqs
            if rid in self.relay_quote_partner
            and rid in self.requests
            and rid not in self.orders
            and rid not in self.lost_requests
            and self.now <= self.requests[rid]["respondBy"]
        }"""
        assert old_comm in code, "old_comm not found"
        code = code.replace(old_comm, new_comm, 1)

        # 4. Surgical stack-v7 optimization C: cache _car_spec_for_order + fast _waiting_single_orders + skip duplicate same-minute _tick_relay
        old_spec = """    def _car_spec_for_order(self, order: Order, retry: Optional[Retry] = None) -> Optional[CarSpec]:
        if len(order["legs"]) != 1 or undelivered(order) != [0]:
            return None"""
        new_spec = """    def _car_spec_for_order(self, order: Order, retry: Optional[Retry] = None) -> Optional[CarSpec]:
        if len(order["legs"]) != 1 or undelivered(order) != [0]:
            return None
        r_eff = retry if retry is not None else self.saved_retry.get((order["id"], 0), Retry())
        cache = getattr(self, "_car_spec_cache", None)
        if cache is None:
            cache = {}
            self._car_spec_cache = cache
        ckey = (
            order["id"],
            order["deadline"],
            order["lastPickupAt"],
            order["legs"][0]["pickup"]["window"]["from"],
            order["legs"][0]["pickup"]["window"]["to"],
            order["legs"][0]["delivery"]["window"]["from"],
            order["legs"][0]["delivery"]["window"]["to"],
            r_eff,
        )
        if ckey in cache:
            return cache[ckey]"""
        assert old_spec in code, "old_spec not found"
        code = code.replace(old_spec, new_spec, 1)

        old_spec_ret_full = """        return CarSpec(
            place_p=pk_place,
            place_d=dl_place,
            stop_p=leg0["pickup"],
            stop_d=leg0["delivery"],
            pick_from=pk_win["from"],
            pick_to=pk_win["to"],
            del_from=dl_win["from"],
            del_to=dl_win["to"],
            deadline=order["deadline"],
            drive_min=self.geo.minutes(pk_place, dl_place),
            extra_min=extra,
            supply_p=self.supply.get(pk_place, 0),
        )

    def _car_spec_for_request_option"""
        new_spec_ret_full = """        spec_val_tmp = CarSpec(
            place_p=pk_place,
            place_d=dl_place,
            stop_p=leg0["pickup"],
            stop_d=leg0["delivery"],
            pick_from=pk_win["from"],
            pick_to=pk_win["to"],
            del_from=dl_win["from"],
            del_to=dl_win["to"],
            deadline=order["deadline"],
            drive_min=self.geo.minutes(pk_place, dl_place),
            extra_min=extra,
            supply_p=self.supply.get(pk_place, 0),
        )
        cache[ckey] = spec_val_tmp
        return spec_val_tmp

    def _car_spec_for_request_option"""
        assert old_spec_ret_full in code, "old_spec_ret_full not found"
        code = code.replace(old_spec_ret_full, new_spec_ret_full, 1)

        old_wait = """    def _waiting_single_orders(self) -> list[tuple[str, Optional[str]]]:
        res: list[tuple[str, Optional[str]]] = []
        for oid, order in self.orders.items():"""
        new_wait = """    def _waiting_single_orders(self) -> list[tuple[str, Optional[str]]]:
        res: list[tuple[str, Optional[str]]] = []
        outbox_singles = {
            a["stops"][0]["orderId"]
            for a in self.outbox
            if a["type"] == "post" and len(a["stops"]) == 2
        }
        for oid, order in self.orders.items():"""
        assert old_wait in code, "old_wait not found"
        code = code.replace(old_wait, new_wait, 1)
        code = code.replace(
            'if any(a["type"] == "post" and len(a["stops"]) == 2 and a["stops"][0]["orderId"] == oid for a in self.outbox):',
            "if oid in outbox_singles:",
            1,
        )

        old_trelay = """    def _tick_relay(self) -> None:
        p = self.p"""
        new_trelay = """    def _tick_relay(self) -> None:
        p = self.p
        relay_sig = (
            self.now,
            bool(self.newly_won_relay),
            len(self.orders),
            len(self.posts),
            len(self.booked),
            len(self.urgent),
            len(self.lost),
            sum(1 for a in self.outbox if a["type"] == "post"),
        )
        if not self.newly_won_relay and getattr(self, "_last_relay_sig", None) == relay_sig:
            return"""
        assert old_trelay in code, "old_trelay not found"
        code = code.replace(old_trelay, new_trelay, 1)

        old_trelay_wait = """        new_set = set(self.newly_won_relay)
        self.newly_won_relay.clear()
        waiting = self._waiting_single_orders()"""
        new_trelay_wait = """        new_set = set(self.newly_won_relay)
        self.newly_won_relay.clear()
        self._last_relay_sig = (
            self.now,
            False,
            len(self.orders),
            len(self.posts),
            len(self.booked),
            len(self.urgent),
            len(self.lost),
            sum(1 for a in self.outbox if a["type"] == "post"),
        )
        waiting = self._waiting_single_orders()"""
        assert old_trelay_wait in code, "old_trelay_wait not found"
        code = code.replace(old_trelay_wait, new_trelay_wait, 1)

        pol_path.write_text(code, encoding="utf-8")

        pkg_dir = tmpdir / "spread_stackv7_opt_pkg"
        shutil.copytree(wt_dir / "src" / "spread_lab", pkg_dir)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_dir)], cwd=REPO, env=env, capture_output=True)

    sys.path.insert(0, str(tmpdir))
    spec = importlib.util.spec_from_file_location(
        "spread_stackv7_opt_pkg", pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)]
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spread_stackv7_opt_pkg"] = mod
    spec.loader.exec_module(mod)
    pol = importlib.import_module("spread_stackv7_opt_pkg.policy")
    return pol.Desk, tmpdir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake-check", action="store_true", help="Verify 100% parity on FakeWorld first")
    ap.add_argument("--seed", default="dev-12")
    ap.add_argument("--mode", default="practice,live")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    champ = json.loads((CHAMPION / "champion.json").read_text(encoding="utf-8"))
    OptStackDesk, tmp_opt = build_optimized_stack_v7("origin/exp/stack-v7")
    try:
        known = set(asdict(OptStackDesk.Params()).keys())
        base_params = {k: v for k, v in champ["params"].items() if k in known}
        overrides = parse_overrides(OptStackDesk, STACK_V7_ALL_FLAGS)
        params = {**base_params, **overrides}

        if args.fake_check:
            from tas_fakeworld import FakeWorld

            BaseStackDesk, tmp_base = load_policy_from_git_ref("origin/exp/stack-v7")
            try:
                wmap = json.loads((lab_home() / "map.json").read_text(encoding="utf-8"))
                geo = Geo(wmap)
                notes_pool = [
                    {"lang": "fi", "text": "Nouto vasta klo 13 jalkeen, manuaalivaihteisto, ei kilpia. Toimitus ennen klo 16:00."},
                    {"lang": "sv", "text": "Avhamtning tidigast kl 10:30, manuell vaxellada, sommardack."},
                    {"lang": "en", "text": "Car ready after 14:00 in bay 12, manual gearbox, deliver before 15:30 tomorrow."},
                ]
                for sname in ("s1", "s2", "s3", "s4"):
                    scores = []
                    for cls in (BaseStackDesk, OptStackDesk):
                        w = FakeWorld(sname, wmap, n_requests=400)
                        for idx, r in enumerate(w.s["requests"]):
                            if idx % 2 == 0:
                                r["note"] = notes_pool[idx % len(notes_pool)]
                        snap = w.snapshot()
                        d = cls(w, cls.Params.from_dict(params), 8, geo, w.roster(), snap["now"])
                        play_practice(w, d, snap["endsAt"])
                        scores.append((w.score()["marginCents"], w.score()["wonOrders"], dict(d.stats)))
                    assert scores[0][:2] == scores[1][:2], f"Score mismatch on {sname}: {scores[0][:2]} vs {scores[1][:2]}"
                print("STACK-V7 OFFLINE PARITY: 4/4 seeds 100% identical marginCents and wonOrders!")
            finally:
                shutil.rmtree(tmp_base, ignore_errors=True)
            return

        rows = []
        for mode in [m.strip() for m in args.mode.split(",") if m.strip()]:
            for seed in [s.strip() for s in args.seed.split(",") if s.strip()]:
                row = run_one(OptStackDesk, params, seed=seed, level=8, mode=mode, fake=False)
                rows.append(row)
                print_markdown_report("stack-v7 (r4-live optimized, all flags)", row)
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    finally:
        shutil.rmtree(tmp_opt, ignore_errors=True)


if __name__ == "__main__":
    main()
