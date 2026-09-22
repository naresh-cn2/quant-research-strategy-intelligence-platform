"""P01 boundary: the market-data contract P02 consumes (spec §2.1, §21; ADR-0007).

P02 does **not** reimplement P01 ingestion, normalization, quarantine, or
replay. It consumes already-validated, point-in-time market data through the
:class:`P01DataContract` protocol below.

Two implementations exist:

- :class:`~qrsip.data.fixtures.FixtureP01Provider` — deterministic, clearly
  labelled fixtures used for development and tests. **These are not real P01
  production data.**
- A real P01 adapter, which is out of scope for this repository and must
  implement the same protocol.

The contract is deliberately narrow: describe datasets, hand back ordered bars.
Anything richer (ingestion, raw vendor formats, replay scheduling) stays in P01.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from qrsip.errors import QRSIPError

__all__ = [
    "OHLCV_FIELDS",
    "Bar",
    "DatasetDescriptor",
    "DatasetHandle",
    "P01DataContract",
    "SchemaError",
]

OHLCV_FIELDS: tuple[str, ...] = ("timestamp", "instrument", "open", "high", "low", "close", "volume")


class SchemaError(QRSIPError):
    """Raised when market data does not conform to the declared schema."""


@dataclass(frozen=True, slots=True)
class Bar:
    """One validated OHLCV observation.

    ``timestamp`` is the *close* of the bar in UTC (the moment the bar's
    information becomes known). Decision code therefore may use this bar at
    ``timestamp`` and not before (spec §17).
    """

    timestamp: datetime
    instrument: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise SchemaError("bar timestamp must be timezone-aware", instrument=self.instrument)
        if not self.instrument:
            raise SchemaError("bar instrument must be non-empty")


class DatasetDescriptor(BaseModel):
    """Identity of a P01 dataset version (no data bytes)."""

    model_config = {"frozen": True, "extra": "forbid"}

    dataset_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    source_version: str = Field(default="1.0.0")
    instruments: tuple[str, ...] = Field(default_factory=tuple)
    frequency: str = Field(default="1d")
    timezone: str = Field(default="UTC")
    schema_version: str = Field(default="1.0.0")
    coverage_start: datetime | None = Field(default=None)
    coverage_end: datetime | None = Field(default=None)
    is_fixture: bool = Field(default=False)
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class DatasetHandle(BaseModel):
    """A described dataset plus its content identity and ordering guarantee."""

    model_config = {"frozen": True, "extra": "forbid"}

    descriptor: DatasetDescriptor
    checksum: str = Field(..., min_length=1)
    row_count: int = Field(..., ge=0)
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class P01DataContract(Protocol):
    """The only market-data surface P02 is allowed to depend on."""

    def list_datasets(self) -> list[DatasetDescriptor]:
        """Return known dataset descriptors in deterministic order."""
        ...

    def describe(self, dataset_id: str, version: str) -> DatasetDescriptor:
        """Return the descriptor for one dataset version; fail closed if absent."""
        ...

    def load(self, dataset_id: str, version: str) -> tuple[DatasetHandle, tuple[Bar, ...]]:
        """Return the handle and the bars, ordered by (timestamp, instrument)."""
        ...
