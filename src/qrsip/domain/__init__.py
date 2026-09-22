"""QRSIP domain package (L1 Domain, spec §13-14).

Canonical lifecycle lives in :mod:`qrsip.domain.lifecycle`; entities live in
:mod:`qrsip.domain.entities` / :mod:`qrsip.domain.results`.

This package root re-exports the public domain surface so callers can use
either ``qrsip.domain.<name>`` or the concrete submodule path.
"""

from __future__ import annotations

from qrsip.domain.base import BaseEntity
from qrsip.domain.entities import (
    DatasetRef,
    Experiment,
    ExperimentRun,
    Hypothesis,
    ResearchQuestion,
    StrategySpec,
)
from qrsip.domain.lifecycle import (
    TERMINAL_STATES,
    LifecycleViolation,
    ResearchLifecycleState,
    allowed_transitions,
    can_transition,
    require_transition,
)
from qrsip.domain.registry import RegistryError, ResearchRegistry
from qrsip.domain.results import PromotionDecision, ResearchReport, ValidationResult

__all__ = [
    "TERMINAL_STATES",
    "BaseEntity",
    "DatasetRef",
    "Experiment",
    "ExperimentRun",
    "Hypothesis",
    "LifecycleViolation",
    "PromotionDecision",
    "RegistryError",
    "ResearchLifecycleState",
    "ResearchQuestion",
    "ResearchRegistry",
    "ResearchReport",
    "StrategySpec",
    "ValidationResult",
    "allowed_transitions",
    "can_transition",
    "require_transition",
]
