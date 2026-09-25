"""Bias checks for causal execution and point-in-time universe selection."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qrsip.data.dataset import MarketDataset
from qrsip.errors import QRSIPError
from qrsip.simulation.engine import SimulationResult

__all__ = [
    "LookAheadEvidence",
    "SurvivorshipEvidence",
    "SurvivorshipUniverseSnapshot",
    "ValidationStatus",
    "verify_look_ahead",
    "verify_survivorship",
]


class ValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


class SurvivorshipUniverseSnapshot(BaseModel):
    """Historical membership known as of one timestamp."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    instruments: tuple[str, ...]
    source: str = Field(..., min_length=1)

    @field_validator("instruments")
    @classmethod
    def _unique_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or any(not item for item in value):
            raise ValueError("historical universe must contain non-empty instruments")
        if len(value) != len(set(value)):
            raise ValueError("historical universe contains duplicate instruments")
        return value


class LookAheadEvidence(BaseModel):
    """Audit of fill timing and point-in-time price access."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    status: ValidationStatus
    fill_count: int = Field(ge=0)
    causal_fill_count: int = Field(ge=0)
    equity_point_count: int = Field(ge=0)
    violations: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def observed(self) -> str:
        return f"{self.causal_fill_count}/{self.fill_count} fills satisfied recorded causal checks"


class SurvivorshipEvidence(BaseModel):
    """Audit comparing a dataset with historical point-in-time universes."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    status: ValidationStatus
    snapshot_count: int = Field(ge=0)
    missing_instruments: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def observed(self) -> str:
        if not self.snapshot_count:
            return "survivorship cannot be assessed without membership evidence"
        if not self.missing_instruments:
            return f"dataset contains all instruments in {self.snapshot_count} historical snapshots"
        return f"{len(self.missing_instruments)} historically eligible instruments are absent"


def verify_look_ahead(result: SimulationResult, dataset: MarketDataset) -> LookAheadEvidence:
    """Verify observable execution invariants; never infer missing strategy history."""
    if result.dataset_checksum != dataset.checksum:
        raise QRSIPError("simulation and dataset checksums differ")
    violations: list[str] = []
    causal = 0
    for item in result.fills:
        fill = item.fill
        if fill.fill_time <= fill.decision_time:
            violations.append(f"same-or-prior fill for {fill.instrument} at {fill.decision_time}")
            continue
        if fill.instrument not in dataset.instruments:
            violations.append(f"unknown instrument {fill.instrument}")
            continue
        matching_bars = [
            bar for bar in dataset.bars_for(fill.instrument) if bar.timestamp == fill.fill_time
        ]
        if not matching_bars:
            violations.append(f"fill has no point-in-time price for {fill.instrument}")
            continue
        causal += 1
    times = [point.timestamp for point in result.equity_curve]
    if times != sorted(times) or len(times) != len(set(times)):
        violations.append("equity timestamps are not strictly ordered")
    if not result.fills:
        status = ValidationStatus.NOT_VERIFIABLE
    elif violations:
        status = ValidationStatus.FAIL
    else:
        status = ValidationStatus.PASS
    limitations = (
        ("simulation produced no fills; decision-to-fill causality is not observable",)
        if not result.fills
        else ()
    )
    return LookAheadEvidence(
        status=status,
        fill_count=len(result.fills),
        causal_fill_count=causal,
        equity_point_count=len(result.equity_curve),
        violations=tuple(violations),
        limitations=limitations,
    )


def verify_survivorship(
    dataset: MarketDataset,
    snapshots: tuple[SurvivorshipUniverseSnapshot, ...],
) -> SurvivorshipEvidence:
    """Compare observed instruments with complete historical universe snapshots."""
    if not snapshots:
        return SurvivorshipEvidence(
            status=ValidationStatus.NOT_VERIFIABLE,
            snapshot_count=0,
            limitations=("no point-in-time historical universe snapshots were supplied",),
        )
    ordered = sorted(snapshots, key=lambda item: item.timestamp)
    missing = tuple(
        sorted(
            {
                instrument
                for snapshot in ordered
                for instrument in snapshot.instruments
                if instrument not in dataset.instruments
            }
        )
    )
    violations = tuple(
        f"{instrument} was historically eligible but absent from the dataset"
        for instrument in missing
    )
    return SurvivorshipEvidence(
        status=ValidationStatus.FAIL if violations else ValidationStatus.PASS,
        snapshot_count=len(ordered),
        missing_instruments=missing,
        limitations=violations,
    )
