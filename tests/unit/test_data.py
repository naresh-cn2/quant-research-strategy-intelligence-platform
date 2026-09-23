"""
Tests for qrsip.data — P01 contract, schema/quality validation, fixtures, and
point-in-time dataset access (spec §17, §21; ADR-0005, ADR-0007).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from qrsip.data import (
    Bar,
    DatasetDescriptor,
    DatasetHandle,
    DataValidationReport,
    FixtureP01Provider,
    LookAheadError,
    MarketDataset,
    P01DataContract,
    PointInTimeView,
    SchemaError,
    Severity,
    build_fixture_bars,
    parse_bars,
    validate_bars,
)
from qrsip.data.dataset import DatasetManifest
from qrsip.data.fixtures import DEFAULT_FIXTURE, FIXTURE_LIMITATION, FixtureSpec
from qrsip.data.validation import DataValidationViolation
from qrsip.errors import QRSIPError

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _dt(day: int) -> datetime:
    return datetime(2024, 1, day, tzinfo=UTC)


def _bar(
    timestamp: datetime,
    *,
    instrument: str = "AAA",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    volume: float = 1_000.0,
) -> Bar:
    return Bar(
        timestamp=timestamp,
        instrument=instrument,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _bars(n: int = 5, *, instrument: str = "AAA") -> tuple[Bar, ...]:
    def make(i: int) -> Bar:
        close = 100.0 + i
        return _bar(
            _dt(i + 1),
            instrument=instrument,
            open_=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
        )

    return tuple(make(i) for i in range(n))


def _handle(
    bars: tuple[Bar, ...], *, dataset_id: str = "T", version: str = "1.0.0"
) -> DatasetHandle:
    descriptor = DatasetDescriptor(
        dataset_id=dataset_id,
        version=version,
        source="test.source",
        instruments=tuple(sorted({bar.instrument for bar in bars})),
        coverage_start=bars[0].timestamp if bars else None,
        coverage_end=bars[-1].timestamp if bars else None,
        is_fixture=True,
        limitations=(FIXTURE_LIMITATION,),
    )
    return DatasetHandle(descriptor=descriptor, checksum="c" * 64, row_count=len(bars))


def _record(day: int, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "timestamp": _dt(day),
        "instrument": "AAA",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1_000.0,
    }
    record.update(overrides)
    return record


class TestBarContract:
    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(SchemaError):
            Bar(
                timestamp=datetime(2024, 1, 1),
                instrument="AAA",
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )

    def test_empty_instrument_rejected(self) -> None:
        with pytest.raises(SchemaError):
            Bar(
                timestamp=T0,
                instrument="",
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )

    def test_bar_is_frozen(self) -> None:
        bar = _bar(T0)
        with pytest.raises(AttributeError):  # frozen dataclass -> FrozenInstanceError
            bar.close = 2.0  # type: ignore[misc]


class TestParseBars:
    def test_valid_records_parse(self) -> None:
        bars = parse_bars([_record(1), _record(2)])
        assert len(bars) == 2
        assert bars[0].close == 100.5
        assert bars[0].timestamp.tzinfo is not None

    def test_empty_input_returns_empty(self) -> None:
        assert parse_bars([]) == ()

    def test_iso_string_timestamp_parses(self) -> None:
        bars = parse_bars([_record(1, timestamp="2024-01-01T00:00:00Z")])
        assert bars[0].timestamp == T0

    @pytest.mark.parametrize(
        "record_override",
        [
            {"close": None},
            {"instrument": ""},
            {"volume": math.nan},
            {"close": math.inf},
            {"timestamp": datetime(2024, 1, 1)},  # naive
            {"timestamp": "not-a-date"},
            {"open": "abc"},
            {"open": True},  # bool is not a price
        ],
    )
    def test_structurally_invalid_records_fail_closed(
        self, record_override: dict[str, object]
    ) -> None:
        with pytest.raises(SchemaError):
            parse_bars([_record(1, **record_override)])

    def test_missing_field_fails_closed(self) -> None:
        record = _record(1)
        del record["volume"]
        with pytest.raises(SchemaError) as excinfo:
            parse_bars([record])
        assert "volume" in excinfo.value.context["missing"]

    def test_non_mapping_record_fails_closed(self) -> None:
        with pytest.raises(SchemaError):
            parse_bars([(1, 2, 3)])  # type: ignore[list-item]


class TestValidateBars:
    def test_valid_bars_pass(self) -> None:
        report = validate_bars(_bars(5), dataset_id="T", version="1.0.0", checksum="c" * 64)
        assert report.ok
        assert report.errors == ()
        assert report.row_count == 5
        report.require_ok()  # must not raise
        assert report.summary().startswith("PASS:")

    def test_empty_dataset_is_error(self) -> None:
        report = validate_bars([])
        assert not report.ok
        assert any(issue.code == "EMPTY_DATASET" for issue in report.errors)
        with pytest.raises(DataValidationViolation):
            report.require_ok()

    def test_duplicates_detected(self) -> None:
        bars = (_bar(_dt(1)), _bar(_dt(1)))
        codes = {i.code for i in validate_bars(bars).errors}
        assert "DUPLICATE_OBSERVATION" in codes

    def test_unsorted_detected(self) -> None:
        bars = (_bar(_dt(2)), _bar(_dt(1)))
        codes = {i.code for i in validate_bars(bars).errors}
        assert "UNSORTED_RECORDS" in codes

    def test_non_positive_price_detected(self) -> None:
        bars = (_bar(_dt(1), low=0.0, open_=10.0, close=5.0),)
        codes = {i.code for i in validate_bars(bars).errors}
        assert "NON_POSITIVE_PRICE" in codes

    def test_non_finite_detected(self) -> None:
        bars = (_bar(_dt(1), close=math.nan),)
        codes = {i.code for i in validate_bars(bars).errors}
        assert "NON_FINITE_VALUE" in codes

    def test_negative_volume_detected(self) -> None:
        bars = (_bar(_dt(1), volume=-1.0),)
        codes = {i.code for i in validate_bars(bars).errors}
        assert "INVALID_VOLUME" in codes

    def test_zero_volume_is_warning_not_error(self) -> None:
        report = validate_bars((_bar(_dt(1), volume=0.0),))
        assert report.ok  # warnings do not block
        assert any(i.code == "ZERO_VOLUME" for i in report.warnings)
        assert all(w.severity is Severity.WARNING for w in report.warnings)

    def test_invalid_ohlc_detected(self) -> None:
        # close above high violates the bounding relationship
        bars = (_bar(_dt(1), open_=100.0, high=100.5, low=99.0, close=101.0),)
        codes = {i.code for i in validate_bars(bars).errors}
        assert "INVALID_OHLC" in codes

    def test_inverted_range_detected(self) -> None:
        bars = (_bar(_dt(1), open_=50.0, high=40.0, low=60.0, close=50.0),)
        codes = {i.code for i in validate_bars(bars).errors}
        assert "INVERTED_RANGE" in codes

    def test_issue_describe_includes_location(self) -> None:
        report = validate_bars((_bar(_dt(1), volume=-1.0),), dataset_id="T")
        text = report.errors[0].describe()
        assert "row=0" in text
        assert "AAA" in text
        assert "INVALID_VOLUME" in text

    def test_report_is_serializable(self) -> None:
        report = validate_bars(_bars(2), dataset_id="T", version="1.0.0")
        dumped = report.model_dump(mode="json")
        assert DataValidationReport.model_validate(dumped) == report


class TestMarketDataset:
    def test_construction_from_ordered_bars(self) -> None:
        bars = _bars(5)
        dataset = MarketDataset(_handle(bars), bars)
        assert len(dataset) == 5
        assert dataset.timestamps == tuple(_dt(i + 1) for i in range(5))
        assert dataset.is_fixture is True
        assert dataset.bars_for("AAA") == bars

    def test_multi_instrument_iteration_is_deterministic(self) -> None:
        bars = tuple(
            sorted(
                (*_bars(3, instrument="AAA"), *_bars(3, instrument="BBB")),
                key=lambda b: (b.timestamp, b.instrument),
            )
        )
        dataset = MarketDataset(_handle(bars), bars)
        assert dataset.timestamps == tuple(_dt(i + 1) for i in range(3))
        assert len(dataset.bars_for("BBB")) == 3

    def test_row_count_mismatch_fails_closed(self) -> None:
        bars = _bars(5)
        handle = _handle(bars)
        with pytest.raises(QRSIPError, match="row count"):
            MarketDataset(handle, bars[:-1])

    def test_unordered_bars_fail_closed(self) -> None:
        bars = (_bar(_dt(2)), _bar(_dt(1)))
        with pytest.raises(QRSIPError, match="not ordered"):
            MarketDataset(_handle(bars), bars)

    def test_manifest_carries_identity(self) -> None:
        bars = _bars(4)
        dataset = MarketDataset(_handle(bars), bars)
        manifest = DatasetManifest.from_dataset(dataset)
        assert manifest.checksum == "c" * 64
        assert manifest.row_count == 4
        assert manifest.is_fixture is True
        assert FIXTURE_LIMITATION in manifest.limitations
        assert "[FIXTURE]" in manifest.identity_line()
        assert manifest == DatasetManifest.model_validate(manifest.model_dump(mode="json"))


class TestPointInTime:
    @pytest.fixture()
    def dataset(self) -> MarketDataset:
        bars = _bars(5)
        return MarketDataset(_handle(bars), bars)

    def test_view_at_start_shows_first_bar_only(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(1))
        assert view.as_of == _dt(1)
        assert view.visible_count == 1
        assert view.price("AAA", at=_dt(1)) == 100.0
        with pytest.raises(LookAheadError):
            view.price("AAA", at=_dt(2))

    def test_advance_reveals_gradually(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(1))
        view.advance_to(_dt(3))
        assert view.visible_count == 3
        assert view.price("AAA", at=_dt(3)) == 102.0
        with pytest.raises(LookAheadError):
            view.price("AAA", at=_dt(4))

    def test_price_exactly_at_boundary_is_visible(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(5))
        assert view.price("AAA", at=_dt(5)) == 104.0

    def test_future_price_raises_look_ahead_with_context(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(2))
        with pytest.raises(LookAheadError) as excinfo:
            view.price("AAA", at=_dt(5))
        assert excinfo.value.context["as_of"] == _dt(2).isoformat()
        assert excinfo.value.context["requested"] == _dt(5).isoformat()
        assert excinfo.value.context["instrument"] == "AAA"

    def test_price_at_missing_timestamp_fails_closed(self) -> None:
        # dataset has a gap at day 2: reading a timestamp inside coverage
        # that has no observation must fail, not assume a price
        bars = (*_bars(1), _bar(_dt(3), open_=102.0, high=103.0, low=101.0, close=102.0))
        dataset = MarketDataset(_handle(bars), bars)
        view = PointInTimeView(dataset, as_of=_dt(3))
        with pytest.raises(QRSIPError, match="no bar exists"):
            view.price("AAA", at=_dt(2))

    def test_advance_backwards_fails_closed(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(3))
        with pytest.raises(LookAheadError, match="cannot move backwards"):
            view.advance_to(_dt(2))

    def test_advance_beyond_end_is_allowed_but_reads_still_fail_closed(
        self, dataset: MarketDataset
    ) -> None:
        # A clock beyond coverage end simply means "everything in the dataset
        # is known by then". It leaks nothing; reads of timestamps with no
        # observation still fail closed.
        view = PointInTimeView(dataset, as_of=_dt(1))
        view.advance_to(_dt(9))
        assert view.visible_count == 5
        assert view.price("AAA", at=_dt(5)) == 104.0
        with pytest.raises(QRSIPError, match="no bar exists"):
            view.price("AAA", at=_dt(6))

    def test_view_before_dataset_start_fails_closed(self, dataset: MarketDataset) -> None:
        with pytest.raises(QRSIPError, match="precedes the dataset start"):
            PointInTimeView(dataset, as_of=datetime(2023, 12, 31, tzinfo=UTC))

    def test_naive_decision_time_rejected(self, dataset: MarketDataset) -> None:
        with pytest.raises(QRSIPError, match="timezone-aware"):
            PointInTimeView(dataset, as_of=datetime(2024, 1, 2))

    def test_last_bar_never_exceeds_clock(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(2))
        last = view.last_bar("AAA")
        assert last is not None
        assert last.timestamp == _dt(2)
        view.advance_to(_dt(5))
        last = view.last_bar("AAA")
        assert last is not None
        assert last.timestamp == _dt(5)

    def test_unknown_instrument_last_bar_fails_closed(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(1))
        with pytest.raises(QRSIPError, match="not present"):
            view.last_bar("ZZZ")

    def test_last_bar_none_when_instrument_not_yet_visible(self) -> None:
        bars = _bars(3)
        other = _bar(_dt(5), instrument="BBB", open_=50.0, high=51.0, low=49.0, close=50.0)
        # keep (timestamp, instrument) ordering required by MarketDataset
        combined = (*bars, other)
        dataset = MarketDataset(_handle(combined), combined)
        view = PointInTimeView(dataset, as_of=_dt(3))
        assert view.last_bar("AAA") is not None
        assert view.last_bar("BBB") is None  # in the dataset, but no bar known yet
        view.advance_to(_dt(5))
        visible = view.last_bar("BBB")
        assert visible is not None
        assert visible.close == 50.0

    def test_history_window_is_bounded(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(5))
        window = view.history("AAA", window=3)
        assert [b.close for b in window] == [102.0, 103.0, 104.0]
        assert view.history("AAA")[-1].close == 104.0
        assert view.history("AAA", window=0) == ()
        # asking for more than exists returns everything known, honestly
        assert len(view.history("AAA", window=10)) == 5

    def test_negative_window_fails_closed(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(2))
        with pytest.raises(QRSIPError, match="non-negative"):
            view.history("AAA", window=-1)

    def test_unknown_instrument_history_fails_closed(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(2))
        with pytest.raises(QRSIPError, match="not present"):
            view.history("ZZZ")

    def test_snapshot_never_exposes_future(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(2))
        snapshot = view.snapshot()
        assert snapshot.bars_by_instrument == {"AAA": 2}
        assert snapshot.last_close == {"AAA": 101.0}
        assert snapshot.as_of == _dt(2)
        assert snapshot.is_fixture is True

    def test_view_dataset_property_returns_dataset(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(1))
        assert view.dataset is dataset

    def test_view_repr_is_informative(self, dataset: MarketDataset) -> None:
        view = PointInTimeView(dataset, as_of=_dt(1))
        assert "as_of=2024-01-01" in repr(view)


class TestFixtureBars:
    def test_deterministic_across_calls(self) -> None:
        first = build_fixture_bars("AAA", start=T0, periods=50, seed=42)
        second = build_fixture_bars("AAA", start=T0, periods=50, seed=42)
        assert first == second

    def test_different_seed_gifferent_series(self) -> None:
        first = build_fixture_bars("AAA", start=T0, periods=50, seed=42)
        second = build_fixture_bars("AAA", start=T0, periods=50, seed=43)
        assert first != second

    def test_ohlc_invariants_hold(self) -> None:
        bars = build_fixture_bars("AAA", start=T0, periods=200, seed=7)
        previous: object = None
        for bar in bars:
            assert bar.low <= min(bar.open, bar.close)
            assert max(bar.open, bar.close) <= bar.high
            assert bar.volume > 0.0
            assert all(math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close))
            key = (bar.timestamp, bar.instrument)
            if previous is not None:
                assert key > previous  # strictly ordered, no duplicates
            previous = key
        assert len(bars) == 200

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"instrument": ""}, "non-empty"),
            ({"periods": 0}, "positive"),
            ({"seed": "abc"}, "integer"),
            ({"start": datetime(2024, 1, 1)}, "timezone"),
        ],
    )
    def test_invalid_arguments_fail_closed(self, kwargs: dict[str, object], match: str) -> None:
        params: dict[str, object] = {"instrument": "AAA", "start": T0, "periods": 5, "seed": 1}
        params.update(kwargs)
        with pytest.raises(QRSIPError, match=match):
            build_fixture_bars(**params)  # type: ignore[arg-type]


class TestFixtureProvider:
    def test_default_provider_satisfies_contract(self) -> None:
        provider = FixtureP01Provider()
        assert isinstance(provider, P01DataContract)

    def test_default_fixture_descriptor_is_labelled(self) -> None:
        provider = FixtureP01Provider()
        descriptor = provider.describe(DEFAULT_FIXTURE.dataset_id, DEFAULT_FIXTURE.version)
        assert descriptor.is_fixture is True
        assert FIXTURE_LIMITATION in descriptor.limitations
        assert "fixture" in descriptor.source
        assert descriptor.coverage_start is not None
        assert descriptor.coverage_end is not None
        assert descriptor.coverage_start <= descriptor.coverage_end

    def test_load_is_deterministic_and_checksummed(self) -> None:
        provider = FixtureP01Provider()
        handle_a, bars_a = provider.load(DEFAULT_FIXTURE.dataset_id, DEFAULT_FIXTURE.version)
        handle_b, bars_b = provider.load(DEFAULT_FIXTURE.dataset_id, DEFAULT_FIXTURE.version)
        assert handle_a.checksum == handle_b.checksum
        assert bars_a == bars_b
        assert handle_a.row_count == len(bars_a)
        # ordering guarantee: (timestamp, instrument)
        keys = [(bar.timestamp, bar.instrument) for bar in bars_a]
        assert keys == sorted(keys)
        # checksum matches independent recomputation via validation report
        report = validate_bars(
            bars_a,
            dataset_id=handle_a.descriptor.dataset_id,
            version=handle_a.descriptor.version,
            checksum=handle_a.checksum,
        )
        assert report.checksum == handle_a.checksum
        assert report.row_count == handle_a.row_count

    def test_list_datasets_is_sorted(self) -> None:
        provider = FixtureP01Provider(
            specs=(
                FixtureSpec(dataset_id="B-SET", instruments=("AAA",), start=T0, periods=2, seed=2),
                FixtureSpec(dataset_id="A-SET", instruments=("AAA",), start=T0, periods=2, seed=1),
            )
        )
        ids = [descriptor.dataset_id for descriptor in provider.list_datasets()]
        assert ids == ["A-SET", "B-SET"]

    def test_multi_instrument_bars_sorted_by_timestamp_then_instrument(self) -> None:
        provider = FixtureP01Provider(
            specs=(
                FixtureSpec(
                    dataset_id="MULTI",
                    version="1.0.0",
                    instruments=("ZZZ", "AAA"),
                    start=T0,
                    periods=3,
                    seed=9,
                ),
            )
        )
        _, bars = provider.load("MULTI", "1.0.0")
        first_two = [(b.timestamp, b.instrument) for b in bars[:2]]
        assert first_two == [(_dt(1), "AAA"), (_dt(1), "ZZZ")]

    def test_unknown_dataset_fails_closed(self) -> None:
        provider = FixtureP01Provider()
        with pytest.raises(QRSIPError, match="unknown fixture dataset"):
            provider.load("NOPE", "1.0.0")
        with pytest.raises(QRSIPError, match="unknown fixture dataset"):
            provider.describe(DEFAULT_FIXTURE.dataset_id, "9.9.9")

    def test_empty_specs_fail_closed(self) -> None:
        with pytest.raises(QRSIPError, match="at least one"):
            FixtureP01Provider(specs=())

    def test_spec_without_instruments_fails_closed(self) -> None:
        with pytest.raises(QRSIPError, match="at least one instrument"):
            FixtureP01Provider(
                specs=(FixtureSpec(dataset_id="X", instruments=(), start=T0, periods=2, seed=1),)
            )

    def test_duplicate_specs_fail_closed(self) -> None:
        spec = FixtureSpec(dataset_id="DUP", instruments=("AAA",), start=T0, periods=2, seed=1)
        with pytest.raises(QRSIPError, match="duplicate"):
            FixtureP01Provider(specs=(spec, spec))
