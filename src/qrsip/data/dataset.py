"""Market dataset and point-in-time access (spec §17, FR-004, NFR-001).

This module is the **enforcement point** for the single most important
correctness property in the platform: a strategy may never observe information
that was not yet available at its decision timestamp.

Design
------

``MarketDataset``
    An immutable, validated collection of :class:`Bar` objects plus the
    :class:`DatasetHandle` that identifies it (id, version, checksum, row count).
    Construction validates the ordering guarantee and fails closed.

``PointInTimeView``
    The **only** way strategy code reads bars. It is created with an "as-of"
    timestamp and refuses to reveal anything after that timestamp. Attempting to
    read the future raises :class:`LookAheadError` — it is never silently
    truncated, because silent truncation hides the bug instead of surfacing it.

``MarketSnapshot``
    A bounded, immutable, serializable payload describing what was known at one
    decision point. It carries counts and last prices, never future bars.

``DatasetManifest``
    The auditable identity record written into experiment artifacts so a run can
    be tied to the exact input bytes it consumed.

Time model
----------

A bar's ``timestamp`` is the bar's **close**. Bar information therefore becomes
known exactly *at* that instant, so the rule implemented here is:

    a bar is visible at decision time ``T`` iff ``bar.timestamp <= T``

Executing a decision made at ``T`` on the next bar is a simulation concern
(ADR-0005), deliberately not implemented in this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, Field

from qrsip.data.contract import Bar, DatasetDescriptor, DatasetHandle
from qrsip.errors import QRSIPError

__all__ = [
    "DatasetManifest",
    "LookAheadError",
    "MarketDataset",
    "MarketSnapshot",
    "PointInTimeView",
]


class LookAheadError(QRSIPError):
    """Raised when code attempts to observe market data from the future.

    This is a *deliberate failure*, not a bug to be worked around: it is the
    signal that a strategy, feature, or reporting path has violated the
    point-in-time contract (spec §15, §17).
    """


class MarketDataset:
    """An immutable, validated, ordered collection of bars for one dataset version.

    Ordering guarantee: bars are sorted by ``(timestamp, instrument)``. This is
    enforced at construction so every downstream consumer can rely on it and so
    deterministic iteration never depends on caller discipline.
    """

    __slots__ = ("_bars", "_by_instrument", "_handle")

    def __init__(self, handle: DatasetHandle, bars: Iterable[Bar]) -> None:
        resolved = tuple(bars)
        if len(resolved) != handle.row_count:
            raise QRSIPError(
                "dataset row count does not match handle",
                expected=handle.row_count,
                actual=len(resolved),
            )
        expected_order = tuple(sorted(resolved, key=lambda bar: (bar.timestamp, bar.instrument)))
        if expected_order != resolved:
            raise QRSIPError(
                "dataset bars are not ordered by (timestamp, instrument)",
                dataset_id=handle.descriptor.dataset_id,
                version=handle.descriptor.version,
            )
        instruments = {bar.instrument for bar in resolved}
        undeclared = sorted(instruments.difference(handle.descriptor.instruments))
        if undeclared:
            raise QRSIPError(
                "dataset contains instruments absent from the descriptor",
                dataset_id=handle.descriptor.dataset_id,
                instruments=undeclared,
            )
        self._handle = handle
        self._bars = resolved
        self._by_instrument: dict[str, tuple[Bar, ...]] = {
            instrument: tuple(bar for bar in resolved if bar.instrument == instrument)
            for instrument in sorted(instruments)
        }

    # -- identity ---------------------------------------------------------
    @property
    def handle(self) -> DatasetHandle:
        """Return the dataset handle (identity, checksum, row count)."""
        return self._handle

    @property
    def descriptor(self) -> DatasetDescriptor:
        """Return the dataset descriptor."""
        return self._handle.descriptor

    @property
    def checksum(self) -> str:
        """Return the content identity of the loaded bars."""
        return self._handle.checksum

    @property
    def is_fixture(self) -> bool:
        """True when this dataset is synthetic fixture data (ADR-0007)."""
        return self._handle.descriptor.is_fixture

    @property
    def limitations(self) -> tuple[str, ...]:
        """Return declared limitations that must travel with every result."""
        return self._handle.descriptor.limitations

    @property
    def bars(self) -> tuple[Bar, ...]:
        """Return all bars in deterministic ``(timestamp, instrument)`` order."""
        return self._bars

    @property
    def instruments(self) -> tuple[str, ...]:
        """Return declared instruments in sorted order."""
        return tuple(self._by_instrument)

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        """Return the distinct, ascending decision timestamps in the dataset."""
        seen: list[datetime] = []
        for bar in self._bars:
            if not seen or seen[-1] != bar.timestamp:
                seen.append(bar.timestamp)
        return tuple(seen)

    @property
    def start(self) -> datetime:
        """Return the first timestamp."""
        return self._bars[0].timestamp

    @property
    def end(self) -> datetime:
        """Return the last timestamp."""
        return self._bars[-1].timestamp

    def bars_for(self, instrument: str) -> tuple[Bar, ...]:
        """Return one instrument's bars in ascending timestamp order."""
        try:
            return self._by_instrument[instrument]
        except KeyError as exc:
            raise QRSIPError(
                "instrument not present in dataset",
                instrument=instrument,
                available=list(self._by_instrument),
            ) from exc

    def __len__(self) -> int:
        return len(self._bars)

    def __repr__(self) -> str:
        descriptor = self._handle.descriptor
        return (
            f"MarketDataset(dataset_id={descriptor.dataset_id!r}, "
            f"version={descriptor.version!r}, rows={len(self._bars)}, "
            f"checksum={self._handle.checksum[:12]}...)"
        )

    # -- point-in-time ----------------------------------------------------
    def view_at(self, as_of: datetime) -> PointInTimeView:
        """Return a point-in-time view whose clock is fixed at ``as_of``."""
        return PointInTimeView(self, as_of=as_of)


class PointInTimeView:
    """A forward-only, leakage-proof cursor over a :class:`MarketDataset`.

    The view holds a monotonically non-decreasing "as-of" clock. Reads return
    only bars whose timestamp is ``<= clock``. Any attempt to read past the
    clock raises :class:`LookAheadError`.

    :meth:`advance_to` refuses to move the clock backwards. Backwards movement
    is rejected because it almost always signals an event-ordering bug in the
    simulation loop, and silently permitting it would corrupt the bias
    guarantees the platform claims.
    """

    __slots__ = ("_as_of", "_dataset", "_index")

    def __init__(self, dataset: MarketDataset, *, as_of: datetime) -> None:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise QRSIPError("point-in-time clock must be timezone-aware", as_of=str(as_of))
        if as_of < dataset.start:
            raise LookAheadError(
                "point-in-time clock precedes the dataset start",
                as_of=as_of.isoformat(),
                dataset_start=dataset.start.isoformat(),
            )
        self._dataset = dataset
        self._as_of = as_of
        self._index = sum(1 for bar in dataset.bars if bar.timestamp <= as_of)

    # -- clock ------------------------------------------------------------
    @property
    def as_of(self) -> datetime:
        """Return the current decision timestamp."""
        return self._as_of

    @property
    def dataset(self) -> MarketDataset:
        """Return the underlying dataset (identity and metadata only)."""
        return self._dataset

    def advance_to(self, timestamp: datetime) -> None:
        """Move the clock forward to ``timestamp``.

        Raises :class:`LookAheadError` when ``timestamp`` precedes the clock.
        """
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise QRSIPError("advance target must be timezone-aware", timestamp=str(timestamp))
        if timestamp < self._as_of:
            raise LookAheadError(
                "point-in-time clock cannot move backwards",
                current=self._as_of.isoformat(),
                requested=timestamp.isoformat(),
            )
        self._as_of = timestamp
        self._index = sum(1 for bar in self._dataset.bars if bar.timestamp <= timestamp)

    # -- reads ------------------------------------------------------------
    @property
    def visible_count(self) -> int:
        """Return the number of bars currently visible at the clock."""
        return self._index

    def visible_bars(self) -> tuple[Bar, ...]:
        """Return all bars visible at the current clock, in dataset order."""
        return self._dataset.bars[: self._index]

    def history(self, instrument: str, *, window: int | None = None) -> tuple[Bar, ...]:
        """Return visible bars for ``instrument``, optionally the last ``window``.

        Requesting more bars than are visible is *not* an error: it returns
        everything known so far. That is the honest behaviour — strategies must
        decide for themselves whether they have enough history to act.
        """
        if window is not None and window < 0:
            raise QRSIPError("history window must be non-negative", window=window)
        bars = tuple(
            bar for bar in self._dataset.bars_for(instrument) if bar.timestamp <= self._as_of
        )
        if window is None:
            return bars
        return bars[-window:] if window else ()

    def last_bar(self, instrument: str) -> Bar | None:
        """Return the most recent visible bar for ``instrument``, or ``None``."""
        recent = self.history(instrument, window=1)
        return recent[-1] if recent else None

    def price(self, instrument: str, *, at: datetime) -> float:
        """Return the close of ``instrument`` exactly at ``at``.

        Raises :class:`LookAheadError` when ``at`` is in the future relative to
        the view clock, and :class:`QRSIPError` when no bar exists at ``at``.

        This method is intentionally strict: pricing a position at a timestamp
        with no observation is an *assumption*, and assumptions must be declared
        by the caller rather than made silently by infrastructure.
        """
        if at > self._as_of:
            raise LookAheadError(
                "attempted to read a price from the future",
                requested=at.isoformat(),
                as_of=self._as_of.isoformat(),
                instrument=instrument,
            )
        for bar in self._dataset.bars_for(instrument):
            if bar.timestamp == at:
                return bar.close
        raise QRSIPError(
            "no bar exists at the requested timestamp",
            instrument=instrument,
            requested=at.isoformat(),
        )

    def snapshot(self, *, instruments: Iterable[str] | None = None) -> MarketSnapshot:
        """Return the immutable payload describing this decision point."""
        selected = (
            tuple(sorted(set(instruments)))
            if instruments is not None
            else self._dataset.instruments
        )
        history = {instrument: self.history(instrument) for instrument in selected}
        return MarketSnapshot(
            as_of=self._as_of,
            dataset_id=self._dataset.descriptor.dataset_id,
            dataset_version=self._dataset.descriptor.version,
            dataset_checksum=self._dataset.checksum,
            is_fixture=self._dataset.is_fixture,
            bars_by_instrument={name: len(bars) for name, bars in history.items()},
            last_close={
                name: bars[-1].close for name, bars in history.items() if bars
            },
        )

    def __repr__(self) -> str:
        return (
            f"PointInTimeView(as_of={self._as_of.isoformat()}, "
            f"visible={self._index}/{len(self._dataset)})"
        )


class MarketSnapshot(BaseModel):
    """Immutable, serializable description of one decision point.

    Strategies receive bar history as immutable tuples, never as a live cursor,
    so they structurally cannot reach future observations between decisions.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    as_of: datetime
    dataset_id: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    dataset_checksum: str = Field(..., min_length=1)
    is_fixture: bool = Field(default=False)
    bars_by_instrument: dict[str, int] = Field(default_factory=dict)
    last_close: dict[str, float] = Field(default_factory=dict)


class DatasetManifest(BaseModel):
    """Auditable dataset identity written into experiment artifacts (spec §26).

    A manifest is the bridge between "an experiment ran" and "these exact input
    bytes were used". It records checksum, coverage, fixture status, and declared
    limitations so no reader can mistake fixture output for market evidence.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    dataset_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    source_version: str = Field(default="1.0.0")
    schema_version: str = Field(default="1.0.0")
    checksum: str = Field(..., min_length=1)
    row_count: int = Field(..., ge=0)
    instruments: tuple[str, ...] = Field(default_factory=tuple)
    frequency: str = Field(default="1d")
    timezone: str = Field(default="UTC")
    coverage_start: datetime | None = Field(default=None)
    coverage_end: datetime | None = Field(default=None)
    is_fixture: bool = Field(default=False)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    @classmethod
    def from_dataset(cls, dataset: MarketDataset) -> DatasetManifest:
        """Build a manifest from a loaded and validated dataset."""
        descriptor = dataset.descriptor
        return cls(
            dataset_id=descriptor.dataset_id,
            version=descriptor.version,
            source=descriptor.source,
            source_version=descriptor.source_version,
            schema_version=descriptor.schema_version,
            checksum=dataset.checksum,
            row_count=dataset.handle.row_count,
            instruments=descriptor.instruments,
            frequency=descriptor.frequency,
            timezone=descriptor.timezone,
            coverage_start=descriptor.coverage_start,
            coverage_end=descriptor.coverage_end,
            is_fixture=descriptor.is_fixture,
            limitations=descriptor.limitations,
        )

    def identity_line(self) -> str:
        """Return a one-line identity string for logs and reports."""
        kind = "FIXTURE" if self.is_fixture else "MARKET"
        return (
            f"{self.dataset_id}@{self.version} [{kind}] "
            f"rows={self.row_count} sha256={self.checksum[:12]}..."
        )
