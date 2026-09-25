"""Parameter sensitivity and walk-forward robustness evidence."""

from __future__ import annotations

import math
from datetime import datetime
from statistics import fmean, pstdev

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qrsip.errors import QRSIPError

__all__ = [
    "ParameterPoint",
    "SensitivityResult",
    "WalkForwardFold",
    "WalkForwardResult",
    "analyze_parameter_sensitivity",
    "walk_forward_validation",
]


class ParameterPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    parameter: str = Field(..., min_length=1)
    value: float
    score: float


class SensitivityResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    parameter: str = Field(..., min_length=1)
    point_count: int = Field(ge=2)
    best_value: float
    worst_value: float
    best_score: float
    worst_score: float
    mean_score: float
    score_stddev: float = Field(ge=0.0)
    negative_fraction: float = Field(ge=0.0, le=1.0)
    points: tuple[ParameterPoint, ...]


class WalkForwardFold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    fold: int = Field(ge=1)
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    score: float

    @field_validator("train_start", "train_end", "validation_start", "validation_end")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("walk-forward timestamps must be timezone-aware")
        return value


class WalkForwardResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    fold_count: int = Field(ge=1)
    mean_score: float
    stddev_score: float = Field(ge=0.0)
    folds: tuple[WalkForwardFold, ...]


def analyze_parameter_sensitivity(
    points: tuple[ParameterPoint, ...], *, negative_threshold: float = 0.0
) -> SensitivityResult:
    """Describe deterministic score variation without selecting a recommended parameter."""
    if len(points) < 2:
        raise QRSIPError("sensitivity analysis requires at least two observations")
    parameters = {point.parameter for point in points}
    if len(parameters) != 1:
        raise QRSIPError(
            "sensitivity observations must vary one parameter", parameters=sorted(parameters)
        )
    if len({point.value for point in points}) < 2:
        raise QRSIPError("sensitivity observations require at least two distinct values")
    if not math.isfinite(negative_threshold):
        raise QRSIPError("negative_threshold must be finite")
    ordered = tuple(sorted(points, key=lambda point: (point.parameter, point.value)))
    scores = [point.score for point in ordered]
    best = max(ordered, key=lambda point: (point.score, point.value))
    worst = min(ordered, key=lambda point: (point.score, point.value))
    return SensitivityResult(
        parameter=next(iter(parameters)),
        point_count=len(ordered),
        best_value=best.value,
        worst_value=worst.value,
        best_score=best.score,
        worst_score=worst.score,
        mean_score=fmean(scores),
        score_stddev=pstdev(scores) if len(scores) > 1 else 0.0,
        negative_fraction=sum(score <= negative_threshold for score in scores) / len(scores),
        points=ordered,
    )


def walk_forward_validation(folds: tuple[WalkForwardFold, ...]) -> WalkForwardResult:
    """Validate ordered, non-overlapping train/validation windows and summarize scores."""
    if not folds:
        raise QRSIPError("walk-forward validation requires at least one fold")
    ordered = tuple(sorted(folds, key=lambda fold: (fold.validation_start, fold.fold)))
    if [fold.fold for fold in ordered] != list(range(1, len(ordered) + 1)):
        raise QRSIPError("walk-forward folds must be numbered consecutively from one")
    previous_validation_end: datetime | None = None
    for fold in ordered:
        if not fold.train_start <= fold.train_end < fold.validation_start <= fold.validation_end:
            raise QRSIPError(
                "walk-forward fold windows must be ordered and non-overlapping", fold=fold.fold
            )
        if previous_validation_end is not None and fold.validation_start <= previous_validation_end:
            raise QRSIPError("walk-forward validation windows overlap", fold=fold.fold)
        previous_validation_end = fold.validation_end
    scores = [fold.score for fold in ordered]
    return WalkForwardResult(
        fold_count=len(ordered),
        mean_score=fmean(scores),
        stddev_score=pstdev(scores) if len(scores) > 1 else 0.0,
        folds=ordered,
    )
