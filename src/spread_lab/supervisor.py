"""Evening supervisor ("rule" and "llm" arms) that sets tomorrow's intake/fee dials at 20:00 Mon-Thu."""
from __future__ import annotations

import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from .env import REPO, lab_home, load_dotenv

HOUR, DAY = 60, 24 * 60
CAPITAL_PLACES = frozenset({"helsinki", "espoo", "vantaa"})
SUPERVISOR_DAYS = ("Mon", "Tue", "Wed", "Thu")

WIN_LIMITS = (0.35, 0.45)
SUPPLY_LIMITS = (18, 30)
FEE_LIMITS = (0.75, 1.00)

GEMINI_MODEL = "gemini-4-argon"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are the evening supervisor for a car-transport dispatch desk in a 1-week Level-8 simulation (requests Mon-Fri).
Goal: maximize gross margin while strictly keeping week on-time share >= 90% (safety target >= 93.5%; < 90% is unranked).
At 20:00 Mon-Thu you set tomorrow's three dials from today's operational JSON:
1. price_target_win (0.35-0.45, base 0.40): target quote win rate; higher cuts price for volume, lower raises price and slows intake.
2. min_supply (18-30, base 22): min drivers within 55 km of pickup; lower opens thinner ring towns, higher closes risky thin towns.
3. fee_open (0.75-1.00, base 0.85): opening driver gig fee x typical fee; higher speeds booking and cuts drops, <0.82 raises drops.
World shocks: one weekday has a competitor price war (low win rate: sit it out, do not raise win target); one day has a regional outage.
Flu or snow spikes gig_dropped and leaves unbooked orders at 20:00; dealer trust (max 25, +1% price each) halves on any late order.
Loosen modestly if projected_on_time >= 0.96, warnings/drops are low, and unbooked_orders_now <= 5; tighten if projected_on_time <= 0.935 or unbooked_orders_now >= 12 or drops/warnings spike; else hold near today's dials.
Answer ONLY JSON: {"price_target_win": float, "min_supply": int, "fee_open": float, "why": "short reason"}."""


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _rate(num: int, den: int) -> float:
    return round(num / den, 3) if den > 0 else 0.0


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def resolve_world_seed(world_id: str) -> tuple[str, bool]:
    """Returns (seed_or_world_id, is_registered_practice)."""
    reg_path = lab_home() / "worlds" / f"{world_id}.json"
    if reg_path.exists():
        try:
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            seed = data.get("seed")
            if isinstance(seed, str) and seed.strip():
                return _sanitize(seed.strip()), True
            return _sanitize(world_id), True
        except Exception:
            pass
    return _sanitize(world_id), False


def clamp_dials(raw: dict[str, Any]) -> dict[str, Any]:
    """Validates and clamps a raw answer dict to the permitted dial ranges."""
    if not isinstance(raw, dict):
        raise ValueError("Supervisor answer must be a JSON object")
    for key in ("price_target_win", "min_supply", "fee_open"):
        if key not in raw or isinstance(raw[key], bool):
            raise ValueError(f"Missing or invalid field: {key}")
    win = float(raw["price_target_win"])
    sup = float(raw["min_supply"])
    fee = float(raw["fee_open"])
    if not (math.isfinite(win) and math.isfinite(sup) and math.isfinite(fee)):
        raise ValueError("Non-finite dial value")
    return {
        "price_target_win": round(_clamp(win, *WIN_LIMITS), 4),
        "min_supply": int(round(_clamp(sup, *SUPPLY_LIMITS))),
        "fee_open": round(_clamp(fee, *FEE_LIMITS), 4),
    }


def _extract_json_object(resp_data: dict[str, Any]) -> dict[str, Any]:
    candidates = resp_data.get("candidates") or []
    if not candidates:
        raise ValueError("No candidates in Gemini API response")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought")]
    if not texts:
        raise ValueError("No text part in Gemini API response")
    text = texts[-1].strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = chr(10).join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Parsed response is not a JSON object")
    return parsed


def call_gemini_argon(summary: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    """Calls gemini-4-argon at temperature 0 via stdlib urllib. Never logs or embeds the API key in URLs."""
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(summary, separators=(",", ":"))}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        GEMINI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_bytes = resp.read()
    resp_data = json.loads(raw_bytes.decode("utf-8"))
    parsed = _extract_json_object(resp_data)
    dials = clamp_dials(parsed)
    why = str(parsed.get("why", "")).strip()
    return {"raw_answer": parsed, "dials": dials, "why": why}


def rule_decide(
    summary: dict[str, Any],
    base_fee_open: float,
    low_backlog: int = 5,
    high_backlog: int = 12,
) -> dict[str, Any]:
    """Formula arm: loosen one step when projected share >= 0.96 and backlog is low;
    tighten one step when projected share <= 0.93 or backlog is high; else keep."""
    cur = summary["dials"]
    proj = float(summary["projected_on_time"])
    unbooked = int(summary["unbooked_orders_now"])
    win = float(cur["price_target_win"])
    sup = int(cur["min_supply"])
    fee = float(cur["fee_open"])

    if proj <= 0.93 or unbooked >= high_backlog:
        raw = {
            "price_target_win": win - 0.02,
            "min_supply": sup + 2,
            "fee_open": fee + 0.05,
        }
        why = f"tighten: proj={proj:.3f}, unbooked={unbooked}"
    elif proj >= 0.96 and unbooked <= low_backlog:
        raw = {
            "price_target_win": win + 0.02,
            "min_supply": sup - 2,
            "fee_open": max(base_fee_open, fee - 0.05),
        }
        why = f"loosen: proj={proj:.3f}, unbooked={unbooked}"
    else:
        raw = {
            "price_target_win": win,
            "min_supply": sup,
            "fee_open": fee,
        }
        why = f"keep: proj={proj:.3f}, unbooked={unbooked}"

    dials = clamp_dials(raw)
    return {"raw_answer": {**dials, "why": why}, "dials": dials, "why": why}


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


class Supervisor:
    """Tracks daily operational metrics and adjusts tomorrow's dials at 20:00 Mon-Thu."""

    def __init__(self, world_id: str, params) -> None:
        mode = params.supervisor.strip().lower()
        if mode not in ("llm", "rule"):
            raise ValueError(f"Unsupported supervisor mode {params.supervisor!r}; expected '', 'llm', or 'rule'")
        self.mode = mode
        self.world_seed, self.is_registered_practice = resolve_world_seed(world_id)
        self.rejoined = False
        self.base_fee_open = float(params.fee_open)

        self.seen_requests: set[str] = set()
        self.quoted_requests: set[str] = set()
        self.seen_wins: set[str] = set()
        self.seen_late_ids: set[str] = set()

        self.req_total: Counter = Counter()
        self.quote_total: Counter = Counter()
        self.normal_quote_total: Counter = Counter()
        self.win_total: Counter = Counter()
        self.normal_win_total: Counter = Counter()

        self.pool_req: dict[int, Counter] = defaultdict(Counter)
        self.pool_quote: dict[int, Counter] = defaultdict(Counter)
        self.pool_win: dict[int, Counter] = defaultdict(Counter)

        self.opt_req: dict[int, Counter] = defaultdict(Counter)
        self.opt_quote: dict[int, Counter] = defaultdict(Counter)
        self.opt_win: dict[int, Counter] = defaultdict(Counter)

        self.warnings: Counter = Counter()
        self.drops: Counter = Counter()
        self.expired: Counter = Counter()
        self.late_today: Counter = Counter()

        self.done_days: set[int] = set()
        self._lock = threading.Lock()
        self._pending: list[tuple[int, dict[str, Any], Optional[dict[str, Any]], bool, bool]] = []

    @property
    def is_live(self) -> bool:
        return self.rejoined and not self.is_registered_practice

    def _pool_of(self, desk, pickup: str) -> str:
        if pickup in CAPITAL_PLACES:
            return "capital"
        if desk.supply.get(pickup, 0) < desk.p.min_supply:
            return "ring"
        return "other"

    def _llm_cache_path(self, day: int) -> Path:
        return REPO / "runs" / "supervisor" / f"{self.world_seed}-{SUPERVISOR_DAYS[day]}.json"

    def _rule_trace_path(self, day: int) -> Path:
        return REPO / "runs" / "supervisor" / "rule" / f"{self.world_seed}-{SUPERVISOR_DAYS[day]}.json"

    def on_quote(self, desk, request: dict[str, Any], prices: dict[str, int], decision: str) -> None:
        req_id = request["id"]
        day = desk.now // DAY
        pickup = request["legs"][0]["pickup"]["placeId"]
        pool = self._pool_of(desk, pickup)

        if req_id not in self.seen_requests:
            self.seen_requests.add(req_id)
            self.req_total[day] += 1
            self.pool_req[day][pool] += 1
            for opt in request["options"]:
                self.opt_req[day][opt["kind"]] += 1

        if decision in ("quote", "floor") and prices and req_id not in self.quoted_requests:
            self.quoted_requests.add(req_id)
            self.quote_total[day] += 1
            if decision == "quote":
                self.normal_quote_total[day] += 1
            self.pool_quote[day][pool] += 1
            for opt_kind in prices:
                self.opt_quote[day][opt_kind] += 1

    def on_event(self, desk, event: dict[str, Any]) -> None:
        kind = event["kind"]
        day = event.get("at", desk.now) // DAY
        if kind == "order_won":
            order = event["order"]
            oid = order["id"]
            if oid not in self.seen_wins and oid in desk.orders:
                self.seen_wins.add(oid)
                pickup = order["legs"][0]["pickup"]["placeId"]
                pool = self._pool_of(desk, pickup)
                self.win_total[day] += 1
                if desk.decided.get(oid) == "quote":
                    self.normal_win_total[day] += 1
                self.pool_win[day][pool] += 1
                self.opt_win[day][order["option"]] += 1
        elif kind == "deadline_close":
            self.warnings[day] += 1
        elif kind in ("gig_dropped", "no_show"):
            self.drops[day] += 1
        elif kind == "gig_expired":
            self.expired[day] += 1
        elif kind == "ledger":
            line = event["line"]
            oid = line.get("orderId")
            if line["kind"] in ("late_refund", "undelivered_penalty") and oid and oid not in self.seen_late_ids:
                self.seen_late_ids.add(oid)
                self.late_today[day] += 1
        elif kind == "delivered":
            oid = event["orderId"]
            order = desk.orders.get(oid)
            if order is not None:
                open_legs = [i for i in range(len(order["legs"])) if order["deliveredAt"][i] is None]
                if not open_legs:
                    delivered_at = max(d for d in order["deliveredAt"] if d is not None)
                    if delivered_at > order["deadline"] and oid not in self.seen_late_ids:
                        self.seen_late_ids.add(oid)
                        self.late_today[day] += 1

    def build_day_summary(self, desk, day: int) -> dict[str, Any]:
        week_won = len(desk.orders)
        late_confirmed = 0
        lost_unstaffed = 0
        urgent_unstaffed = 0
        unbooked_active = 0
        unbooked_due_tomorrow = 0

        for oid, order in desk.orders.items():
            open_legs = [i for i in range(len(order["legs"])) if order["deliveredAt"][i] is None]
            gigs = desk.leg_gigs.get(oid, {})
            is_staffed = all(gigs.get(leg) in desk.booked for leg in open_legs)
            if not open_legs:
                delivered_at = max(d for d in order["deliveredAt"] if d is not None)
                if delivered_at > order["deadline"] or oid in desk.late:
                    late_confirmed += 1
                    if oid not in self.seen_late_ids:
                        self.seen_late_ids.add(oid)
                        self.late_today[day] += 1
            else:
                if not is_staffed and oid not in desk.lost and desk.now <= order["deadline"]:
                    unbooked_active += 1
                    if order["deadline"] // DAY <= day + 1:
                        unbooked_due_tomorrow += 1
                if oid in desk.late or desk.now > order["deadline"]:
                    late_confirmed += 1
                    if oid not in self.seen_late_ids:
                        self.seen_late_ids.add(oid)
                        self.late_today[day] += 1
                elif oid in desk.lost or (not is_staffed and desk.now > order["lastPickupAt"]):
                    lost_unstaffed += 1
                    if oid not in self.seen_late_ids:
                        self.seen_late_ids.add(oid)
                        self.late_today[day] += 1
                elif not is_staffed and oid in desk.urgent:
                    urgent_unstaffed += 1

        denom = max(week_won, desk.p.guard_min_orders)
        projected_on_time = round(
            1.0 - (late_confirmed + lost_unstaffed + desk.p.guard_risk_weight * urgent_unstaffed) / denom,
            4,
        )
        top_dealers = sorted(
            desk.dealer_request_count.keys(),
            key=lambda d_id: (-desk.dealer_request_count[d_id], d_id),
        )[:5]

        return {
            "day": SUPERVISOR_DAYS[day],
            "requests": self.req_total[day],
            "quotes": self.quote_total[day],
            "wins": self.win_total[day],
            "win_rate": _rate(self.win_total[day], self.quote_total[day]),
            "normal_win_rate": _rate(self.normal_win_total[day], self.normal_quote_total[day]),
            "by_pool": {
                pool: {
                    "requests": self.pool_req[day][pool],
                    "quotes": self.pool_quote[day][pool],
                    "wins": self.pool_win[day][pool],
                    "win_rate": _rate(self.pool_win[day][pool], self.pool_quote[day][pool]),
                }
                for pool in ("capital", "ring", "other")
            },
            "by_option": {
                opt: {
                    "requests": self.opt_req[day][opt],
                    "quotes": self.opt_quote[day][opt],
                    "wins": self.opt_win[day][opt],
                    "win_rate": _rate(self.opt_win[day][opt], self.opt_quote[day][opt]),
                }
                for opt in ("same_day", "next_day", "within_3_days")
            },
            "late_orders_today": self.late_today[day],
            "late_or_lost_week": late_confirmed + lost_unstaffed,
            "warnings_today": self.warnings[day],
            "warnings_week": sum(self.warnings.values()),
            "drops_today": self.drops[day],
            "drops_week": sum(self.drops.values()),
            "unbooked_orders_now": unbooked_active,
            "unbooked_urgent_now": urgent_unstaffed,
            "unbooked_due_tomorrow": unbooked_due_tomorrow,
            "week_won_orders": week_won,
            "projected_on_time": projected_on_time,
            "top_5_dealers_trust": [
                {
                    "dealer": d_id,
                    "requests": desk.dealer_request_count[d_id],
                    "trust": desk.dealer_trust[d_id],
                }
                for d_id in top_dealers
            ],
            "dials": {
                "price_target_win": round(desk.p.price_target_win, 4),
                "min_supply": int(desk.p.min_supply),
                "fee_open": round(desk.p.fee_open, 4),
                "price_mult": round(desk.mult, 3),
            },
        }

    def _apply_outcome(
        self,
        desk,
        day: int,
        summary: dict[str, Any],
        outcome: Optional[dict[str, Any]],
        from_cache: bool = False,
        api_called: bool = False,
    ) -> None:
        desk.stats[f"sup_proj_ot_d{day}"] = summary["projected_on_time"]
        desk.stats[f"sup_unbooked_d{day}"] = summary["unbooked_orders_now"]
        if api_called:
            desk.stats["sup_api_calls"] += 1
        if from_cache:
            desk.stats["sup_cache_hits"] += 1

        old_win = round(desk.p.price_target_win, 4)
        old_sup = int(desk.p.min_supply)
        old_fee = round(desk.p.fee_open, 4)

        if outcome is None:
            desk.stats["sup_fallbacks"] += 1
            desk.stats["sup_kept"] += 1
            desk.stats[f"sup_win_d{day}"] = old_win
            desk.stats[f"sup_supply_d{day}"] = old_sup
            desk.stats[f"sup_fee_d{day}"] = old_fee
            return

        dials = outcome["dials"]
        new_win = dials["price_target_win"]
        new_sup = dials["min_supply"]
        new_fee = dials["fee_open"]

        desk.p.price_target_win = new_win
        desk.p.min_supply = new_sup
        desk.p.fee_open = new_fee
        desk.stats["sup_answers_used"] += 1

        if (new_win, new_sup, new_fee) == (old_win, old_sup, old_fee):
            desk.stats["sup_kept"] += 1
        elif new_win > old_win or new_sup < old_sup or new_fee < old_fee:
            desk.stats["sup_loosened"] += 1
        else:
            desk.stats["sup_tightened"] += 1

        desk.stats[f"sup_win_d{day}"] = new_win
        desk.stats[f"sup_supply_d{day}"] = new_sup
        desk.stats[f"sup_fee_d{day}"] = new_fee

    def _drain_pending(self, desk) -> None:
        with self._lock:
            if not self._pending:
                return
            ready = list(self._pending)
            self._pending.clear()
        for day, summary, outcome, from_cache, api_called in ready:
            self._apply_outcome(desk, day, summary, outcome, from_cache=from_cache, api_called=api_called)

    def _load_cached_llm(self, day: int) -> Optional[dict[str, Any]]:
        path = self._llm_cache_path(day)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("raw_answer") or data.get("dials") or data
            dials = clamp_dials(raw)
            why = str(data.get("why") or (raw.get("why") if isinstance(raw, dict) else "") or "").strip()
            return {"raw_answer": raw, "dials": dials, "why": why}
        except Exception:
            return None

    def _save_llm_cache(self, day: int, summary: dict[str, Any], outcome: dict[str, Any]) -> None:
        path = self._llm_cache_path(day)
        record = {
            "seed": self.world_seed,
            "day": SUPERVISOR_DAYS[day],
            "day_index": day,
            "mode": "llm",
            "summary": summary,
            "raw_answer": outcome["raw_answer"],
            "dials": outcome["dials"],
            "why": outcome["why"],
        }
        try:
            _atomic_write_json(path, record)
        except Exception:
            pass

    def _save_rule_trace(self, day: int, summary: dict[str, Any], outcome: dict[str, Any]) -> None:
        path = self._rule_trace_path(day)
        record = {
            "seed": self.world_seed,
            "day": SUPERVISOR_DAYS[day],
            "day_index": day,
            "mode": "rule",
            "summary": summary,
            "dials": outcome["dials"],
            "why": outcome["why"],
        }
        try:
            _atomic_write_json(path, record)
        except Exception:
            pass

    def _run_llm_async(self, day: int, summary: dict[str, Any]) -> None:
        def worker() -> None:
            outcome: Optional[dict[str, Any]] = None
            try:
                outcome = call_gemini_argon(summary, timeout=20.0)
                self._save_llm_cache(day, summary, outcome)
            except Exception:
                outcome = None
            with self._lock:
                self._pending.append((day, summary, outcome, False, True))

        t = threading.Thread(target=worker, name=f"supervisor-{self.world_seed}-{day}", daemon=True)
        t.start()

    def on_tick(self, desk) -> None:
        self._drain_pending(desk)
        day = desk.now // DAY
        if day not in (0, 1, 2, 3) or day in self.done_days:
            return
        if desk.now % DAY < 20 * HOUR:
            return

        self.done_days.add(day)
        desk.stats["sup_calls"] += 1
        summary = self.build_day_summary(desk, day)

        if self.mode == "rule":
            outcome = rule_decide(
                summary,
                base_fee_open=self.base_fee_open,
                low_backlog=desk.p.sup_low_backlog,
                high_backlog=desk.p.sup_high_backlog,
            )
            self._save_rule_trace(day, summary, outcome)
            self._apply_outcome(desk, day, summary, outcome, from_cache=False, api_called=False)
            return

        cached = self._load_cached_llm(day)
        if cached is not None:
            self._apply_outcome(desk, day, summary, cached, from_cache=True, api_called=False)
            return

        if self.is_live:
            self._run_llm_async(day, summary)
            return

        try:
            outcome = call_gemini_argon(summary, timeout=20.0)
            self._save_llm_cache(day, summary, outcome)
            self._apply_outcome(desk, day, summary, outcome, from_cache=False, api_called=True)
        except Exception:
            self._apply_outcome(desk, day, summary, None, from_cache=False, api_called=True)

    def on_rejoin(self, desk, snapshot: dict[str, Any], history: list[dict[str, Any]]) -> None:
        """Rebuilds daily counters and restores cached evening dials after a mid-week restart."""
        self.rejoined = True
        won_ids = {e["order"]["id"] for e in history if e["kind"] == "order_won"}
        lost_req_ids = {e["requestId"] for e in history if e["kind"] == "order_lost"}

        for e in history:
            kind = e["kind"]
            d = e["at"] // DAY
            if kind == "price_request":
                req = e["request"]
                rid = req["id"]
                if rid not in self.seen_requests:
                    self.seen_requests.add(rid)
                    pickup = req["legs"][0]["pickup"]["placeId"]
                    pool = self._pool_of(desk, pickup)
                    self.req_total[d] += 1
                    self.pool_req[d][pool] += 1
                    for opt in req["options"]:
                        self.opt_req[d][opt["kind"]] += 1
                    was_admitted = (
                        rid in won_ids
                        or (
                            rid in lost_req_ids
                            and (desk.gate_supply.get(pickup, 0) >= desk.p.min_supply or rid in desk.ext_ring_reqs)
                        )
                    )
                    if was_admitted and rid not in self.quoted_requests:
                        self.quoted_requests.add(rid)
                        self.quote_total[d] += 1
                        self.normal_quote_total[d] += 1
                        self.pool_quote[d][pool] += 1
                        for opt in req["options"]:
                            self.opt_quote[d][opt["kind"]] += 1
            elif kind == "order_won":
                order = e["order"]
                oid = order["id"]
                if oid not in self.seen_wins and oid in desk.orders:
                    self.seen_wins.add(oid)
                    pickup = order["legs"][0]["pickup"]["placeId"]
                    pool = self._pool_of(desk, pickup)
                    self.win_total[d] += 1
                    self.normal_win_total[d] += 1
                    self.pool_win[d][pool] += 1
                    self.opt_win[d][order["option"]] += 1
            elif kind == "deadline_close":
                self.warnings[d] += 1
            elif kind in ("gig_dropped", "no_show"):
                self.drops[d] += 1
            elif kind == "gig_expired":
                self.expired[d] += 1
            elif kind == "ledger":
                line = e["line"]
                oid = line.get("orderId")
                if line["kind"] in ("late_refund", "undelivered_penalty") and oid and oid not in self.seen_late_ids:
                    self.seen_late_ids.add(oid)
                    self.late_today[d] += 1

        for past_day in (0, 1, 2, 3):
            if desk.now >= past_day * DAY + 20 * HOUR:
                self.done_days.add(past_day)
                path = self._llm_cache_path(past_day) if self.mode == "llm" else self._rule_trace_path(past_day)
                if path.exists():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        dials = clamp_dials(data.get("dials") or data.get("raw_answer") or data)
                        desk.p.price_target_win = dials["price_target_win"]
                        desk.p.min_supply = dials["min_supply"]
                        desk.p.fee_open = dials["fee_open"]
                    except Exception:
                        pass
