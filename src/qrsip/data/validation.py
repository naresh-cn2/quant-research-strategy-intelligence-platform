"""Market-data schema and quality validation (spec 21, 23).

This module is the *fail-closed* gate between raw P01-contract records and the
rest of the platform. Every rule below exists because violating it would let a
strategy consume information that is invalid, ambiguous, or impossible:

- malformed schema / missing fields     -> cannot be interpreted at all
- unsorted records                      -> ordering assumptions are undefined
- duplicate (timestamp, instrument)     -> ambiguous price at a decision point
- invalid OHLC relationships            -> impossible market state
- non-positive prices                   -> impossible market state
- negative volume                       -> impossible market state
- NaN / infinity                        -> poisons every downstream calculation
- naive timestamps                      -> timezone ambiguity / look-ahead risk
- empty dataset                         -> nothing to validate or research

Validation never repairs data. It reports issues and lets the caller decide
(``require_ok`` is the fail-closed path used by the experiment runner).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from qrsip.data.contract import OHLCV_FIELDS, Bar, SchemaError
from qrsip.errors import QRSIPError

__all__ = [
    "DataIssue",
    "DataValidationReport",
    "DataValidationViolation",
    "Severity",
    "parse_bars",
    "validate_bars",
]


class Severity(StrEnum):
    """Impact of a data issue on research validity."""

    ERROR = "ERROR"
    WARNING = "WARNING"


class DataValidationViolation(QRSIPError):  # noqa: N818 - "Violation" is the domain term
    """Raised when error-severity data issues must stop execution."""


class DataIssue(BaseModel):
    """One detected data problem with enough context to locate it."""

    model_config = {"frozen": True, "extra": "forbid"}

    code: str = Field(..., min_length=1, description="Stable machine-readable issue code")
    severity: Severity = Severity.ERROR
    message: str = Field(..., min_length=1)
    row_index: int | None = Field(default=None, ge=0)
    timestamp: datetime | None = Field(default=None)
    instrument: str | None = Field(default=None)

    def describe(self) -> str:
        """Return a single-line human-readable description."""
        location = []
        if self.row_index is not None:
            location.append(f"row={self.row_index}")
        if self.timestamp is not None:
            location.append(f"timestamp={self.timestamp.isoformat()}")
        if self.instrument is not None:
            location.append(f"instrument={self.instrument}")
        where = f" ({', '.join(location)})" if location else ""
        return f"[{self.severity.value}] {self.code}: {self.message}{where}"


class DataValidationReport(BaseModel):
    """Outcome of validating a dataset. Deterministic and serializable."""

    model_config = {"frozen": True, "extra": "forbid"}

    dataset_id: str = Field(default="unknown")
    version: str = Field(default="0.0.0")
    checksum: str = Field(default="")
    row_count: int = Field(default=0, ge=0)
    issues: tuple[DataIssue, ...] = Field(default_factory=tuple)

    @property
    def errors(self) -> tuple[DataIssue, ...]:
        """Return error-severity issues."""
        return tuple(issue for issue in self.issues if issue.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[DataIssue, ...]:
        """Return warning-severity issues."""
        return tuple(issue for issue in self.issues if issue.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        """True when no error-severity issue was found."""
        return not self.errors

    def require_ok(self) -> None:
        """Raise :class:`DataValidationViolation` when errors exist."""
        if not self.ok:
            raise DataValidationViolation(
                "dataset failed validation",
                dataset_id=self.dataset_id,
                version=self.version,
                error_count=len(self.errors),
                issues=[issue.describe() for issue in self.errors],
            )

    def summary(self) -> str:
        """Return a compact human-readable summary line."""
        status = "PASS" if self.ok else "FAIL"
        return (
            f"{status}: dataset={self.dataset_id}@{self.version} rows={self.row_count} "
            f"errors={len(self.errors)} warnings={len(self.warnings)}"
        )


def _as_number(value: Any, field: str, index: int) -> float:
    """Convert a raw value to float, rejecting non-numeric/NaN/inf input."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SchemaError(
            "field is not numeric",
            field=field,
            row_index=index,
            value_type=type(value).__name__,
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SchemaError("field is not numeric", field=field, row_index=index, value=value) from exc
    if math.isnan(number) or math.isinf(number):
        raise SchemaError("field must be finite", field=field, row_index=index, value=value)
    return number


def _as_timestamp(value: Any, index: int) -> datetime:
    """Parse a timestamp, requiring timezone awareness (spec 21)."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise SchemaError("timestamp is not ISO-8601", row_index=index, value=value) from exc
    else:
        raise SchemaError(
            "timestamp must be a datetime or ISO-8601 string",
            row_index=index,
            value_type=type(value).__name__,
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchemaError("timestamp must be timezone-aware", row_index=index, value=str(value))
    return parsed


def parse_bars(records: Iterable[Mapping[str, Any]]) -> tuple[Bar, ...]:
    """Parse raw OHLCV records into :class:`Bar` objects.

    Raises :class:`~qrsip.data.contract.SchemaError` on the first structurally
    invalid record. Structural errors are not recoverable: a record without a
    usable price or timestamp cannot be repaired without inventing data.
    """
    bars: list[Bar] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise SchemaError(
                "record must be a mapping",
                row_index=index,
                value_type=type(record).__name__,
            )
        missing = [field for field in OHLCV_FIELDS if field not in record]
        if missing:
            raise SchemaError("record is missing required fields", row_index=index, missing=missing)
        instrument = record["instrument"]
        if not isinstance(instrument, str) or not instrument.strip():
            raise SchemaError("instrument must be a non-empty string", row_index=index)
        bars.append(
            Bar(
                timestamp=_as_timestamp(record["timestamp"], index),
                instrument=instrument.strip(),
                open=_as_number(record["open"], "open", index),
                high=_as_number(record["high"], "high", index),
                low=_as_number(record["low"], "low", index),
                close=_as_number(record["close"], "close", index),
                volume=_as_number(record["volume"], "volume", index),
            )
        )
    return tuple(bars)


def validate_bars(
    bars: Sequence[Bar],
    *,
    dataset_id: str = "unknown",
    version: str = "0.0.0",
    checksum: str = "",
) -> DataValidationReport:
    """Validate parsed bars against every rule in the module docstring.

    Never raises for data problems and never repairs data: it returns a report.
    Callers that must not proceed use :meth:`DataValidationReport.require_ok`.
    """
    issues: list[DataIssue] = []

    if not bars:
        issues.append(
            DataIssue(
                code="EMPTY_DATASET",
                message="dataset contains no observations; nothing can be researched",
            )
        )
        return DataValidationReport(
            dataset_id=dataset_id,
            version=version,
            checksum=checksum,
            row_count=0,
            issues=tuple(issues),
        )

    seen: set[tuple[datetime, str]] = set()
    previous: tuple[datetime, str] | None = None

    for index, bar in enumerate(bars):
        key = (bar.timestamp, bar.instrument)
        if key in seen:
            issues.append(
                DataIssue(
                    code="DUPLICATE_OBSERVATION",
                    message="duplicate (timestamp, instrument); price is ambiguous at this decision point",
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )
        seen.add(key)

        # Ordering: records must be sorted by (timestamp, instrument).
        if previous is not None and key < previous:
            issues.append(
                DataIssue(
                    code="UNSORTED_RECORDS",
                    message="records are not ordered by (timestamp, instrument)",
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )
        previous = key

        for field_name in ("open", "high", "low", "close"):
            value = getattr(bar, field_name)
            if not math.isfinite(value):
                issues.append(
                    DataIssue(
                        code="NON_FINITE_VALUE",
                        message=f"{field_name} is not finite",
                        row_index=index,
                        timestamp=bar.timestamp,
                        instrument=bar.instrument,
                    )
                )
            elif value <= 0.0:
                issues.append(
                    DataIssue(
                        code="NON_POSITIVE_PRICE",
                        message=f"{field_name}={value} is not a valid price",
                        row_index=index,
                        timestamp=bar.timestamp,
                        instrument=bar.instrument,
                    )
                )

        if not math.isfinite(bar.volume) or bar.volume < 0.0:
            issues.append(
                DataIssue(
                    code="INVALID_VOLUME",
                    message=f"volume={bar.volume} must be finite and non-negative",
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )
        elif bar.volume == 0.0:
            issues.append(
                DataIssue(
                    code="ZERO_VOLUME",
                    severity=Severity.WARNING,
                    message="zero volume; bar is present but untradeable in reality",
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )

        # OHLC consistency: high must bound the bar, low must bound it.
        if not (bar.low <= min(bar.open, bar.close) and max(bar.open, bar.close) <= bar.high):
            issues.append(
                DataIssue(
                    code="INVALID_OHLC",
                    message=(
                        f"OHLC relationship violated: open={bar.open} high={bar.high} "
                        f"low={bar.low} close={bar.close}"
                    ),
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )
        if bar.high < bar.low:
            issues.append(
                DataIssue(
                    code="INVERTED_RANGE",
                    message=f"high={bar.high} is below low={bar.low}",
                    row_index=index,
                    timestamp=bar.timestamp,
                    instrument=bar.instrument,
                )
            )

    return DataValidationReport(
        dataset_id=dataset_id,
        version=version,
        checksum=checksum,
        row_count=len(bars),
        issues=tuple(issues),
    )
