"""QRSIP promotion gates + research report + validation result entities."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from qrsip.domain.base import BaseEntity

__all__ = ["PromotionDecision", "ResearchReport", "ValidationResult"]


class ValidationResult(BaseEntity):
    """One validation check outcome (spec 23). Fail-closed evidence."""

    experiment_id: str = Field(..., min_length=1)
    check: str = Field(..., min_length=1)
    expected: str = Field(default="")
    observed: str = Field(default="")
    status: str = Field(default="PENDING")
    evidence: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class PromotionDecision(BaseEntity):
    """FR-016 promotion gate decision. Human approval mandatory."""

    experiment_id: str = Field(..., min_length=1)
    decision: str = Field(default="PENDING")
    gates: dict[str, str] = Field(default_factory=dict)
    decided_by: str = Field(default="")
    rationale: str = Field(default="")


class ResearchReport(BaseEntity):
    """FR-015 research report envelope (spec 27-28)."""

    experiment_id: str = Field(..., min_length=1)
    observed: list[str] = Field(default_factory=list)
    inference: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    human_decision: str = Field(default="")
