"""QRSIP portfolio accounting (L4: simulation → portfolio; spec §25).

Cash-first double-entry-style accounting for simulated fills:

- Every fill moves cash and updates the position's average price and
  realized PnL. Nothing is estimated: quantities, cash, and realized PnL are
  arithmetic facts of the fills applied.
- **Accounting identity (verified, spec §25):**

      equity == initial_cash + realized_pnl + unrealized_pnl - commissions

  Slippage is embedded in fill prices (see execution), so it never appears as
  a separate term — it is already inside realized/unrealized PnL.
- ``apply_fill`` fails closed: a buy the cash cannot cover raises
  :class:`~qrsip.errors.PortfolioError` instead of allowing negative cash.

Positions are held per instrument; marks (last known prices) are supplied by
the engine from validated bars only. A position without a mark cannot be
valued, so valuation fails closed rather than defaulting to cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from qrsip.errors import PortfolioError
from qrsip.simulation.execution import Fill, OrderSide

__all__ = ["Portfolio", "Position", "RealizedEvent"]

_CASH_TOLERANCE = 1e-6


@dataclass(slots=True)
class Position:
    """One instrument's net position and its realized PnL accumulator."""

    quantity: float = 0.0  # signed: > 0 long, < 0 short
    average_price: float = 0.0
    realized_pnl: float = 0.0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0.0


@dataclass(frozen=True, slots=True)
class RealizedEvent:
    """A closed-trade PnL event produced by reducing/crossing a position."""

    instrument: str
    at: datetime
    pnl: float


@dataclass(slots=True)
class Portfolio:
    """Simulated multi-instrument portfolio with verified accounting.

    Parameters
    ----------
    initial_cash:
        Starting cash; must be finite and strictly positive.
    """

    initial_cash: float
    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    realized_events: list[RealizedEvent] = field(default_factory=list)
    total_commission: float = 0.0
    total_slippage_cost: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.initial_cash) or self.initial_cash <= 0.0:
            raise PortfolioError(
                "initial cash must be finite and positive", value=self.initial_cash
            )
        self.cash = self.initial_cash

    # -- reads ------------------------------------------------------------
    def position(self, instrument: str) -> Position:
        """Return the (possibly empty) position record for ``instrument``."""
        return self.positions.get(instrument, Position())

    def market_value(self) -> float:
        """Sum of ``quantity * mark`` over all positions; fails closed unmaked."""
        total = 0.0
        for instrument, position in self.positions.items():
            if position.quantity == 0.0:
                continue
            mark = self.marks.get(instrument)
            if mark is None:
                raise PortfolioError(
                    "position has no mark; valuation would be invented",
                    instrument=instrument,
                    quantity=position.quantity,
                )
            total += position.quantity * mark
        return total

    def equity(self) -> float:
        """Cash plus market value."""
        return self.cash + self.market_value()

    def unrealized_pnl(self) -> float:
        """Sum of ``(mark - average_price) * quantity`` over open positions."""
        total = 0.0
        for instrument, position in self.positions.items():
            if position.quantity == 0.0:
                continue
            mark = self.marks.get(instrument)
            if mark is None:
                raise PortfolioError(
                    "position has no mark; unrealized PnL would be invented",
                    instrument=instrument,
                )
            total += (mark - position.average_price) * position.quantity
        return total

    def realized_pnl(self) -> float:
        """Total realized gross PnL across instruments."""
        return sum(position.realized_pnl for position in self.positions.values())

    def gross_exposure(self) -> float:
        """Sum of absolute position market values."""
        total = 0.0
        for instrument, position in self.positions.items():
            if position.quantity == 0.0:
                continue
            mark = self.marks.get(instrument)
            if mark is None:
                raise PortfolioError("position has no mark", instrument=instrument)
            total += abs(position.quantity * mark)
        return total

    def trade_pnls(self) -> tuple[float, ...]:
        """Realized PnL events in application order (closed-trade samples)."""
        return tuple(event.pnl for event in self.realized_events)

    # -- mutation ---------------------------------------------------------
    def apply_fill(self, fill: Fill) -> float:
        """Apply a fill to cash and the position; return PnL realized by it.

        Raises :class:`~qrsip.errors.PortfolioError` when a buy would drive
        cash below ``-_CASH_TOLERANCE`` (fail closed — money is never
        invented). Commission always reduces cash; slippage is embedded in
        ``fill.price`` already.
        """
        position = self.positions.setdefault(fill.instrument, Position())
        signed = fill.quantity if fill.side is OrderSide.BUY else -fill.quantity

        if fill.side is OrderSide.BUY:
            cost = fill.quantity * fill.price + fill.commission
            if self.cash + _CASH_TOLERANCE < cost:
                raise PortfolioError(
                    "buy fill exceeds available cash (fail closed)",
                    instrument=fill.instrument,
                    cash=self.cash,
                    cost=cost,
                )
            self.cash -= cost
        else:
            self.cash += fill.quantity * fill.price - fill.commission

        old_quantity = position.quantity
        realized = 0.0

        if old_quantity == 0.0:
            # Open a new position.
            position.quantity = signed
            position.average_price = fill.price
        elif old_quantity * signed > 0:
            # Increasing: weighted-average the entry price.
            total = old_quantity + signed
            position.average_price = (
                abs(old_quantity) * position.average_price + abs(signed) * fill.price
            ) / abs(total)
            position.quantity = total
        else:
            # Reducing, closing, or crossing.
            direction = 1.0 if old_quantity > 0.0 else -1.0
            closed = min(abs(old_quantity), abs(signed))
            realized = (fill.price - position.average_price) * closed * direction
            position.realized_pnl += realized
            remaining = old_quantity + signed
            if remaining == 0.0:
                position.quantity = 0.0
                position.average_price = 0.0
            elif old_quantity * remaining > 0:
                position.quantity = remaining  # still same side; entry unchanged
            else:
                # Crossed through zero: the residual opens at the fill price.
                position.quantity = remaining
                position.average_price = fill.price
            if realized != 0.0:
                self.realized_events.append(
                    RealizedEvent(instrument=fill.instrument, at=fill.fill_time, pnl=realized)
                )

        self.total_commission += fill.commission
        self.total_slippage_cost += fill.slippage_cost
        # A closed or reduced position invalidates a stale mark? No: mark
        # persists per instrument and is refreshed by the engine each bar.
        return realized

    def mark(self, instrument: str, price: float) -> None:
        """Record the latest known price for ``instrument`` (validated input)."""
        if not math.isfinite(price) or price <= 0.0:
            raise PortfolioError(
                "mark price must be finite and positive",
                instrument=instrument,
                value=price,
            )
        self.marks[instrument] = price

    # -- verification -----------------------------------------------------
    def assert_accounting_identity(self) -> None:
        """Verify ``equity == initial + realized + unrealized - commissions``.

        Raises :class:`~qrsip.errors.PortfolioError` with both sides on
        mismatch (tolerance 1e-6 absolute — see ADR-0006 tolerance policy).
        """
        lhs = self.equity()
        rhs = (
            self.initial_cash + self.realized_pnl() + self.unrealized_pnl() - self.total_commission
        )
        if abs(lhs - rhs) > _CASH_TOLERANCE:
            raise PortfolioError(
                "accounting identity violated",
                equity=lhs,
                expected=rhs,
                cash=self.cash,
                realized=self.realized_pnl(),
                unrealized=self.unrealized_pnl(),
                commissions=self.total_commission,
            )
