"""QRSIP data layer (L2 Data).

Provides the P01 contract, deterministic fixtures, checksum-bound Parquet
access, dataset validation, and point-in-time access. This layer owns *how*
market data reaches the platform and
enforces the rule that no strategy may observe the future (spec §17).

Modules:
- :mod:`qrsip.data.contract`   — P01 boundary (protocol + descriptors)
- :mod:`qrsip.data.fixtures`   — deterministic, clearly-labelled fixtures
- :mod:`qrsip.data.dataset`    — market dataset + point-in-time view
- :mod:`qrsip.data.validation` — schema and quality validation
- :mod:`qrsip.data.parquet`   — checksum-bound Parquet P01 adapter
"""

from __future__ import annotations

from qrsip.data.contract import (
    Bar,
    DatasetDescriptor,
    DatasetHandle,
    P01DataContract,
    SchemaError,
)
from qrsip.data.dataset import (
    DatasetManifest,
    LookAheadError,
    MarketDataset,
    MarketSnapshot,
    PointInTimeView,
)
from qrsip.data.fixtures import FixtureP01Provider, build_fixture_bars
from qrsip.data.parquet import ParquetP01Adapter, load_parquet_dataset, manifest_bytes
from qrsip.data.validation import (
    DataIssue,
    DataValidationReport,
    Severity,
    parse_bars,
    validate_bars,
)

__all__ = [
    "Bar",
    "DataIssue",
    "DataValidationReport",
    "DatasetDescriptor",
    "DatasetHandle",
    "DatasetManifest",
    "FixtureP01Provider",
    "LookAheadError",
    "MarketDataset",
    "MarketSnapshot",
    "P01DataContract",
    "ParquetP01Adapter",
    "PointInTimeView",
    "SchemaError",
    "Severity",
    "build_fixture_bars",
    "load_parquet_dataset",
    "manifest_bytes",
    "parse_bars",
    "validate_bars",
]
