"""
Tests for qrsip.quant — causal features, deterministic signals, and fail-closed
metrics (spec §16, §17, §27, ADR-0005, ADR-0006).
"""

from __future__ import annotations

import math

import pytest

from qrsip.errors import MetricError, QRSIPError
from qrsip.quant import (
    ConstantStrategy,
    MovingAverageCrossStrategy,
    PerformanceMetrics,
    Signal,
    SignalStrategy,
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    compute_performance_metrics,
    ema,
    log_returns,
    max_drawdown,
    momentum,
    period_returns,
    profit_factor,
    rolling_volatility,
    sharpe_ratio,
    simple_returns,
    sma,
    sortino_ratio,
    total_return,
    win_rate,
)

UPS = tuple(100.0 + i for i in range(10))  # strictly increasing closes
DOWN = tuple(200.0 - i for i in range(10))  # strictly decreasing closes


class TestSMA:
    def test_warmup_is_none_not_number(self) -> None:
        out = sma(UPS, 4)
        assert out[:3] == (None, None, None)
        assert out[3] == pytest.approx(101.5)  # (100+101+102+103)/4

    def test_aligned_length(self) -> None:
        assert len(sma(UPS, 3)) == len(UPS)

    def test_causal_prefix_property(self) -> None:
        full = sma(UPS, 3)
        prefix = sma(UPS[:6], 3)
        assert full[:6] == prefix

    @pytest.mark.parametrize("window", [0, -3])
    def test_invalid_window_fails_closed(self, window: int) -> None:
        with pytest.raises(QRSIPError, match="positive integer"):
            sma(UPS, window)

    def test_bool_window_rejected(self) -> None:
        with pytest.raises(QRSIPError, match="positive integer"):
            sma(UPS, True)  # type: ignore[arg-type]


class TestEMA:
    def test_seeded_with_first_value(self) -> None:
        assert ema(UPS, 5)[0] == 100.0

    def test_ema_tracks_upward_trend(self) -> None:
        out = ema(UPS, 3)
        assert out[-1] > out[1]  # type: ignore[operator]

    def test_empty_fails_closed(self) -> None:
        with pytest.raises(MetricError, match="not enough values"):
            ema((), 3)

    def test_invalid_span_fails_closed(self) -> None:
        with pytest.raises(QRSIPError, match="positive integer"):
            ema(UPS, 0)


class TestReturns:
    def test_simple_returns_length_and_value(self) -> None:
        out = simple_returns([100.0, 110.0, 99.0])
        assert len(out) == 2
        assert out[0] == pytest.approx(0.10)
        assert out[1] == pytest.approx(-0.10)

    def test_simple_returns_zero_price_fails(self) -> None:
        with pytest.raises(MetricError, match="zero price"):
            simple_returns([0.0, 1.0])

    def test_simple_returns_short_input_fails(self) -> None:
        with pytest.raises(MetricError, match="not enough values"):
            simple_returns([100.0])

    def test_log_returns_match_natural_log(self) -> None:
        out = log_returns([100.0, 105.0])
        assert out[0] == pytest.approx(math.log(1.05), rel=1e-12)

    @pytest.mark.parametrize("series", [[-1.0, 1.0], [1.0, 0.0]])
    def test_log_returns_require_positive_prices(self, series: list[float]) -> None:
        with pytest.raises(MetricError, match="positive prices"):
            log_returns(series)


class TestRollingVolatilityAndMomentum:
    def test_warmup_is_none(self) -> None:
        out = rolling_volatility(UPS, 4)
        assert out[:4] == (None, None, None, None)
        assert out[4] is not None

    def test_zero_variance_window_is_zero_not_error(self) -> None:
        flat = tuple(100.0 for _ in range(10))
        out = rolling_volatility(flat, 4)
        assert out[4] == 0.0  # an honest fact, not an undefined ratio

    def test_annualization_scales_with_ppy(self) -> None:
        base = rolling_volatility(UPS, 4, periods_per_year=1)[4]
        scaled = rolling_volatility(UPS, 4, periods_per_year=4)[4]
        assert scaled == pytest.approx(base * 2.0, rel=1e-12)  # sqrt(4)=2

    def test_invalid_ppy_fails(self) -> None:
        with pytest.raises(QRSIPError, match="positive"):
            rolling_volatility(UPS, 4, periods_per_year=0)

    def test_momentum_value(self) -> None:
        out = momentum(UPS, 3)
        assert out[3] == pytest.approx(103.0 / 100.0 - 1.0)
        assert out[:3] == (None, None, None)

    def test_momentum_zero_base_fails(self) -> None:
        with pytest.raises(MetricError, match="zero price"):
            momentum([0.0, 1.0, 2.0], 1)


class TestSignals:
    def test_signal_protocol_conformance(self) -> None:
        assert isinstance(ConstantStrategy(Signal.LONG), SignalStrategy)
        assert isinstance(MovingAverageCrossStrategy(), SignalStrategy)

    def test_constant_strategy_is_constant(self) -> None:
        strategy = ConstantStrategy(Signal.LONG)
        assert strategy.target_signal(UPS) is Signal.LONG
        assert strategy.target_signal(()) is Signal.LONG

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"fast": 0, "slow": 10}, "positive integer"),
            ({"fast": 10, "slow": 5}, "slow window must exceed"),
            ({"fast": 5.5, "slow": 10}, "positive integer"),
        ],
    )
    def test_invalid_cross_parameters_fail_closed(
        self, kwargs: dict[str, object], match: str
    ) -> None:
        with pytest.raises(QRSIPError, match=match):
            MovingAverageCrossStrategy(**kwargs)  # type: ignore[arg-type]

    def test_insufficient_history_is_flat(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5)
        assert strategy.target_signal(UPS[:4]) is Signal.FLAT

    def test_uptrend_goes_long(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5)
        assert strategy.target_signal(UPS) is Signal.LONG

    def test_downtrend_flat_when_short_disallowed(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5, allow_short=False)
        assert strategy.target_signal(DOWN) is Signal.FLAT

    def test_downtrend_short_when_allowed(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5, allow_short=True)
        assert strategy.target_signal(DOWN) is Signal.SHORT

    def test_flat_series_ties_are_flat(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5, allow_short=True)
        constant = tuple(100.0 for _ in range(10))
        assert strategy.target_signal(constant) is Signal.FLAT

    def test_signal_depends_only_on_prefix(self) -> None:
        strategy = MovingAverageCrossStrategy(fast=2, slow=5)
        shared = list(UPS[:6])
        suffix_a = list(UPS[6:])
        suffix_b = [1000.0, 1.0, 500.0, 2.0, 999.0, 3.0]
        assert strategy.target_signal(shared + suffix_a) == strategy.target_signal(
            shared + suffix_b
        )


class TestRatioMetrics:
    def test_period_returns_from_equity(self) -> None:
        out = period_returns([100.0, 110.0, 99.0])
        assert len(out) == 2
        assert out[0] == pytest.approx(0.10, rel=1e-12)
        assert out[1] == pytest.approx(-0.10, rel=1e-12)

    def test_period_returns_short_curve_fails(self) -> None:
        with pytest.raises(MetricError, match="at least 2"):
            period_returns([100.0])

    def test_total_return(self) -> None:
        assert total_return([100.0, 110.0]) == pytest.approx(0.10, rel=1e-12)

    def test_total_return_empty_fails(self) -> None:
        with pytest.raises(MetricError, match="empty"):
            total_return([])

    def test_total_return_nonpositive_start_fails(self) -> None:
        with pytest.raises(MetricError, match="positive"):
            total_return([0.0, 1.0])

    def test_annualized_return_four_periods(self) -> None:
        # 100 -> 121 over 4 periods with ppy=4 compounds to exactly +21%/yr.
        equity = [100.0, 105.0, 110.0, 115.0, 121.0]
        assert annualized_return(equity, periods_per_year=4) == pytest.approx(0.21, rel=1e-12)

    def test_annualized_return_invalid_inputs(self) -> None:
        with pytest.raises(MetricError, match="at least 2"):
            annualized_return([100.0])
        with pytest.raises(MetricError, match="periods_per_year"):
            annualized_return([100.0, 101.0], periods_per_year=0)
        with pytest.raises(MetricError, match="positive"):
            annualized_return([-1.0, 1.0])

    def test_annualized_volatility_known_value(self) -> None:
        returns = simple_returns([100.0, 101.0, 100.0, 102.0])
        vol = annualized_volatility(returns, periods_per_year=1)
        mean = sum(returns) / len(returns)
        expected = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
        assert vol == pytest.approx(expected, rel=1e-12)

    def test_volatility_short_input_fails(self) -> None:
        with pytest.raises(MetricError, match="at least 2"):
            annualized_volatility([0.01])

    def test_sharpe_known_value(self) -> None:
        returns = [0.01, 0.02, 0.03]  # mean 0.02, sample stdev 0.01
        value = sharpe_ratio(returns, periods_per_year=252)
        assert value == pytest.approx(0.02 / 0.01 * math.sqrt(252), rel=1e-9)

    def test_sharpe_zero_vol_fails_closed(self) -> None:
        with pytest.raises(MetricError, match="zero-volatility"):
            sharpe_ratio([0.01, 0.01, 0.01])

    def test_sharpe_short_input_fails(self) -> None:
        with pytest.raises(MetricError, match="at least 2"):
            sharpe_ratio([0.01])

    def test_sortino_known_value(self) -> None:
        # mean = (0.05-0.01-0.02)/3 = 0.0066667
        # downside dev = sqrt((0.01^2 + 0.02^2)/3) = sqrt(0.0005/3) = 0.01290994
        # sortino = 0.0066667 / 0.01290994 * sqrt(252) = 8.19756061276768
        value = sortino_ratio([0.05, -0.01, -0.02], periods_per_year=252)
        assert value == pytest.approx(8.19756061276768, rel=1e-12)

    def test_sortino_no_downside_fails_closed(self) -> None:
        with pytest.raises(MetricError, match="no returns below"):
            sortino_ratio([0.01, 0.02, 0.03])

    def test_max_drawdown_known_value(self) -> None:
        assert max_drawdown([100.0, 120.0, 90.0, 130.0]) == pytest.approx(-0.25, rel=1e-12)

    def test_max_drawdown_monotonic_is_zero(self) -> None:
        assert max_drawdown([1.0, 2.0, 3.0]) == 0.0

    def test_max_drawdown_empty_fails(self) -> None:
        with pytest.raises(MetricError, match="empty"):
            max_drawdown([])

    def test_calmar_known_value(self) -> None:
        # calmar = annualized / |max_drawdown| → positive return, negative
        # drawdown yields a positive ratio (and vice versa).
        assert calmar_ratio(0.10, -0.20) == pytest.approx(0.5, rel=1e-12)
        assert calmar_ratio(-0.10, -0.20) == pytest.approx(-0.5, rel=1e-12)

    def test_calmar_without_drawdown_fails(self) -> None:
        with pytest.raises(MetricError, match="negative drawdown"):
            calmar_ratio(0.1, 0.0)

    def test_win_rate(self) -> None:
        assert win_rate([1.0, -2.0, 3.0, -4.0, 5.0]) == pytest.approx(0.6, rel=1e-12)

    def test_win_rate_empty_fails(self) -> None:
        with pytest.raises(MetricError, match="at least one"):
            win_rate([])

    def test_profit_factor(self) -> None:
        assert profit_factor([2.0, -1.0]) == pytest.approx(2.0, rel=1e-12)


class TestPerformanceBundle:
    def test_bundle_known_curve(self) -> None:
        equity = [100.0, 110.0, 99.0, 121.0]
        bundle = compute_performance_metrics(equity, periods_per_year=252, trade_pnls=[5.0, -2.0])
        assert isinstance(bundle, PerformanceMetrics)
        assert bundle.start_equity == 100.0
        assert bundle.end_equity == 121.0
        assert bundle.n_periods == 3
        assert bundle.n_closed_trades == 2
        assert bundle.total_return == pytest.approx(0.21, rel=1e-12)
        # peak 110 → trough 99
        assert bundle.max_drawdown == pytest.approx(99.0 / 110.0 - 1.0, rel=1e-12)
        assert bundle.win_rate == pytest.approx(0.5, rel=1e-12)
        assert bundle.sharpe is not None
        assert bundle.volatility is not None

    def test_undefined_ratios_become_none_not_nan(self) -> None:
        # strictly rising equity: no drawdown, no trades → explicit None
        bundle = compute_performance_metrics([100.0, 101.0, 102.0, 103.0], periods_per_year=4)
        assert bundle.max_drawdown == 0.0
        assert bundle.calmar is None
        assert bundle.win_rate is None
        assert bundle.profit_factor is None

    def test_flat_equity_yields_none_ratios(self) -> None:
        # zero volatility → sharpe/sortino undefined → None, never inf/nan
        bundle = compute_performance_metrics([100.0] * 4, periods_per_year=252)
        assert bundle.total_return == 0.0
        assert bundle.volatility == 0.0
        assert bundle.sharpe is None
        assert bundle.sortino is None
        assert bundle.calmar is None

    @pytest.mark.parametrize(
        ("equity", "match"),
        [
            ([], "at least 2"),
            ([100.0], "at least 2"),
            ([-100.0, 90.0], "positive"),
        ],
    )
    def test_bundle_fails_closed_on_bad_input(self, equity: list[float], match: str) -> None:
        with pytest.raises(MetricError, match=match):
            compute_performance_metrics(equity)

    def test_higher_risk_free_rate_lowers_sharpe(self) -> None:
        equity = [100.0, 104.0, 98.0, 106.0, 101.0]
        zero_rf = compute_performance_metrics(equity, periods_per_year=252, risk_free_rate=0.0)
        pos_rf = compute_performance_metrics(equity, periods_per_year=252, risk_free_rate=0.05)
        assert zero_rf.sharpe is not None and pos_rf.sharpe is not None
        assert pos_rf.sharpe < zero_rf.sharpe

    @pytest.mark.parametrize("pnls", [[], [1.0, 2.0]])
    def test_profit_factor_undefined_cases_fail(self, pnls: list[float]) -> None:
        with pytest.raises(MetricError):
            profit_factor(pnls)
