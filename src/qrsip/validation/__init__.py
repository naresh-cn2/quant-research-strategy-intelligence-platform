"""QRSIP validation layer (L5): bias checks, robustness, and statistics.

- :mod:`qrsip.validation.stats` — significance math without SciPy, with every
  approximation declared (ADR-0006).

The layer exists to *disprove* results, not to decorate them: a validation gate
that cannot fail is not a gate.
"""

from __future__ import annotations

from qrsip.validation.stats import (
    deflated_sharpe_ratio,
    expected_max_standard_normal,
    normal_cdf,
    p_value_two_sided,
    sample_kurtosis_excess,
    sample_skewness,
    t_statistic,
)

__all__ = [
    "deflated_sharpe_ratio",
    "expected_max_standard_normal",
    "normal_cdf",
    "p_value_two_sided",
    "sample_kurtosis_excess",
    "sample_skewness",
    "t_statistic",
]
