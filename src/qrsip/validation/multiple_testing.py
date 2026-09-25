"""Deterministic multiple-testing correction for research hypotheses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from qrsip.errors import QRSIPError

__all__ = ["CorrectedTest", "holm_bonferroni"]


class CorrectedTest(BaseModel):
    """One named hypothesis with its original and corrected two-sided p-value."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    name: str = Field(..., min_length=1)
    raw_p_value: float = Field(ge=0.0, le=1.0)
    adjusted_p_value: float = Field(ge=0.0, le=1.0)
    rejected_at_alpha: bool


def holm_bonferroni(
    p_values: dict[str, float], *, alpha: float = 0.05
) -> tuple[CorrectedTest, ...]:
    """Apply Holm's step-down correction with deterministic name tie-breaking."""
    if not p_values:
        raise QRSIPError("multiple-testing correction requires at least one p-value")
    if not 0.0 < alpha < 1.0:
        raise QRSIPError("alpha must be strictly between zero and one", value=alpha)
    for name, value in p_values.items():
        if not name:
            raise QRSIPError("test name must be non-empty")
        if not isinstance(value, float) or value != value or value < 0.0 or value > 1.0:
            raise QRSIPError("p-value must be finite and between zero and one", name=name)
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    total = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for index, (name, value) in enumerate(ordered):
        candidate = min(1.0, (total - index) * value)
        running = max(running, candidate)
        adjusted[name] = running
    return tuple(
        CorrectedTest(
            name=name,
            raw_p_value=p_values[name],
            adjusted_p_value=adjusted[name],
            rejected_at_alpha=adjusted[name] <= alpha,
        )
        for name in sorted(p_values)
    )
