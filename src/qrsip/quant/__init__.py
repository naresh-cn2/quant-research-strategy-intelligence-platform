"""QRSIP quant layer (L3): deterministic features, signals, and metrics (spec §16, §27).

- :mod:`qrsip.quant.features` — causal, pure feature computation over close
  histories (None during warm-up, never a fabricated number).
- :mod:`qrsip.quant.signals`  — strategy protocol + SMA crossover / constant
  signals; inputs are closes only (orders and fills belong to L4).
- :mod:`qrsip.quant.metrics`  — performance measurement that raises when a
  value cannot honestly be computed, with an explicit ``None`` convention for
  ratios undefined for an otherwise valid run.

This layer performs no I/O and never touches clocks, storage, or portfolios.
"""

from __future__ import annotations

from qrsip.quant.features import (
    ema,
    log_returns,
    momentum,
    rolling_volatility,
    simple_returns,
    sma,
)
from qrsip.quant.metrics import (
    PerformanceMetrics,
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    compute_performance_metrics,
    max_drawdown,
    period_returns,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    total_return,
    win_rate,
)
from qrsip.quant.signals import (
    ConstantStrategy,
    MovingAverageCrossStrategy,
    Signal,
    SignalStrategy,
)

__all__ = [
    "ConstantStrategy",
    "MovingAverageCrossStrategy",
    "PerformanceMetrics",
    "Signal",
    "SignalStrategy",
    "annualized_return",
    "annualized_volatility",
    "calmar_ratio",
    "compute_performance_metrics",
    "ema",
    "log_returns",
    "max_drawdown",
    "momentum",
    "period_returns",
    "profit_factor",
    "rolling_volatility",
    "sharpe_ratio",
    "simple_returns",
    "sma",
    "sortino_ratio",
    "total_return",
    "win_rate",
]
