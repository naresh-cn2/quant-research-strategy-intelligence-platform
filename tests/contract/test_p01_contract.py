"""Contract tests for the QRSIP/P01 data boundary."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qrsip.data import (
    DatasetManifest,
    FixtureP01Provider,
    LookAheadError,
    MarketDataset,
    P01DataContract,
)


def test_fixture_provider_satisfies_p01_contract() -> None:
    provider = FixtureP01Provider()
    assert isinstance(provider, P01DataContract)
    descriptor = provider.list_datasets()[0]
    assert descriptor.dataset_id
    assert descriptor.version
    assert descriptor.instruments
    assert descriptor.is_fixture is True
    assert descriptor.limitations


def test_manifest_records_exact_input_identity() -> None:
    provider = FixtureP01Provider()
    handle, bars = provider.load("FIXTURE-P01-EQUITY-DAILY", "1.0.0")
    dataset = MarketDataset(handle, bars)
    manifest = DatasetManifest.from_dataset(dataset)
    assert manifest.checksum == handle.checksum
    assert manifest.row_count == len(bars)
    assert manifest.coverage_start == bars[0].timestamp
    assert manifest.coverage_end == bars[-1].timestamp
    assert manifest.is_fixture is True
    assert "SYNTHETIC FIXTURE" in " ".join(manifest.limitations)


def test_point_in_time_view_refuses_future_reads() -> None:
    provider = FixtureP01Provider()
    handle, bars = provider.load("FIXTURE-P01-EQUITY-DAILY", "1.0.0")
    dataset = MarketDataset(handle, bars)
    view = dataset.view_at(bars[0].timestamp)
    assert view.visible_count == 1
    with pytest.raises(LookAheadError):
        view.price(bars[0].instrument, at=datetime(2030, 1, 1, tzinfo=UTC))
