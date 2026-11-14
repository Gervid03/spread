"""OracleDesk (Layer 2 of TAS): keeps Champion v5's staffing and physical gates verbatim
while choosing and pricing orders using the fork price oracle with profit-per-driver-block + trust-velocity + deadband steering."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from spread.types import PriceRequest

from ..policy import DAY, Desk, Params


@dataclass
class OracleParams(Params):
    oracle_backlog_mult: float = 1.30
    oracle_min_net_eur: float = 14.0
    oracle_min_margin_frac: float = 0.22
    oracle_min_yield: float = 13.0
    oracle_load_yield_slope: float = 22.0
    oracle_deadend_block_add: float = 0.35
    oracle_sd_hub_pen_eur: float = 4.0
    oracle_sd_thin_pen_eur: float = 14.0
    oracle_trust_bonus_eur: float = 12.0
    oracle_dealer_share_cap: float = 0.68
    oracle_mon_dealer_cap: float = 0.68
    oracle_super_yield: float = 42.0
    oracle_max_week_orders: int = 345


class OracleDesk(Desk):
    """Subclass of Champion v5 Desk whose staffing/fees/offers/pairing are 100% unchanged.
    Delegates physical gate checks directly to `super().price(request)`."""

    Params = OracleParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.oracle_in_flight: set[str] = set()
        self._probing_feasibility: bool = False
        self.dealer_day_seen: dict[tuple[int, str], int] = Counter()
        self.dealer_day_won: dict[tuple[int, str], int] = Counter()

    def handle(self, e: dict) -> None:
        kind = e["kind"]
        if kind == "price_request":
            req = e["request"]
            self.dealer_day_seen[(self.now // DAY, req["dealerId"])] += 1
        elif kind == "order_won":
            oid = e["order"]["id"]
            self.oracle_in_flight.discard(oid)
            req = self.requests.get(oid)
            if req is not None:
                self.dealer_day_won[(req["arrivedAt"] // DAY, req["dealerId"])] += 1
        elif kind == "order_lost":
            self.oracle_in_flight.discard(e["requestId"])
        super().handle(e)

    def backlog_near(self, place: str, include_in_flight: bool = True) -> float:
        p, radius, n = self.p, self.p.supply_radius_km, 0.0
        for order in self.orders.values():
            if self.geo.line_km(order["legs"][0]["pickup"]["placeId"], place) <= radius and not self.staffed(order):
                if p.backlog_multiday_weight != 1.0 and order["deadline"] // DAY > self.now // DAY and order["id"] not in self.urgent:
                    n += p.backlog_multiday_weight
                else:
                    n += 1.0
        if include_in_flight and not self._probing_feasibility:
            for req_id in self.oracle_in_flight:
                req = self.requests.get(req_id)
                if req and req_id not in self.orders and req_id not in self.lost_requests and self.now <= req["respondBy"]:
                    if self.geo.line_km(req["legs"][0]["pickup"]["placeId"], place) <= radius:
                        n += 0.5
        return n

    def feasible_options(self, request: PriceRequest) -> tuple[list[str], dict]:
        p: OracleParams = self.p  # type: ignore[assignment]
        saved_p = self.p
        self._probing_feasibility = True
        try:
            self.p = replace(p, backlog_ratio=p.backlog_ratio * p.oracle_backlog_mult)
            prices, _ = super().price(request)
        finally:
            self.p = saved_p
            self._probing_feasibility = False

        legs = request["legs"]
        pickup = legs[0]["pickup"]["placeId"]
        deliv = legs[-1]["delivery"]["placeId"]
        supply = self.supply.get(pickup, 0)
        gate_supply = self.gate_supply.get(pickup, 0)
        dest_supply = self.supply.get(deliv, 0)
        drive = sum(self.geo.minutes(leg["pickup"]["placeId"], leg["delivery"]["placeId"]) for leg in legs)
        if len(legs) == 2:
            drive += self.geo.minutes(legs[0]["delivery"]["placeId"], legs[1]["pickup"]["placeId"])

        tight = self.tightening()
        gate_min = p.min_supply * (1 + (p.guard_supply_mult - 1) * tight)
        if gate_supply < gate_min:
            max_backlog = float(p.backlog_min) * p.oracle_backlog_mult
        else:
            max_backlog = max(p.backlog_min, p.backlog_ratio * p.oracle_backlog_mult * gate_supply) * (1 - tight)

        meta = {
            "pickup": pickup,
            "deliv": deliv,
            "supply": supply,
            "gate_supply": gate_supply,
            "dest_supply": dest_supply,
            "drive": drive,
            "max_backlog": max(1.0, max_backlog),
        }
        return list(prices.keys()), meta

    def expected_fee_eur(self, request: PriceRequest, kind: str, meta: dict) -> float:
        ref = request["referenceFeeCents"] / 100.0
        ds = meta["dest_supply"]
        ps = meta["supply"]
        drive = meta["drive"]
        mult = 0.85 if ds >= 150 else (0.93 if ds >= 40 else 1.03)
        if kind == "same_day":
            mult += 0.05 if (ps >= 90 and drive <= 180) else 0.11
        elif kind == "within_3_days":
            mult -= 0.03
        if ps < 22:
            mult += 0.05
        if drive > 280:
            mult += 0.08 * ((drive - 280) / 100.0)
        return max(1.0, ref * mult)

    def driver_blocks(self, kind: str, meta: dict) -> float:
        p: OracleParams = self.p  # type: ignore[assignment]
        blocks = 1.0 + (meta["drive"] / 150.0)
        if meta["dest_supply"] < 25:
            blocks += p.oracle_deadend_block_add
        if kind == "same_day" and meta["supply"] < 100:
            blocks += 0.20
        return blocks

    def choose_from_limits(self, request: PriceRequest, limits_cents: dict[str, int], meta: dict) -> tuple[str | None, int, float]:
        p: OracleParams = self.p  # type: ignore[assignment]
        if len(self.orders) + len(self.oracle_in_flight) >= p.oracle_max_week_orders:
            return None, 0, -1.0

        cur_bl = self.backlog_near(meta["pickup"], include_in_flight=True)
        if cur_bl + 1e-9 >= meta["max_backlog"]:
            return None, 0, -1.0

        load_ratio = min(1.0, max(0.0, cur_bl / max(1.0, meta["max_backlog"])))
        day = self.now // DAY
        fri_scale = 0.65 if day == 4 else 1.0
        min_net = p.oracle_min_net_eur * fri_scale
        min_frac = p.oracle_min_margin_frac * fri_scale
        yield_hurdle = p.oracle_min_yield * fri_scale + p.oracle_load_yield_slope * (load_ratio ** 1.3)

        dealer = request["dealerId"]
        trust = self.dealer_trust.get(dealer, 0)
        seen = self.dealer_day_seen.get((day, dealer), 1)
        won = self.dealer_day_won.get((day, dealer), 0) + sum(
            1 for r_id in self.oracle_in_flight if self.requests[r_id]["dealerId"] == dealer and self.requests[r_id]["arrivedAt"] // DAY == day
        )
        cap = p.oracle_mon_dealer_cap if day == 0 else (p.oracle_dealer_share_cap if day < 4 else 1.0)

        trust_bonus = 0.0
        if day <= 2 and trust < 25 and meta["drive"] <= 180 and meta["supply"] >= 50:
            trust_bonus = p.oracle_trust_bonus_eur * ((3 - day) / 3.0)

        best_kind: str | None = None
        best_cents = 0
        best_val_eur = -1e9
        best_yield = -1e9

        for kind, lo_cents in limits_cents.items():
            if not lo_cents or lo_cents <= 0:
                continue
            lim_eur = lo_cents / 100.0
            cost_eur = self.expected_fee_eur(request, kind, meta)
            net_eur = lim_eur - cost_eur
            if net_eur < max(min_net, cost_eur * min_frac):
                continue
            hub_sd_ok = meta["supply"] >= 100 and meta["drive"] <= 180 and load_ratio < 0.72
            sd_pen = (p.oracle_sd_hub_pen_eur if hub_sd_ok else p.oracle_sd_thin_pen_eur) if kind == "same_day" else 0.0
            sd_t_bonus = 0.25 * trust_bonus if (kind == "same_day" and hub_sd_ok) else 0.0
            adj_val = net_eur + trust_bonus + sd_t_bonus - sd_pen
            blk_yield = adj_val / self.driver_blocks(kind, meta)
            if blk_yield < yield_hurdle:
                continue
            if adj_val > best_val_eur:
                best_val_eur = adj_val
                best_yield = blk_yield
                best_kind = kind
                best_cents = lo_cents

        if best_kind is None:
            return None, 0, -1.0

        if day < 4 and seen >= 7 and (won + 1) / seen > cap and best_yield < p.oracle_super_yield:
            self.stats["oracle_dealer_cap_skip"] += 1
            return None, 0, -1.0

        return best_kind, best_cents, best_yield
