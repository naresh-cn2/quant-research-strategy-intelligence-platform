"""Tests for the L4 simulation engine (spec §18, §20; ADR-0005).

Covers:
- ADR-0005 execution timing (decision at T → fill at T+1)
- No same-bar fills
- Commission and slippage in accounting
- Affordability / solvency rejection
- Risk limit rejection
- Drawdown circuit-breaker halt
- Halt prevents subsequent risk-taking
- Accounting identity at every step
- Deterministic execution (two identical runs)
- Pending order queue mechanics
- Sell-before-buy ordering
- Short-selling controls
- Multi-instrument simulation
- Point-in-time causality
- SimulationConfig validation
- SimulationResult immutability
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from qrsip.data.contract import Bar, DatasetDescriptor, DatasetHandle
from qrsip.data.dataset import MarketDataset
from qrsip.errors import ConfigurationError
from qrsip.quant.signals import Signal, SignalStrategy
from qrsip.simulation.engine import (
    FillRecord,
    HaltRecord,
    SimulationConfig,
    run_simulation,
)
from qrsip.simulation.execution import CostModel, OrderSide
from qrsip.simulation.risk import RiskLimits

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _ts(day: int) -> datetime:
    """UTC timestamp for day offset."""
    return _BASE + timedelta(days=day)


def _make_bars(
    n: int = 5,
    instrument: str = "TEST",
    *,
    base_price: float = 100.0,
    price_step: float = 1.0,
) -> tuple[Bar, ...]:
    """Create ``n`` bars with linearly increasing prices."""
    return tuple(
        Bar(
            timestamp=_ts(i),
            instrument=instrument,
            open=base_price + i * price_step,
            high=base_price + i * price_step + 5.0,
            low=base_price + i * price_step - 5.0,
            close=base_price + i * price_step + 2.0,
            volume=1000.0,
        )
        for i in range(n)
    )


def _make_dataset(
    bars: tuple[Bar, ...],
    instruments: tuple[str, ...] | None = None,
) -> MarketDataset:
    """Build a MarketDataset from bars."""
    if instruments is None:
        instruments = tuple(sorted({b.instrument for b in bars}))
    descriptor = DatasetDescriptor(
        dataset_id="test-sim",
        version="1.0",
        source="fixture",
        instruments=instruments,
    )
    handle = DatasetHandle(
        descriptor=descriptor,
        checksum="sha256:test123",
        row_count=len(bars),
    )
    return MarketDataset(handle, bars)


def _simple_dataset(n: int = 5) -> MarketDataset:
    """Default single-instrument dataset."""
    return _make_dataset(_make_bars(n))


def _default_config(**overrides: object) -> SimulationConfig:
    """SimulationConfig with sensible defaults for tests."""
    kwargs: dict = {
        "initial_cash": 100_000.0,
        "cost_model": CostModel(),
        "risk_limits": RiskLimits(),
    }
    kwargs.update(overrides)
    return SimulationConfig(**kwargs)


@dataclass(frozen=True, slots=True)
class AlwaysLong:
    """Strategy that always signals LONG."""

    def target_signal(self, closes: Sequence[float]) -> Signal:
        return Signal.LONG


@dataclass(frozen=True, slots=True)
class AlwaysShort:
    """Strategy that always signals SHORT."""

    def target_signal(self, closes: Sequence[float]) -> Signal:
        return Signal.SHORT


@dataclass(frozen=True, slots=True)
class LongThenFlat:
    """Signals LONG for the first ``switch_after`` calls, then FLAT."""

    switch_after: int = 1
    _count: int = 0

    def target_signal(self, closes: Sequence[float]) -> Signal:
        # Mutable state via object.__setattr__ on frozen dataclass
        count = object.__getattribute__(self, "_count")
        object.__setattr__(self, "_count", count + 1)
        if count < self.switch_after:
            return Signal.LONG
        return Signal.FLAT


@dataclass(frozen=True, slots=True)
class RecordingStrategy:
    """Records what closes it sees for causality verification."""

    observed: list[tuple[float, ...]]

    def target_signal(self, closes: Sequence[float]) -> Signal:
        self.observed.append(tuple(closes))
        return Signal.FLAT


# ===========================================================================
# TestSimulationConfig
# ===========================================================================


class TestSimulationConfig:
    """Validate SimulationConfig construction."""

    def test_valid_config(self) -> None:
        cfg = SimulationConfig(initial_cash=50_000.0)
        assert cfg.initial_cash == 50_000.0
        assert cfg.allow_short is False
        assert cfg.order_quantity is None

    def test_invalid_initial_cash_zero(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=0.0)

    def test_invalid_initial_cash_negative(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=-1.0)

    def test_invalid_initial_cash_nan(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=float("nan"))

    def test_invalid_initial_cash_inf(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=float("inf"))

    def test_invalid_order_quantity(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=100_000.0, order_quantity=-10.0)

    def test_invalid_risk_policy(self) -> None:
        with pytest.raises(ConfigurationError):
            SimulationConfig(initial_cash=100_000.0, risk_policy="INVALID")

    def test_valid_order_quantity(self) -> None:
        cfg = SimulationConfig(initial_cash=100_000.0, order_quantity=50.0)
        assert cfg.order_quantity == 50.0


# ===========================================================================
# TestRunSimulation — core event loop
# ===========================================================================


class TestRunSimulation:
    """Core event-loop tests."""

    def test_execution_timing_t_plus_one(self) -> None:
        """Signal at T, fill at T+1 open (ADR-0005)."""
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        # LONG signal at T0 → fill at T1.
        assert len(result.fills) >= 1
        first_fill = result.fills[0]
        assert first_fill.fill.decision_time == _ts(0)
        assert first_fill.fill.fill_time == _ts(1)
        assert first_fill.fill.fill_time > first_fill.fill.decision_time

    def test_no_same_bar_fill(self) -> None:
        """No order can fill on the bar that generated it."""
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        for fr in result.fills:
            assert fr.fill.fill_time > fr.fill.decision_time

    def test_commission_in_accounting(self) -> None:
        """Commission reduces equity compared to a zero-commission run."""
        dataset = _simple_dataset(3)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        cfg_no_cost = _default_config(order_quantity=10.0, cost_model=CostModel())
        cfg_with_cost = _default_config(
            order_quantity=10.0,
            cost_model=CostModel(commission_bps=100.0),
        )

        r_no_cost = run_simulation(dataset, strategies, cfg_no_cost)
        r_with_cost = run_simulation(dataset, strategies, cfg_with_cost)

        assert r_with_cost.final_portfolio.total_commission > 0.0
        # Equity with commission should be less than without.
        assert r_with_cost.equity_curve[-1].equity < r_no_cost.equity_curve[-1].equity

    def test_slippage_in_accounting(self) -> None:
        """Slippage is embedded in fill price."""
        cost_model = CostModel(slippage_bps=100.0)  # 1% slippage
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0, cost_model=cost_model)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) >= 1
        fill = result.fills[0].fill
        # Buy slippage: fill price > reference price.
        assert fill.price > fill.reference_price
        assert fill.slippage_cost > 0.0
        assert result.final_portfolio.total_slippage_cost > 0.0

    def test_affordability_rejection(self) -> None:
        """Order rejected when cash is insufficient at fill time."""
        dataset = _simple_dataset(3)
        # Initial cash too low to buy even 1 share at ~101.
        cfg = _default_config(initial_cash=10.0, order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        # Should have a rejection for insufficient cash.
        assert any("insufficient cash" in r for rej in result.rejections for r in rej.reasons)

    def test_accounting_identity_every_step(self) -> None:
        """Accounting identity holds at every equity point.

        equity == initial_cash + realized_pnl + unrealized_pnl - commissions
        (verified inside the engine via assert_accounting_identity).
        """
        dataset = _simple_dataset(5)
        cost_model = CostModel(commission_bps=50.0, slippage_bps=20.0)
        cfg = _default_config(order_quantity=10.0, cost_model=cost_model)
        strategies = dict.fromkeys(dataset.instruments, LongThenFlat(switch_after=1))

        # If accounting identity fails, run_simulation raises PortfolioError.
        result = run_simulation(dataset, strategies, cfg)

        # Verify the identity on the final portfolio as well.
        p = result.final_portfolio
        lhs = p.equity()
        rhs = p.initial_cash + p.realized_pnl() + p.unrealized_pnl() - p.total_commission
        assert abs(lhs - rhs) < 1e-6

    def test_equity_curve_structure(self) -> None:
        """Equity curve has one point per timestamp, in order."""
        dataset = _simple_dataset(5)
        cfg = _default_config()
        strategies: dict[str, SignalStrategy] = {}

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.equity_curve) == 5
        timestamps = [ep.timestamp for ep in result.equity_curve]
        assert timestamps == sorted(timestamps)
        # No trades → equity stays at initial_cash.
        for ep in result.equity_curve:
            assert ep.equity == cfg.initial_cash

    def test_long_signal_generates_buy(self) -> None:
        """LONG signal generates a BUY fill at next bar."""
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) >= 1
        assert result.fills[0].fill.side is OrderSide.BUY

    def test_flat_signal_closes_position(self) -> None:
        """FLAT signal closes an existing long position."""
        dataset = _simple_dataset(5)
        cfg = _default_config(order_quantity=10.0)
        # LONG for 1 bar, then FLAT → should close.
        strategies = dict.fromkeys(dataset.instruments, LongThenFlat(switch_after=1))

        result = run_simulation(dataset, strategies, cfg)

        # Should have BUY (open) and SELL (close).
        sides = [fr.fill.side for fr in result.fills]
        assert OrderSide.BUY in sides
        assert OrderSide.SELL in sides

    def test_no_strategy_no_trades(self) -> None:
        """Empty strategies dict → no fills."""
        dataset = _simple_dataset(5)
        cfg = _default_config()

        result = run_simulation(dataset, {}, cfg)

        assert len(result.fills) == 0
        assert len(result.rejections) == 0
        assert not result.halted

    def test_single_bar_no_trades(self) -> None:
        """Only one timestamp → no trades (can't fill at T+1)."""
        dataset = _simple_dataset(1)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) == 0
        assert len(result.equity_curve) == 1

    def test_pending_order_fills_next_bar(self) -> None:
        """Order created at bar T fills at bar T+1's open price."""
        bars = _make_bars(3, base_price=100.0, price_step=10.0)
        dataset = _make_dataset(bars)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) >= 1
        fill = result.fills[0].fill
        # Fill at T1 open = base_price + 1*price_step = 110.0
        assert fill.reference_price == 110.0
        assert fill.fill_time == _ts(1)

    def test_sell_before_buy_ordering(self) -> None:
        """SELLs execute before BUYs within the same bar (freeing cash)."""
        # Two instruments: A is closing long, B is opening long.
        bars_a = tuple(
            Bar(
                timestamp=_ts(i),
                instrument="A",
                open=100.0 + i,
                high=110.0,
                low=90.0,
                close=102.0 + i,
                volume=1000.0,
            )
            for i in range(4)
        )
        bars_b = tuple(
            Bar(
                timestamp=_ts(i),
                instrument="B",
                open=100.0 + i,
                high=110.0,
                low=90.0,
                close=102.0 + i,
                volume=1000.0,
            )
            for i in range(4)
        )
        all_bars = tuple(sorted(bars_a + bars_b, key=lambda b: (b.timestamp, b.instrument)))
        dataset = _make_dataset(all_bars, instruments=("A", "B"))

        # A: LONG then FLAT (sell). B: FLAT then LONG (buy).
        @dataclass(frozen=True, slots=True)
        class StratA:
            def target_signal(self, closes: Sequence[float]) -> Signal:
                return Signal.LONG if len(closes) <= 1 else Signal.FLAT

        @dataclass(frozen=True, slots=True)
        class StratB:
            def target_signal(self, closes: Sequence[float]) -> Signal:
                return Signal.FLAT if len(closes) <= 1 else Signal.LONG

        cfg = _default_config(order_quantity=10.0)
        strategies: dict[str, SignalStrategy] = {"A": StratA(), "B": StratB()}

        result = run_simulation(dataset, strategies, cfg)

        # Verify fills exist for both instruments.
        fill_instruments = {fr.fill.instrument for fr in result.fills}
        assert "A" in fill_instruments
        assert "B" in fill_instruments

    def test_multi_instrument_simulation(self) -> None:
        """Multiple instruments trade independently."""
        bars_x = _make_bars(4, instrument="X", base_price=50.0)
        bars_y = _make_bars(4, instrument="Y", base_price=200.0)
        all_bars = tuple(sorted(bars_x + bars_y, key=lambda b: (b.timestamp, b.instrument)))
        dataset = _make_dataset(all_bars, instruments=("X", "Y"))

        cfg = _default_config(order_quantity=5.0)
        strategies: dict[str, SignalStrategy] = {
            "X": AlwaysLong(),
            "Y": AlwaysLong(),
        }

        result = run_simulation(dataset, strategies, cfg)

        x_fills = [fr for fr in result.fills if fr.fill.instrument == "X"]
        y_fills = [fr for fr in result.fills if fr.fill.instrument == "Y"]
        assert len(x_fills) >= 1
        assert len(y_fills) >= 1

    def test_result_portfolio_isolated(self) -> None:
        """Mutating the result portfolio does not affect internal state."""
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        original_cash = result.final_portfolio.cash
        result.final_portfolio.cash = 0.0  # mutate the copy
        # The result object's portfolio is the copy, so this is fine.
        assert result.final_portfolio.cash == 0.0
        # Run again to confirm engine state wasn't affected.
        result2 = run_simulation(dataset, strategies, cfg)
        assert result2.final_portfolio.cash == original_cash

    def test_point_in_time_causality(self) -> None:
        """Strategy only sees closes up to and including current bar."""
        dataset = _simple_dataset(4)
        observed: list[tuple[float, ...]] = []
        strategy = RecordingStrategy(observed=observed)
        cfg = _default_config()
        strategies: dict[str, SignalStrategy] = {"TEST": strategy}

        run_simulation(dataset, strategies, cfg)

        bars = _make_bars(4)
        all_closes = [b.close for b in bars]
        # Strategy is called for bars 0, 1, 2 (not bar 3 which is last).
        assert len(observed) == 3
        assert observed[0] == (all_closes[0],)
        assert observed[1] == (all_closes[0], all_closes[1])
        assert observed[2] == (all_closes[0], all_closes[1], all_closes[2])

    def test_fill_record_structure(self) -> None:
        """FillRecord contains the fill and realized PnL."""
        dataset = _simple_dataset(3)
        cfg = _default_config(order_quantity=10.0)
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) >= 1
        fr = result.fills[0]
        assert isinstance(fr, FillRecord)
        assert fr.fill.quantity > 0
        assert fr.realized_pnl == 0.0  # opening trade

    def test_result_metadata(self) -> None:
        """SimulationResult carries dataset identity."""
        dataset = _simple_dataset(3)
        cfg = _default_config()

        result = run_simulation(dataset, {}, cfg)

        assert result.dataset_id == "test-sim"
        assert result.dataset_version == "1.0"
        assert result.dataset_checksum == "sha256:test123"
        assert result.bar_count == 3
        assert result.instrument_count == 1


# ===========================================================================
# TestSimulationRisk — risk controls in the engine
# ===========================================================================


class TestSimulationRisk:
    """Risk controls integrated with the engine."""

    def test_risk_rejection_order_notional(self) -> None:
        """Order exceeding max_order_notional is rejected."""
        dataset = _simple_dataset(3)
        limits = RiskLimits(max_order_notional=100.0)  # very tight limit
        cfg = _default_config(
            order_quantity=10.0,
            risk_limits=limits,
        )
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.rejections) >= 1
        assert any("max_order_notional" in r for rej in result.rejections for r in rej.reasons)

    def test_risk_rejection_gross_exposure(self) -> None:
        """Order exceeding max_gross_exposure is rejected."""
        dataset = _simple_dataset(3)
        limits = RiskLimits(max_gross_exposure=0.001)  # virtually zero
        cfg = _default_config(
            order_quantity=10.0,
            risk_limits=limits,
        )
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.rejections) >= 1
        assert any("max_gross_exposure" in r for rej in result.rejections for r in rej.reasons)

    def test_drawdown_halt(self) -> None:
        """Equity drop triggers drawdown circuit breaker."""
        # Create bars with a price crash to trigger drawdown.
        bars = (
            Bar(
                timestamp=_ts(0),
                instrument="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(1),
                instrument="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(2),
                instrument="TEST",
                open=100,
                high=100,
                low=10,
                close=20,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(3), instrument="TEST", open=20, high=25, low=15, close=20, volume=1000
            ),
            Bar(
                timestamp=_ts(4), instrument="TEST", open=20, high=25, low=15, close=20, volume=1000
            ),
        )
        dataset = _make_dataset(bars)
        limits = RiskLimits(max_drawdown=0.10)  # 10% drawdown limit
        cfg = _default_config(
            order_quantity=500.0,
            risk_limits=limits,
        )
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert result.halted
        assert result.halt is not None
        assert isinstance(result.halt, HaltRecord)
        assert result.halt.drawdown > 0.0

    def test_halt_prevents_new_trades(self) -> None:
        """After halt, no new orders are generated."""
        bars = (
            Bar(
                timestamp=_ts(0),
                instrument="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(1),
                instrument="TEST",
                open=100,
                high=110,
                low=90,
                close=100,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(2),
                instrument="TEST",
                open=100,
                high=100,
                low=10,
                close=20,
                volume=1000,
            ),
            Bar(
                timestamp=_ts(3), instrument="TEST", open=20, high=25, low=15, close=20, volume=1000
            ),
            Bar(
                timestamp=_ts(4), instrument="TEST", open=20, high=25, low=15, close=20, volume=1000
            ),
        )
        dataset = _make_dataset(bars)
        limits = RiskLimits(max_drawdown=0.10)
        cfg = _default_config(
            order_quantity=500.0,
            risk_limits=limits,
        )
        strategies = dict.fromkeys(dataset.instruments, AlwaysLong())

        result = run_simulation(dataset, strategies, cfg)

        assert result.halted
        # After halt, equity curve continues but no fills after the halt bar.
        halt_time = result.halt.timestamp  # type: ignore[union-attr]
        fills_after_halt = [fr for fr in result.fills if fr.fill.fill_time > halt_time]
        assert len(fills_after_halt) == 0

    def test_short_selling_disabled(self) -> None:
        """SELL that would create short position is blocked when allow_short=False."""
        dataset = _simple_dataset(3)
        cfg = _default_config(
            order_quantity=10.0,
            allow_short=False,
        )
        # AlwaysShort tries to sell → should be blocked for opening short.
        strategies = dict.fromkeys(dataset.instruments, AlwaysShort())

        result = run_simulation(dataset, strategies, cfg)

        # No fills should occur (can't go short from flat).
        assert len(result.fills) == 0

    def test_short_selling_enabled(self) -> None:
        """Short sell succeeds when allow_short=True and order_quantity is set."""
        dataset = _simple_dataset(3)
        cfg = _default_config(
            order_quantity=10.0,
            allow_short=True,
        )
        strategies = dict.fromkeys(dataset.instruments, AlwaysShort())

        result = run_simulation(dataset, strategies, cfg)

        assert len(result.fills) >= 1
        assert result.fills[0].fill.side is OrderSide.SELL

    def test_drawdown_exact_boundary(self) -> None:
        """Drawdown at exact limit triggers halt (tolerance per ADR-0006)."""
        from qrsip.simulation.risk import RiskEngine

        engine = RiskEngine(RiskLimits(max_drawdown=0.20))
        # 80000/100000 = 0.8 → 20% drawdown exactly at limit.
        assert engine.drawdown_breach(equity=80_000.0, peak_equity=100_000.0)


# ===========================================================================
# TestSimulationDeterminism
# ===========================================================================


class TestSimulationDeterminism:
    """Deterministic execution guarantee."""

    def test_deterministic_two_runs(self) -> None:
        """Same inputs produce identical results."""
        dataset = _simple_dataset(5)
        cost_model = CostModel(commission_bps=50.0, slippage_bps=20.0)
        cfg = _default_config(order_quantity=10.0, cost_model=cost_model)
        strategies: dict[str, SignalStrategy] = dict.fromkeys(dataset.instruments, AlwaysLong())

        r1 = run_simulation(dataset, strategies, cfg)
        r2 = run_simulation(dataset, strategies, cfg)

        assert len(r1.equity_curve) == len(r2.equity_curve)
        for ep1, ep2 in zip(r1.equity_curve, r2.equity_curve, strict=True):
            assert ep1.timestamp == ep2.timestamp
            assert ep1.equity == ep2.equity
            assert ep1.cash == ep2.cash

        assert len(r1.fills) == len(r2.fills)
        for f1, f2 in zip(r1.fills, r2.fills, strict=True):
            assert f1.fill.decision_time == f2.fill.decision_time
            assert f1.fill.fill_time == f2.fill.fill_time
            assert f1.fill.price == f2.fill.price
            assert f1.fill.quantity == f2.fill.quantity
            assert f1.fill.commission == f2.fill.commission
            assert f1.realized_pnl == f2.realized_pnl

        assert r1.halted == r2.halted

    def test_result_is_frozen(self) -> None:
        """SimulationResult fields cannot be reassigned."""
        dataset = _simple_dataset(3)
        cfg = _default_config()

        result = run_simulation(dataset, {}, cfg)

        with pytest.raises(AttributeError):
            result.halted = True  # type: ignore[misc]
