"""QRSIP simulation engine (L4): the deterministic event loop (spec §18, §20).

This module ties together execution, portfolio accounting, and risk to produce
deterministic backtest results over a point-in-time market dataset.

Event-loop contract (one iteration per dataset timestamp):

1. **Fill pending orders** at the current bar's *open* price (ADR-0005: fills
   occur strictly after the decision that generated them).
2. **Mark the portfolio** to the current bar's *close* price.
3. **Verify the accounting identity** (spec §25): equity == initial_cash +
   realized_pnl + unrealized_pnl - commissions.
4. **Record an equity point.**
5. **Evaluate the drawdown circuit breaker** (spec §19): halt when the
   peak-to-trough decline reaches ``max_drawdown``.
6. **If not halted and not the last bar**, evaluate strategy signals and queue
   approved orders for the next bar.

The engine never invents values: unaffordable trades are rejected, unmarked
positions refuse valuation, and every fill must occur strictly after the
decision that produced it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from qrsip.data.contract import Bar
from qrsip.data.dataset import MarketDataset
from qrsip.errors import ConfigurationError, QRSIPError
from qrsip.quant.signals import Signal, SignalStrategy
from qrsip.simulation.execution import (
    CostModel,
    Fill,
    Order,
    OrderSide,
    affordable_buy_quantity,
    execute_order,
)
from qrsip.simulation.portfolio import Portfolio, Position
from qrsip.simulation.risk import RiskEngine, RiskLimits, RiskPolicy

__all__ = [
    "EquityPoint",
    "FillRecord",
    "HaltRecord",
    "RejectionRecord",
    "SimulationConfig",
    "SimulationResult",
    "run_simulation",
]


# -- configuration -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Validated simulation parameters.

    ``order_quantity`` overrides the default position-sizing logic (which uses
    :func:`~qrsip.simulation.execution.affordable_buy_quantity` for buys).
    Required for opening short positions when ``allow_short`` is ``True``.

    ``allow_short`` controls whether SELL orders that create negative positions
    are permitted. Closing an existing long position is always allowed.
    """

    initial_cash: float
    cost_model: CostModel = field(default_factory=CostModel)
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    risk_policy: str = RiskPolicy.REJECT
    allow_short: bool = False
    order_quantity: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.initial_cash) or self.initial_cash <= 0.0:
            raise ConfigurationError(
                "initial_cash must be finite and positive", value=self.initial_cash
            )
        if self.order_quantity is not None and (
            not math.isfinite(self.order_quantity) or self.order_quantity <= 0.0
        ):
            raise ConfigurationError(
                "order_quantity must be finite and positive when set",
                value=self.order_quantity,
            )
        if self.risk_policy not in RiskPolicy._VALID:
            raise ConfigurationError(
                "unknown risk_policy",
                value=self.risk_policy,
                allowed=sorted(RiskPolicy._VALID),
            )


# -- audit record types (all frozen) -------------------------------------------


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """One point on the equity curve, recorded after marking at bar close."""

    timestamp: datetime
    equity: float
    cash: float
    market_value: float


@dataclass(frozen=True, slots=True)
class FillRecord:
    """A fill and the realized PnL it produced (zero when opening)."""

    fill: Fill
    realized_pnl: float


@dataclass(frozen=True, slots=True)
class RejectionRecord:
    """An order rejected by risk, affordability, or the allow_short constraint."""

    order: Order
    reasons: tuple[str, ...]
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class HaltRecord:
    """Records the moment the drawdown circuit breaker activated."""

    timestamp: datetime
    equity: float
    peak_equity: float
    drawdown: float
    pending_cancelled: int


# -- result container ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Immutable container for the complete simulation output.

    ``final_portfolio`` is an isolated copy; mutating it does not affect
    engine state.
    """

    equity_curve: tuple[EquityPoint, ...]
    fills: tuple[FillRecord, ...]
    rejections: tuple[RejectionRecord, ...]
    halt: HaltRecord | None
    final_portfolio: Portfolio
    halted: bool
    config: SimulationConfig
    dataset_id: str
    dataset_version: str
    dataset_checksum: str
    is_fixture: bool
    limitations: tuple[str, ...]
    bar_count: int
    instrument_count: int


# -- internal helpers ----------------------------------------------------------


def _copy_portfolio(portfolio: Portfolio) -> Portfolio:
    """Create an isolated shallow copy so the result cannot alias engine state."""
    copy = Portfolio(initial_cash=portfolio.initial_cash)
    copy.cash = portfolio.cash
    copy.positions = {
        inst: Position(
            quantity=pos.quantity,
            average_price=pos.average_price,
            realized_pnl=pos.realized_pnl,
        )
        for inst, pos in portfolio.positions.items()
    }
    copy.marks = dict(portfolio.marks)
    copy.realized_events = list(portfolio.realized_events)
    copy.total_commission = portfolio.total_commission
    copy.total_slippage_cost = portfolio.total_slippage_cost
    return copy


def _bar_at(dataset: MarketDataset, instrument: str, timestamp: datetime) -> Bar | None:
    """Return the bar for ``instrument`` at ``timestamp``, or ``None``."""
    for bar in dataset.bars_for(instrument):
        if bar.timestamp == timestamp:
            return bar
    return None


def _signal_to_order(
    *,
    signal: Signal,
    instrument: str,
    current_pos: float,
    current_time: datetime,
    last_close: float,
    config: SimulationConfig,
    cash: float,
) -> Order | None:
    """Convert a target signal into at most one order, or ``None``.

    Crossing (e.g., short → long) is handled incrementally: the engine first
    closes the existing position and the strategy will re-signal next bar.
    """
    if signal is Signal.LONG:
        if current_pos > 0.0:
            return None  # already long
        if current_pos < 0.0:
            # Close short first (buy to cover).
            return Order(
                decision_time=current_time,
                instrument=instrument,
                side=OrderSide.BUY,
                quantity=abs(current_pos),
                reason="close short (target LONG)",
            )
        # Flat → open long.
        if config.order_quantity is not None:
            qty = config.order_quantity
        else:
            qty = affordable_buy_quantity(cash, price=last_close, cost_model=config.cost_model)
        if qty <= 0.0:
            return None
        return Order(
            decision_time=current_time,
            instrument=instrument,
            side=OrderSide.BUY,
            quantity=qty,
            reason="LONG signal",
        )

    if signal is Signal.SHORT:
        if current_pos < 0.0:
            return None  # already short
        if current_pos > 0.0:
            # Close long — always allowed regardless of allow_short.
            return Order(
                decision_time=current_time,
                instrument=instrument,
                side=OrderSide.SELL,
                quantity=current_pos,
                reason="close long (target SHORT)",
            )
        # Flat → open short.
        if not config.allow_short:
            return None
        if config.order_quantity is None:
            return None  # explicit quantity required for short opens
        return Order(
            decision_time=current_time,
            instrument=instrument,
            side=OrderSide.SELL,
            quantity=config.order_quantity,
            reason="SHORT signal",
        )

    # Signal.FLAT → close any open position.
    if signal is Signal.FLAT:
        if current_pos > 0.0:
            return Order(
                decision_time=current_time,
                instrument=instrument,
                side=OrderSide.SELL,
                quantity=current_pos,
                reason="close long (target FLAT)",
            )
        if current_pos < 0.0:
            return Order(
                decision_time=current_time,
                instrument=instrument,
                side=OrderSide.BUY,
                quantity=abs(current_pos),
                reason="close short (target FLAT)",
            )
        return None  # already flat


# -- main event loop -----------------------------------------------------------


def run_simulation(
    dataset: MarketDataset,
    strategies: dict[str, SignalStrategy],
    config: SimulationConfig,
) -> SimulationResult:
    """Run a deterministic backtest over ``dataset``.

    Parameters
    ----------
    dataset:
        A validated :class:`~qrsip.data.dataset.MarketDataset` providing
        point-in-time bars.
    strategies:
        Mapping of instrument name to :class:`~qrsip.quant.signals.SignalStrategy`.
        Instruments not in this dict are not traded.  Use
        ``dict.fromkeys(dataset.instruments, strategy)`` when one strategy
        covers all instruments.
    config:
        Validated simulation parameters.

    Returns
    -------
    SimulationResult
        Frozen result container with equity curve, fill log, rejections, halt
        record, and an isolated copy of the final portfolio.

    Raises
    ------
    QRSIPError
        When the dataset has no timestamps or an accounting identity violation
        is detected (should never occur if the code is correct).
    """
    timestamps = dataset.timestamps
    if not timestamps:
        raise QRSIPError("dataset contains no timestamps; simulation requires data")

    portfolio = Portfolio(initial_cash=config.initial_cash)
    risk_engine = RiskEngine(config.risk_limits, policy=config.risk_policy)

    pending_orders: list[Order] = []
    equity_curve: list[EquityPoint] = []
    fill_records: list[FillRecord] = []
    rejection_records: list[RejectionRecord] = []
    halt_record: HaltRecord | None = None
    peak_equity: float = config.initial_cash
    halted: bool = False

    for i, current_time in enumerate(timestamps):
        # -- Phase 1: fill pending orders at current bar's open ----------------
        # Sort SELLs before BUYs so cash is freed before buying.
        pending_sorted = sorted(
            pending_orders,
            key=lambda o: (0 if o.side is OrderSide.SELL else 1, o.instrument),
        )
        for order in pending_sorted:
            bar = _bar_at(dataset, order.instrument, current_time)
            if bar is None:
                rejection_records.append(
                    RejectionRecord(
                        order=order,
                        reasons=("no bar for instrument at fill timestamp",),
                        timestamp=current_time,
                    )
                )
                continue

            # Determine fill quantity.
            if order.side is OrderSide.BUY:
                affordable = affordable_buy_quantity(
                    portfolio.cash, price=bar.open, cost_model=config.cost_model
                )
                qty = min(order.quantity, affordable)
                if qty <= 0.0:
                    rejection_records.append(
                        RejectionRecord(
                            order=order,
                            reasons=("insufficient cash at fill time",),
                            timestamp=current_time,
                        )
                    )
                    continue
            else:
                qty = order.quantity
                # Safety: prevent accidental short if allow_short is disabled.
                if not config.allow_short:
                    current_pos = portfolio.position(order.instrument).quantity
                    if current_pos - qty < -1e-9:
                        rejection_records.append(
                            RejectionRecord(
                                order=order,
                                reasons=("sell would create short position (allow_short=False)",),
                                timestamp=current_time,
                            )
                        )
                        continue

            fill = execute_order(order, bar, cost_model=config.cost_model, quantity=qty)
            realized = portfolio.apply_fill(fill)
            fill_records.append(FillRecord(fill=fill, realized_pnl=realized))

        pending_orders.clear()

        # -- Phase 2: mark portfolio at current bar's close --------------------
        for instrument in dataset.instruments:
            bar = _bar_at(dataset, instrument, current_time)
            if bar is not None:
                portfolio.mark(instrument, bar.close)

        # -- Phase 3: verify accounting identity (spec §25) --------------------
        portfolio.assert_accounting_identity()

        # -- Phase 4: record equity point --------------------------------------
        equity = portfolio.equity()
        equity_curve.append(
            EquityPoint(
                timestamp=current_time,
                equity=equity,
                cash=portfolio.cash,
                market_value=portfolio.market_value(),
            )
        )

        # -- Phase 5: update peak and evaluate drawdown circuit breaker --------
        peak_equity = max(peak_equity, equity)

        if not halted and risk_engine.drawdown_breach(equity=equity, peak_equity=peak_equity):
            dd = 1.0 - equity / peak_equity if peak_equity > 0.0 else 1.0
            halt_record = HaltRecord(
                timestamp=current_time,
                equity=equity,
                peak_equity=peak_equity,
                drawdown=dd,
                pending_cancelled=len(pending_orders),  # always 0 here
            )
            halted = True
            continue  # skip strategy evaluation

        # -- Phase 6: strategy evaluation (skip if halted or last bar) ---------
        if halted or i == len(timestamps) - 1:
            continue

        for instrument in dataset.instruments:
            strategy = strategies.get(instrument)
            if strategy is None:
                continue

            # Point-in-time: only closes up to and including current_time.
            inst_bars = dataset.bars_for(instrument)
            visible = tuple(b for b in inst_bars if b.timestamp <= current_time)
            if not visible:
                continue
            closes = tuple(b.close for b in visible)

            signal = strategy.target_signal(closes)
            current_pos = portfolio.position(instrument).quantity
            last_bar = visible[-1]

            new_order = _signal_to_order(
                signal=signal,
                instrument=instrument,
                current_pos=current_pos,
                current_time=current_time,
                last_close=last_bar.close,
                config=config,
                cash=portfolio.cash,
            )
            if new_order is None:
                continue

            # Pre-trade risk check.
            check = risk_engine.check_order(new_order, portfolio=portfolio)
            if check.approved:
                pending_orders.append(new_order)
            else:
                rejection_records.append(
                    RejectionRecord(
                        order=new_order,
                        reasons=check.reasons,
                        timestamp=current_time,
                    )
                )

    return SimulationResult(
        equity_curve=tuple(equity_curve),
        fills=tuple(fill_records),
        rejections=tuple(rejection_records),
        halt=halt_record,
        final_portfolio=_copy_portfolio(portfolio),
        halted=halted,
        config=config,
        dataset_id=dataset.descriptor.dataset_id,
        dataset_version=dataset.descriptor.version,
        dataset_checksum=dataset.checksum,
        is_fixture=dataset.is_fixture,
        limitations=dataset.limitations,
        bar_count=len(dataset),
        instrument_count=len(dataset.instruments),
    )
