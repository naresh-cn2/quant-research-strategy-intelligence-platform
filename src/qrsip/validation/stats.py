"""QRSIP validation statistics (L5): significance math without SciPy.

Declared approximations (ADR-0006 — tolerances must be explicit):

- P-values use the **normal approximation** ``p = 2·(1 - Φ(|t|))`` rather than
  the exact Student-t distribution. For the sample sizes this platform
  requires (tens to thousands of periods) the normal tail is within ~1e-2 of
  the t tail; tests state this bound. This avoids a SciPy dependency the
  project does not carry.
- Moment estimators are **population** (divide by ``n``), matching the
  Bailey-López de Prado deflated-Sharpe literature.
- Deflated Sharpe uses the asymptotic expected-maximum
  ``E[max] ≈ sigma·√(2·ln T)`` for ``T`` independent trials (T = 1 → 0), which is
  an approximation with known small-T bias; it is documented in
  :func:`deflated_sharpe_ratio` and asserted in tests.

Every function raises :class:`~qrsip.errors.MetricError` when the input cannot
produce an honest value. Nothing here invents numbers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from qrsip.errors import MetricError

__all__ = [
    "deflated_sharpe_ratio",
    "expected_max_standard_normal",
    "normal_cdf",
    "p_value_two_sided",
    "sample_kurtosis_excess",
    "sample_skewness",
    "t_statistic",
]


def normal_cdf(x: float) -> float:
    """Standard normal CDF via ``math.erf`` (exact to double precision)."""
    if not math.isfinite(x):
        raise MetricError("normal CDF argument must be finite", value=x)
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _moments(returns: Sequence[float], minimum: int) -> tuple[float, float, float, float]:
    n = len(returns)
    if n < minimum:
        raise MetricError("not enough observations", provided=n, required=minimum)
    mean = sum(returns) / n
    m2 = sum((r - mean) ** 2 for r in returns) / n
    if m2 <= 0.0:
        raise MetricError("moments undefined for a constant series")
    m3 = sum((r - mean) ** 3 for r in returns) / n
    m4 = sum((r - mean) ** 4 for r in returns) / n
    return mean, m2, m3, m4


def t_statistic(returns: Sequence[float], *, null_mean: float = 0.0) -> float:
    """One-sample t statistic of the mean: ``(x̄ - μ₀) / (s/√n)``, ``s`` ddof=1."""
    n = len(returns)
    if n < 2:
        raise MetricError("t statistic needs at least 2 observations", provided=n)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    if variance <= 0.0:
        raise MetricError("t statistic undefined for zero variance")
    return (mean - null_mean) / math.sqrt(variance / n)


def p_value_two_sided(t: float) -> float:
    """Two-sided p-value using the normal approximation (declared above)."""
    if not math.isfinite(t):
        raise MetricError("t statistic must be finite", value=t)
    return 2.0 * (1.0 - normal_cdf(abs(t)))


def sample_skewness(returns: Sequence[float]) -> float:
    """Population skewness ``μ₃/sigma³`` (Bailey-López de Prado convention)."""
    _, m2, m3, _ = _moments(returns, minimum=3)
    return float(m3 / (m2**1.5))


def sample_kurtosis_excess(returns: Sequence[float]) -> float:
    """Population **excess** kurtosis ``μ₄/sigma⁴ - 3`` (same convention)."""
    _, m2, _, m4 = _moments(returns, minimum=4)
    return m4 / (m2 * m2) - 3.0


def expected_max_standard_normal(trials: int) -> float:
    """Asymptotic expected maximum of ``trials`` iid standard normals.

    ``E[max] ≈ √(2·ln T)`` for ``T ≥ 2``; ``T = 1`` gives ``0.0``. This is an
    approximation with known small-``T`` bias (declared in the module docstring).
    """
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise MetricError("trials must be a positive integer", provided=trials)
    if trials == 1:
        return 0.0
    return math.sqrt(2.0 * math.log(trials))


def deflated_sharpe_ratio(
    observed_sharpe: float,
    *,
    trials: int,
    returns: Sequence[float],
    periods_per_year: int = 252,
) -> float:
    """Probability the *true* Sharpe exceeds the trial-adjusted benchmark.

    Implements Bailey-López de Prado's deflated Sharpe ratio:

    1. Convert the annualized ``observed_sharpe`` to per-period units.
    2. Estimate skew ``γ₃`` and excess kurtosis ``γ₄-3`` from ``returns``
       (population moments, ``n ≥ 4``).
    3. Benchmark ``SR0 = E[max over trials] · √Var[SR]``.
    4. ``DSR = Φ( (SR̂ - SR0)·√(n-1) / √(1 - γ₃·SR̂ + (γ₄-1)/4·SR̂²) )``.

    Returns a value in ``[0, 1]``. Raises :class:`MetricError` when the input
    cannot produce an honest value (too few observations, constant series, or
    a non-positive variance term).
    """
    if not math.isfinite(observed_sharpe):
        raise MetricError("observed_sharpe must be finite", value=observed_sharpe)
    if periods_per_year < 1:
        raise MetricError("periods_per_year must be positive", value=periods_per_year)

    n = len(returns)
    mean, m2, m3, m4 = _moments(returns, minimum=4)
    del mean  # moments helper returns the mean first; DSR is scale-free here
    gamma3 = m3 / (m2**1.5)
    gamma4 = m4 / (m2 * m2)

    sr_period = observed_sharpe / math.sqrt(float(periods_per_year))
    scale = 1.0 - gamma3 * sr_period + (gamma4 - 1.0) / 4.0 * sr_period**2
    if scale <= 0.0:
        raise MetricError(
            "deflated Sharpe variance term is non-positive",
            scale=scale,
            skew=gamma3,
            excess_kurtosis=gamma4 - 3.0,
        )
    variance_sr = scale / (n - 1)
    sr0_period = expected_max_standard_normal(trials) * math.sqrt(variance_sr)
    denominator = math.sqrt(scale)
    z = (sr_period - sr0_period) * math.sqrt(n - 1) / denominator
    return normal_cdf(z)
