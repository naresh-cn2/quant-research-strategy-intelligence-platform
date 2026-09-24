"""QRSIP execution simulation (L4): orders, fills, and cost model (spec §18; ADR-0005).

Timing contract (ADR-0005, locked by tests):

- A decision is made at the **close** of bar ``T`` (``decision_time = T``).
- The resulting market order fills at the **open of the next bar for that
  instrument** (``fill_time > decision_time`` — enforced structurally here,
  never merely by convention).
- There are no perfect fills: buy quantity is capped at the whole number of
  shares affordable at the fill price given the cost model (deterministic,
  documented), sells execute in full.

Costs are explicit (spec §18): commission in basis points plus an optional
fixed fee per fill, and slippage as a one-way basis-point penalty applied to
the fill price (buy pays up, sell receives down). Slippage is *embedded in the
fill price* so accounting identities stay honest; the informational
``slippage_cost`` on a fill reports its size.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from qrsip.data.contract import Bar
from qrsip.errors import ExecutionError

__all__ = [
    "CostModel",
    "Fill",
    "Order",
    "OrderSide",
    "affordable_buy_quantity",
    "execute_order",
]


class OrderSide(StrEnum):
    """Direction of an order."""

    BUY = "BUY"
    SELL = "SELL"


def _require_aware(timestamp: datetime, field: str) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ExecutionError(f"{field} must be timezone-aware", field=field)


def _require_positive(value: float, field: str, **context: object) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ExecutionError(
            f"{field} must be finite and positive", field=field, value=value, **context
        )


@dataclass(frozen=True, slots=True)
class Order:
    """A decision to trade, created at bar close ``decision_time`` (ADR-0005)."""

    decision_time: datetime
    instrument: str
    side: OrderSide
    quantity: float
    reason: str = ""

    def __post_init__(self) -> None:
        _require_aware(self.decision_time, "decision_time")
        if not self.instrument or not self.instrument.strip():
            raise ExecutionError("order instrument must be non-empty")
        _require_positive(self.quantity, "order.quantity", instrument=self.instrument)


@dataclass(frozen=True, slots=True)
class Fill:
    """A deterministic execution of an order at the next bar's open (ADR-0005)."""

    decision_time: datetime
    fill_time: datetime
    instrument: str
    side: OrderSide
    quantity: float
    reference_price: float  # raw next-bar open
    price: float  # reference +/- slippage
    commission: float
    slippage_cost: float

    def __post_init__(self) -> None:
        _require_aware(self.decision_time, "decision_time")
        _require_aware(self.fill_time, "fill_time")
        if self.fill_time <= self.decision_time:
            raise ExecutionError(
                "fill must occur strictly after the decision (ADR-0005)",
                decision_time=self.decision_time.isoformat(),
                fill_time=self.fill_time.isoformat(),
            )
        _require_positive(self.quantity, "fill.quantity")
        _require_positive(self.price, "fill.price")
        _require_positive(self.reference_price, "fill.reference_price")
        if self.commission < 0.0 or not math.isfinite(self.commission):
            raise ExecutionError("fill commission must be finite and non-negative")
        if self.slippage_cost < 0.0 or not math.isfinite(self.slippage_cost):
            raise ExecutionError("fill slippage_cost must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class CostModel:
    """Explicit, validated trading-cost assumptions attached to every experiment."""

    commission_bps: float = 0.0
    fixed_commission: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("commission_bps", self.commission_bps),
            ("fixed_commission", self.fixed_commission),
            ("slippage_bps", self.slippage_bps),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ExecutionError(f"{name} must be finite and non-negative", **{name: value})

    @property
    def commission_rate(self) -> float:
        """Per-notional commission as a fraction (``bps / 10_000``)."""
        return self.commission_bps / 10_000.0

    @property
    def slippage_rate(self) -> float:
        """One-way slippage as a fraction (``bps / 10_000``)."""
        return self.slippage_bps / 10_000.0

    def to_dict(self) -> dict[str, float]:
        """JSON-serializable snapshot for experiment configs."""
        return {
            "commission_bps": self.commission_bps,
            "fixed_commission": self.fixed_commission,
            "slippage_bps": self.slippage_bps,
        }


def execute_order(
    order: Order,
    bar: Bar,
    *,
    cost_model: CostModel,
    quantity: float | None = None,
) -> Fill:
    """Execute ``order`` at ``bar``'s open, applying the cost model.

    ``bar`` must be *strictly later* than ``order.decision_time`` — this is
    where ADR-0005 is enforced. ``quantity`` overrides the ordered quantity
    (used by the engine for affordability capping) and must be positive.

    Raises :class:`ExecutionError` on any contract violation (fail closed).
    """
    if bar.timestamp <= order.decision_time:
        raise ExecutionError(
            "order would fill at or before its decision time (ADR-0005 violation)",
            decision_time=order.decision_time.isoformat(),
            fill_time=bar.timestamp.isoformat(),
            instrument=order.instrument,
        )
    if bar.instrument != order.instrument:
        raise ExecutionError(
            "fill bar instrument does not match order",
            order_instrument=order.instrument,
            bar_instrument=bar.instrument,
        )
    _require_positive(bar.open, "bar.open", instrument=bar.instrument)

    qty = order.quantity if quantity is None else quantity
    _require_positive(qty, "fill.quantity")

    if order.side is OrderSide.BUY:
        slipped = bar.open * (1.0 + cost_model.slippage_rate)
    else:
        slipped = bar.open * (1.0 - cost_model.slippage_rate)
    _require_positive(slipped, "slipped price")

    commission = slipped * qty * cost_model.commission_rate + cost_model.fixed_commission
    slippage_cost = abs(slipped - bar.open) * qty

    return Fill(
        decision_time=order.decision_time,
        fill_time=bar.timestamp,
        instrument=order.instrument,
        side=order.side,
        quantity=qty,
        reference_price=bar.open,
        price=slipped,
        commission=commission,
        slippage_cost=slippage_cost,
    )


def affordable_buy_quantity(cash: float, *, price: float, cost_model: CostModel) -> float:
    """Largest whole-share buy quantity affordable given ``cash``.

    Solves ``q * price_with_slippage * (1 + commission_rate) + fixed <= cash``
    and floors to whole shares. Returns ``0.0`` when nothing (even one share)
    is affordable — the caller rejects the order; money is never invented.
    """
    if not math.isfinite(cash) or cash <= 0.0:
        return 0.0
    budget = cash - cost_model.fixed_commission
    if budget <= 0.0:
        return 0.0
    unit_cost = price * (1.0 + cost_model.slippage_rate) * (1.0 + cost_model.commission_rate)
    if unit_cost <= 0.0:
        return 0.0
    return float(math.floor(budget / unit_cost))
