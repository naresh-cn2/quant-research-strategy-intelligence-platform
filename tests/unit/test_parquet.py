"""Tests for the checksum-bound P01 Parquet boundary adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as parquet
import pytest

from qrsip.data import Bar, DatasetDescriptor, ParquetP01Adapter, manifest_bytes
from qrsip.errors import QRSIPError
from qrsip.infrastructure.storage import sha256_hex


def _write_dataset(path: Path) -> tuple[bytes, DatasetDescriptor]:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [
        {
            "timestamp": timestamp + (datetime(2024, 1, 2, tzinfo=UTC) - timestamp) * index,
            "instrument": "AAA",
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "volume": 1_000.0,
        }
        for index in range(3)
    ]
    parquet.write_table(pa.Table.from_pylist(rows), path)
    descriptor = DatasetDescriptor(
        dataset_id="p01-parquet",
        version="1.0.0",
        source="validated-p01",
        instruments=("AAA",),
        coverage_start=rows[0]["timestamp"],
        coverage_end=rows[-1]["timestamp"],
    )
    return manifest_bytes(
        descriptor, checksum=sha256_hex(path.read_bytes()), row_count=3
    ), descriptor


def test_parquet_round_trip_and_adapter_contract(tmp_path: Path) -> None:
    payload = tmp_path / "bars.parquet"
    manifest = tmp_path / "bars.manifest.json"
    content, descriptor = _write_dataset(payload)
    manifest.write_bytes(content)
    adapter = ParquetP01Adapter(payload, manifest)
    handle, bars = adapter.load("p01-parquet", "1.0.0")
    assert adapter.list_datasets() == [descriptor]
    assert adapter.describe("p01-parquet", "1.0.0") == descriptor
    assert handle.checksum == sha256_hex(payload.read_bytes())
    assert bars == tuple(sorted(bars, key=lambda bar: bar.timestamp))
    assert all(isinstance(bar, Bar) for bar in bars)


def test_parquet_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    payload = tmp_path / "bars.parquet"
    manifest = tmp_path / "bars.manifest.json"
    content, _ = _write_dataset(payload)
    manifest.write_bytes(content)
    payload.write_bytes(payload.read_bytes() + b"changed")
    with pytest.raises(QRSIPError, match="checksum mismatch"):
        ParquetP01Adapter(payload, manifest)


def test_parquet_manifest_failures_are_explicit(tmp_path: Path) -> None:
    payload = tmp_path / "bars.parquet"
    manifest = tmp_path / "bars.manifest.json"
    content, _ = _write_dataset(payload)
    with pytest.raises(QRSIPError, match="manifest does not exist"):
        ParquetP01Adapter(payload, manifest)
    manifest.write_bytes(b"not-json")
    with pytest.raises(QRSIPError, match="cannot read"):
        ParquetP01Adapter(payload, manifest)
    manifest.write_bytes(content)
    with pytest.raises(QRSIPError, match="dataset not found"):
        ParquetP01Adapter(payload, manifest).load("other", "1.0.0")


def test_manifest_rejects_invalid_metadata(tmp_path: Path) -> None:
    descriptor = DatasetDescriptor(dataset_id="x", version="1", source="p01", instruments=("AAA",))
    with pytest.raises(QRSIPError, match="checksum"):
        manifest_bytes(descriptor, checksum="bad", row_count=1)
    with pytest.raises(QRSIPError, match="row_count"):
        manifest_bytes(descriptor, checksum="a" * 64, row_count=True)


def test_manifest_is_canonical_json(tmp_path: Path) -> None:
    descriptor = DatasetDescriptor(dataset_id="x", version="1", source="p01", instruments=("AAA",))
    decoded = json.loads(manifest_bytes(descriptor, checksum="a" * 64, row_count=0))
    assert decoded["checksum"] == "a" * 64
    assert decoded["descriptor"]["dataset_id"] == "x"
