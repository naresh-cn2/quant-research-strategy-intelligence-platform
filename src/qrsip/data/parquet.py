"""Checksum-bound Parquet adapter for already-validated P01 OHLCV data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as parquet

from qrsip.data.contract import Bar, DatasetDescriptor, DatasetHandle
from qrsip.data.validation import parse_bars, validate_bars
from qrsip.errors import QRSIPError
from qrsip.infrastructure.storage import canonical_json_bytes, sha256_hex

__all__ = ["ParquetP01Adapter", "load_parquet_dataset", "manifest_bytes"]


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise QRSIPError("Parquet dataset manifest does not exist", path=str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QRSIPError("cannot read Parquet dataset manifest", reason=str(exc)) from exc
    if not isinstance(payload, dict):
        raise QRSIPError("Parquet dataset manifest must be a JSON object")
    missing = sorted({"descriptor", "checksum", "row_count"} - payload.keys())
    if missing:
        raise QRSIPError("Parquet dataset manifest is incomplete", missing=missing)
    return payload


def _validate_digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise QRSIPError("manifest checksum must be a lowercase SHA-256 hex digest")
    return value


def load_parquet_dataset(path: Path, manifest_path: Path) -> tuple[DatasetHandle, tuple[Bar, ...]]:
    """Load a manifest-bound Parquet payload, preserving P01 validation rules."""
    if not path.is_file():
        raise QRSIPError("Parquet dataset file does not exist", path=str(path))
    manifest = _read_manifest(manifest_path)
    try:
        descriptor = DatasetDescriptor.model_validate(manifest["descriptor"])
    except (TypeError, ValueError) as exc:
        raise QRSIPError("invalid Parquet dataset manifest", reason=str(exc)) from exc
    expected_checksum = _validate_digest(manifest["checksum"])
    row_count = manifest["row_count"]
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise QRSIPError("manifest row_count must be a non-negative integer")
    try:
        actual_checksum = sha256_hex(path.read_bytes())
    except OSError as exc:
        raise QRSIPError("cannot read Parquet payload", reason=str(exc)) from exc
    if actual_checksum != expected_checksum:
        raise QRSIPError(
            "Parquet dataset checksum mismatch",
            expected=expected_checksum,
            actual=actual_checksum,
        )
    try:
        table = parquet.read_table(path)
    except Exception as exc:  # PyArrow exception classes vary by supported version.
        raise QRSIPError("cannot read Parquet payload", reason=str(exc)) from exc
    columns = ("timestamp", "instrument", "open", "high", "low", "close", "volume")
    missing = sorted(set(columns) - set(table.column_names))
    if missing:
        raise QRSIPError("Parquet payload schema is incomplete", missing=missing)
    records: list[dict[str, Any]] = [
        {column: row[column] for column in columns} for row in table.to_pylist()
    ]
    bars = parse_bars(records)
    report = validate_bars(
        bars,
        dataset_id=descriptor.dataset_id,
        version=descriptor.version,
        checksum=actual_checksum,
    )
    report.require_ok()
    if len(bars) != row_count:
        raise QRSIPError(
            "Parquet manifest row count mismatch", expected=row_count, actual=len(bars)
        )
    actual_instruments = tuple(sorted({bar.instrument for bar in bars}))
    if actual_instruments != tuple(sorted(set(descriptor.instruments))):
        raise QRSIPError(
            "Parquet manifest instrument set mismatch",
            expected=sorted(set(descriptor.instruments)),
            actual=list(actual_instruments),
        )
    if bars and descriptor.coverage_start not in (None, bars[0].timestamp):
        raise QRSIPError("Parquet manifest coverage_start mismatch")
    if bars and descriptor.coverage_end not in (None, bars[-1].timestamp):
        raise QRSIPError("Parquet manifest coverage_end mismatch")
    handle = DatasetHandle(descriptor=descriptor, checksum=actual_checksum, row_count=len(bars))
    return handle, bars


def manifest_bytes(descriptor: DatasetDescriptor, *, checksum: str, row_count: int) -> bytes:
    """Return canonical manifest bytes for an external P01 data producer."""
    _validate_digest(checksum)
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise QRSIPError("row_count must be a non-negative integer")
    return canonical_json_bytes(
        {
            "checksum": checksum,
            "descriptor": descriptor.model_dump(mode="json"),
            "row_count": row_count,
        }
    )


class ParquetP01Adapter:
    """One configured P01 Parquet dataset implementing the narrow data contract."""

    def __init__(self, path: Path, manifest_path: Path) -> None:
        self._handle, self._bars = load_parquet_dataset(path, manifest_path)

    def list_datasets(self) -> list[DatasetDescriptor]:
        return [self._handle.descriptor]

    def describe(self, dataset_id: str, version: str) -> DatasetDescriptor:
        descriptor = self._handle.descriptor
        if (dataset_id, version) != (descriptor.dataset_id, descriptor.version):
            raise QRSIPError("dataset not found", dataset_id=dataset_id, version=version)
        return descriptor

    def load(self, dataset_id: str, version: str) -> tuple[DatasetHandle, tuple[Bar, ...]]:
        self.describe(dataset_id, version)
        return self._handle, self._bars
