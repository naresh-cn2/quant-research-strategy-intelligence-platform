"""QRSIP research entities: question, hypothesis, strategy, experiment (FR-001..FR-005)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from qrsip.domain.base import BaseEntity
from qrsip.domain.lifecycle import ResearchLifecycleState

__all__ = [
    "DatasetRef",
    "Experiment",
    "ExperimentRun",
    "Hypothesis",
    "ResearchQuestion",
    "StrategySpec",
]


class ResearchQuestion(BaseEntity):
    """FR-001 research question registry entry."""

    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    motivation: str = Field(default="")
    scope: str = Field(default="")
    universe: list[str] = Field(default_factory=list)
    horizon: str = Field(default="")
    owner: str = Field(default="")
    status: ResearchLifecycleState = Field(default=ResearchLifecycleState.DRAFT)


class Hypothesis(BaseEntity):
    """FR-002 hypothesis registry entry."""

    question_id: str = Field(..., min_length=1)
    null_hypothesis: str = Field(..., min_length=1)
    alternative_hypothesis: str = Field(..., min_length=1)
    expected_mechanism: str = Field(default="")
    measurable_prediction: str = Field(default="")
    invalidation_condition: str = Field(default="")
    required_data: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    status: ResearchLifecycleState = Field(default=ResearchLifecycleState.DRAFT)


class StrategySpec(BaseEntity):
    """FR-003 machine-readable strategy specification."""

    entry_rules: str = Field(..., min_length=1)
    exit_rules: str = Field(..., min_length=1)
    signal_timing: str = Field(default="bar_close_T_to_next_open_Tplus1")
    position_sizing: str = Field(default="")
    stop_loss_rules: str = Field(default="")
    take_profit_rules: str = Field(default="")
    max_holding_period: str = Field(default="")
    universe_rules: str = Field(default="")
    constraints: list[str] = Field(default_factory=list)
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)
    risk_limits: dict[str, Any] = Field(default_factory=dict)
    status: ResearchLifecycleState = Field(default=ResearchLifecycleState.DRAFT)


class DatasetRef(BaseEntity):
    """FR-004 dataset registry entry (identity + provenance, no data bytes)."""

    source: str = Field(..., min_length=1)
    source_version: str = Field(default="1.0.0")
    coverage_start: datetime | None = Field(default=None)
    coverage_end: datetime | None = Field(default=None)
    instruments: list[str] = Field(default_factory=list)
    frequency: str = Field(default="")
    timezone: str = Field(default="UTC")
    schema_version: str = Field(default="1.0.0")
    quality_status: str = Field(default="UNKNOWN")
    checksum: str = Field(default="")


class Experiment(BaseEntity):
    """FR-005 experiment registry entry (immutable config reference)."""

    hypothesis_id: str = Field(..., min_length=1)
    strategy_id: str = Field(..., min_length=1)
    strategy_version: str = Field(default="1.0.0")
    dataset_id: str = Field(..., min_length=1)
    dataset_version: str = Field(default="1.0.0")
    dataset_checksum: str = Field(default="")
    code_commit: str = Field(default="")
    environment_id: str = Field(default="")
    config: dict[str, Any] = Field(default_factory=dict)
    seed: int = Field(default=42)
    execution_model: str = Field(default="")
    cost_model: str = Field(default="")
    risk_model: str = Field(default="")
    status: ResearchLifecycleState = Field(default=ResearchLifecycleState.DRAFT)
    started_at: datetime | None = Field(default=None)
    ended_at: datetime | None = Field(default=None)


class ExperimentRun(BaseEntity):
    """One deterministic execution of an experiment."""

    experiment_id: str = Field(..., min_length=1)
    seed: int = Field(default=42)
    code_commit: str = Field(default="")
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="PENDING")
    metrics: dict[str, float] = Field(default_factory=dict)
