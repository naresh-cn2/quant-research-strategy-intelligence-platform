"""QRSIP metrics (L3): performance measurement with explicit failure modes.

Design (spec §27 metric definitions, ADR-0006 numerical tolerance):

- Individual metric functions **raise** :class:`~qrsip.errors.MetricError`
  when the input cannot produce an honest value (zero volatility, no losing
  trades, empty series). They never return ``inf``/``nan`` — JSON artifacts
  cannot represent those, and silently-infinite ratios hide real failures.
- The bundle function :func:`compute_performance_metrics` returns ``None`` for
  ratios that are *undefined for an otherwise valid run* (zero vol, monotonic
  equity, no losses) so a complete backtest can still be persisted, with the
  undefinedness explicit in the record instead of invented.
- Annualization assumes ``periods_per_year`` periods of equal length; the
  caller declares it (252 for daily data) and tests state the value used.
- Floating-point comparisons in tests use documented tolerances (pytest.approx
  with rel=1e-9 unless stated otherwise).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence

from pydantic import BaseModel, Field

from qrsip.errors import MetricError

__all__ = [
    "PerformanceMetrics",
    "annualized_return",
    "annualized_volatility",
    "calmar_ratio",
    "compute_performance_metrics",
    "max_drawdown",
    "period_returns",
    "profit_factor",
    "sharpe_ratio",
    "sortino_ratio",
    "total_return",
    "win_rate",
]


def period_returns(equity: Sequence[float]) -> tuple[float, ...]:
    """Per-period simple returns from an equity curve; length ``n - 1``."""
    if len(equity) < 2:
        raise MetricError("equity curve needs at least 2 points", provided=len(equity))
    result: list[float] = []
    for index, (previous, current) in enumerate(itertools.pairwise(equity)):
        if previous <= 0.0:
            raise MetricError("equity must stay strictly positive", index=index, value=previous)
        result.append(current / previous - 1.0)
    return tuple(result)


def total_return(equity: Sequence[float]) -> float:
    """``equity[-1]/equity[0] - 1``. Requires a positive starting equity."""
    if len(equity) < 1:
        raise MetricError("equity curve is empty")
    if equity[0] <= 0.0:
        raise MetricError("starting equity must be positive", value=equity[0])
    return equity[-1] / equity[0] - 1.0


def annualized_return(equity: Sequence[float], *, periods_per_year: int = 252) -> float:
    """Compound the total growth to a yearly rate: ``(end/start)**(ppy/n) - 1``."""
    if periods_per_year < 1:
        raise MetricError("periods_per_year must be positive", value=periods_per_year)
    if len(equity) < 2:
        raise MetricError("equity curve needs at least 2 points", provided=len(equity))
    if equity[0] <= 0.0 or equity[-1] <= 0.0:
        raise MetricError(
            "equity must be strictly positive to annualize",
            start=equity[0],
            end=equity[-1],
        )
    periods = len(equity) - 1
    growth = equity[-1] / equity[0]
    return float(growth ** (periods_per_year / periods)) - 1.0


def annualized_volatility(returns: Sequence[float], *, periods_per_year: int = 252) -> float:
    """Sample stdev (ddof=1) of returns, scaled by ``sqrt(periods_per_year)``."""
    if periods_per_year < 1:
        raise MetricError("periods_per_year must be positive", value=periods_per_year)
    if len(returns) < 2:
        raise MetricError("volatility needs at least 2 returns", provided=len(returns))
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(float(periods_per_year))


def sharpe_ratio(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sharpe: ``(mean(r) - rf/ppy) / stdev(r) * sqrt(ppy)``.

    Raises when volatility is zero — a zero-vol Sharpe is undefined, and
    returning ``inf`` would poison JSON artifacts and hide the degeneracy.
    """
    if len(returns) < 2:
        raise MetricError("Sharpe needs at least 2 returns", provided=len(returns))
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        raise MetricError("Sharpe undefined for zero-volatility returns")
    excess = mean - risk_free_rate / float(periods_per_year)
    return excess / std * math.sqrt(float(periods_per_year))


def sortino_ratio(
    returns: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sortino using downside deviation below the per-period target."""
    if len(returns) < 2:
        raise MetricError("Sortino needs at least 2 returns", provided=len(returns))
    target = risk_free_rate / float(periods_per_year)
    downside = [min(r - target, 0.0) ** 2 for r in returns]
    downside_dev = math.sqrt(sum(downside) / len(returns))
    if downside_dev == 0.0:
        raise MetricError("Sortino undefined: no returns below the target")
    excess = sum(returns) / len(returns) - target
    return excess / downside_dev * math.sqrt(float(periods_per_year))


def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a non-positive fraction (``0.0`` if none)."""
    if len(equity) < 1:
        raise MetricError("equity curve is empty")
    worst = 0.0
    peak = equity[0]
    for value in equity:
        if value > peak:
            peak = value
        if peak > 0.0:
            drawdown = value / peak - 1.0
            if drawdown < worst:
                worst = drawdown
    return worst


def calmar_ratio(annualized: float, drawdown: float) -> float:
    """``annualized_return / |max_drawdown|``; raises without a negative drawdown."""
    if drawdown >= 0.0:
        raise MetricError("Calmar undefined without a negative drawdown", drawdown=drawdown)
    return annualized / abs(drawdown)


def win_rate(trade_pnls: Sequence[float]) -> float:
    """Fraction of trades with positive realized PnL. Raises when empty."""
    if not trade_pnls:
        raise MetricError("win rate needs at least one closed trade")
    wins = sum(1 for pnl in trade_pnls if pnl > 0.0)
    return wins / len(trade_pnls)


def profit_factor(trade_pnls: Sequence[float]) -> float:
    """Gross profits / gross losses. Raises when there are no losing trades."""
    if not trade_pnls:
        raise MetricError("profit factor needs at least one closed trade")
    gross_profit = sum(pnl for pnl in trade_pnls if pnl > 0.0)
    gross_loss = -sum(pnl for pnl in trade_pnls if pnl < 0.0)
    if gross_loss == 0.0:
        raise MetricError("profit factor undefined: no losing trades")
    return gross_profit / gross_loss


class PerformanceMetrics(BaseModel):
    """Complete, JSON-serializable performance summary of one backtest.

    ``None`` means *undefined for this input* (zero vol, monotonic equity, no
    closed trades) — never an invented number. Everything else is exact.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    periods_per_year: int = Field(..., ge=1)
    start_equity: float
    end_equity: float
    n_periods: int = Field(..., ge=1)
    n_closed_trades: int = Field(..., ge=0)
    total_return: float
    annualized_return: float
    volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float  # non-positive fraction
    calmar: float | None
    win_rate: float | None
    profit_factor: float | None


def compute_performance_metrics(
    equity: Sequence[float],
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    trade_pnls: Sequence[float] = (),
) -> PerformanceMetrics:
    """Summarize an equity curve (and optional closed-trade PnLs).

    Raises :class:`MetricError` only when *no* honest summary exists (empty or
    single-point curve, non-positive equity). Ratios that are undefined for an
    otherwise valid run become ``None`` so the run can still be persisted with
    the undefinedness explicit (see module docstring).
    """
    if len(equity) < 2:
        raise MetricError(
            "performance summary needs at least 2 equity points", provided=len(equity)
        )
    if equity[0] <= 0.0:
        raise MetricError("starting equity must be positive", value=equity[0])

    returns = period_returns(equity)
    total = total_return(equity)
    annualized = annualized_return(equity, periods_per_year=periods_per_year)

    def _optional(fn: Callable[[], float]) -> float | None:
        # Run a ratio computation; None (undefined) instead of raising.
        try:
            return fn()
        except MetricError:
            return None

    volatility = _optional(
        lambda: annualized_volatility(returns, periods_per_year=periods_per_year)
    )

    sharpe = _optional(
        lambda: sharpe_ratio(
            returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year
        )
    )
    sortino = _optional(
        lambda: sortino_ratio(
            returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year
        )
    )

    drawdown = max_drawdown(equity)
    calmar = calmar_ratio(annualized, drawdown) if drawdown < 0.0 else None

    if trade_pnls:
        win = _optional(lambda: win_rate(trade_pnls))
        factor = _optional(lambda: profit_factor(trade_pnls))
    else:
        win = None
        factor = None

    return PerformanceMetrics(
        periods_per_year=periods_per_year,
        start_equity=equity[0],
        end_equity=equity[-1],
        n_periods=len(equity) - 1,
        n_closed_trades=len(trade_pnls),
        total_return=total,
        annualized_return=annualized,
        volatility=volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=drawdown,
        calmar=calmar,
        win_rate=win,
        profit_factor=factor,
    )
