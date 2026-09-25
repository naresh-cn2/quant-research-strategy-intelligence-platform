"""Immutable L5 validation and robustness evidence."""

from __future__ import annotations

from qrsip.validation.bias import (
    LookAheadEvidence,
    SurvivorshipEvidence,
    SurvivorshipUniverseSnapshot,
    ValidationStatus,
    verify_look_ahead,
    verify_survivorship,
)
from qrsip.validation.multiple_testing import CorrectedTest, holm_bonferroni
from qrsip.validation.robustness import (
    ParameterPoint,
    SensitivityResult,
    WalkForwardFold,
    WalkForwardResult,
    analyze_parameter_sensitivity,
    walk_forward_validation,
)
from qrsip.validation.runner import (
    ValidationCheck,
    ValidationPolicy,
    ValidationRunner,
    ValidationSummary,
)
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
    "CorrectedTest",
    "LookAheadEvidence",
    "ParameterPoint",
    "SensitivityResult",
    "SurvivorshipEvidence",
    "SurvivorshipUniverseSnapshot",
    "ValidationCheck",
    "ValidationPolicy",
    "ValidationRunner",
    "ValidationStatus",
    "ValidationSummary",
    "WalkForwardFold",
    "WalkForwardResult",
    "analyze_parameter_sensitivity",
    "deflated_sharpe_ratio",
    "expected_max_standard_normal",
    "holm_bonferroni",
    "normal_cdf",
    "p_value_two_sided",
    "sample_kurtosis_excess",
    "sample_skewness",
    "t_statistic",
    "verify_look_ahead",
    "verify_survivorship",
    "walk_forward_validation",
]
