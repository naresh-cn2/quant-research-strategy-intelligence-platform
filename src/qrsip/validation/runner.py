"""Fail-closed orchestration for deterministic L5 validation evidence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qrsip.data.dataset import MarketDataset
from qrsip.errors import QRSIPError
from qrsip.simulation.engine import SimulationResult
from qrsip.validation.bias import (
    SurvivorshipUniverseSnapshot,
    ValidationStatus,
    verify_look_ahead,
    verify_survivorship,
)
from qrsip.validation.multiple_testing import holm_bonferroni
from qrsip.validation.robustness import (
    ParameterPoint,
    WalkForwardFold,
    analyze_parameter_sensitivity,
    walk_forward_validation,
)
from qrsip.validation.stats import deflated_sharpe_ratio, p_value_two_sided, t_statistic

__all__ = ["ValidationCheck", "ValidationPolicy", "ValidationRunner", "ValidationSummary"]


class ValidationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    significance_level: float = Field(default=0.05, gt=0.0, lt=1.0)
    trials: int = Field(default=1, ge=1)
    periods_per_year: int = Field(default=252, ge=1)
    require_survivorship: bool = False
    require_sensitivity: bool = False
    require_walk_forward: bool = False


class ValidationCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    name: str = Field(..., min_length=1)
    status: ValidationStatus
    expected: str = Field(..., min_length=1)
    observed: str = Field(..., min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()


class ValidationSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    experiment_id: str = Field(..., min_length=1)
    dataset_checksum: str = Field(..., min_length=64)
    checks: tuple[ValidationCheck, ...]

    @property
    def overall_status(self) -> ValidationStatus:
        if self.checks and all(item.status is ValidationStatus.PASS for item in self.checks):
            return ValidationStatus.PASS
        return ValidationStatus.FAIL

    def check(self, name: str) -> ValidationCheck:
        for item in self.checks:
            if item.name == name:
                return item
        raise QRSIPError("validation check not found", name=name)


class ValidationRunner:
    def __init__(self, policy: ValidationPolicy | None = None) -> None:
        self.policy = policy or ValidationPolicy()

    def run(
        self,
        *,
        experiment_id: str,
        result: SimulationResult,
        dataset: MarketDataset,
        returns: Sequence[float],
        observed_sharpe: float,
        p_values: dict[str, float] | None = None,
        snapshots: tuple[SurvivorshipUniverseSnapshot, ...] = (),
        sensitivity_points: tuple[ParameterPoint, ...] = (),
        walk_forward_folds: tuple[WalkForwardFold, ...] = (),
    ) -> ValidationSummary:
        if not experiment_id:
            raise QRSIPError("experiment_id is required for validation")
        if not returns:
            raise QRSIPError("validation requires at least one return observation")
        checks: tuple[ValidationCheck, ...] = (
            self._significance(returns, observed_sharpe),
            self._look_ahead(result, dataset),
            self._survivorship(dataset, snapshots),
            self._sensitivity(sensitivity_points),
            self._walk_forward(walk_forward_folds),
        )
        if p_values:
            corrected = holm_bonferroni(p_values, alpha=self.policy.significance_level)
            checks += (
                ValidationCheck(
                    name="multiple_testing",
                    status=ValidationStatus.PASS,
                    expected="all hypotheses receive deterministic Holm adjustment",
                    observed=f"{len(corrected)} hypotheses corrected",
                    evidence={"tests": [item.model_dump(mode="json") for item in corrected]},
                    limitations=("statistical rejection is not a promotion decision",),
                ),
            )
        return ValidationSummary(
            experiment_id=experiment_id,
            dataset_checksum=result.dataset_checksum,
            checks=checks,
        )

    def _significance(self, returns: Sequence[float], observed_sharpe: float) -> ValidationCheck:
        try:
            statistic = t_statistic(returns)
            p_value = p_value_two_sided(statistic)
            dsr = deflated_sharpe_ratio(
                observed_sharpe,
                trials=self.policy.trials,
                returns=returns,
                periods_per_year=self.policy.periods_per_year,
            )
        except QRSIPError as exc:
            return ValidationCheck(
                name="significance",
                status=ValidationStatus.FAIL,
                expected="finite significance and deflated-Sharpe evidence",
                observed=exc.message,
                evidence={"error_context": exc.context},
            )
        status = (
            ValidationStatus.PASS
            if p_value <= self.policy.significance_level and dsr >= self.policy.significance_level
            else ValidationStatus.FAIL
        )
        return ValidationCheck(
            name="significance",
            status=status,
            expected=f"p <= {self.policy.significance_level:g}; DSR >= {self.policy.significance_level:g}",
            observed=f"p={p_value:.12g}; DSR={dsr:.12g}",
            evidence={
                "t_statistic": statistic,
                "p_value": p_value,
                "deflated_sharpe_ratio": dsr,
                "trials": self.policy.trials,
            },
            limitations=("p-value uses the documented normal-tail approximation",),
        )

    def _look_ahead(self, result: SimulationResult, dataset: MarketDataset) -> ValidationCheck:
        evidence = verify_look_ahead(result, dataset)
        return ValidationCheck(
            name="look_ahead",
            status=evidence.status,
            expected="every fill occurs after its decision and has a recorded price bar",
            observed=evidence.observed,
            evidence=evidence.model_dump(mode="json"),
            limitations=evidence.limitations,
        )

    def _survivorship(
        self, dataset: MarketDataset, snapshots: tuple[SurvivorshipUniverseSnapshot, ...]
    ) -> ValidationCheck:
        evidence = verify_survivorship(dataset, snapshots)
        status = evidence.status
        limitations = evidence.limitations
        if self.policy.require_survivorship and status is ValidationStatus.NOT_VERIFIABLE:
            status = ValidationStatus.FAIL
            limitations += ("survivorship evidence is required by this policy",)
        return ValidationCheck(
            name="survivorship",
            status=status,
            expected="all point-in-time eligible instruments are present",
            observed=evidence.observed,
            evidence=evidence.model_dump(mode="json"),
            limitations=limitations,
        )

    def _sensitivity(self, points: tuple[ParameterPoint, ...]) -> ValidationCheck:
        if not points:
            status = (
                ValidationStatus.FAIL
                if self.policy.require_sensitivity
                else ValidationStatus.NOT_VERIFIABLE
            )
            limitations = ["missing robustness evidence is not a pass"]
            if self.policy.require_sensitivity:
                limitations.append("parameter sensitivity is required by this policy")
            return ValidationCheck(
                name="parameter_sensitivity",
                status=status,
                expected="at least two parameter variants",
                observed="no sensitivity observations supplied",
                limitations=tuple(limitations),
            )
        result = analyze_parameter_sensitivity(points)
        return ValidationCheck(
            name="parameter_sensitivity",
            status=ValidationStatus.PASS,
            expected="parameter variants are explicitly observed",
            observed=f"{result.point_count} variants; mean score={result.mean_score:.12g}",
            evidence=result.model_dump(mode="json"),
        )

    def _walk_forward(self, folds: tuple[WalkForwardFold, ...]) -> ValidationCheck:
        if not folds:
            status = (
                ValidationStatus.FAIL
                if self.policy.require_walk_forward
                else ValidationStatus.NOT_VERIFIABLE
            )
            limitations = ["missing robustness evidence is not a pass"]
            if self.policy.require_walk_forward:
                limitations.append("walk-forward validation is required by this policy")
            return ValidationCheck(
                name="walk_forward",
                status=status,
                expected="ordered non-overlapping train and validation windows",
                observed="no walk-forward folds supplied",
                limitations=tuple(limitations),
            )
        result = walk_forward_validation(folds)
        return ValidationCheck(
            name="walk_forward",
            status=ValidationStatus.PASS,
            expected="ordered non-overlapping train and validation windows",
            observed=f"{result.fold_count} folds; mean score={result.mean_score:.12g}",
            evidence=result.model_dump(mode="json"),
        )
