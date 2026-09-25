"""Behavioral verification for L5 statistical, bias, and robustness validation."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from qrsip.data import Bar, DatasetDescriptor, DatasetHandle, MarketDataset
from qrsip.errors import MetricError, QRSIPError
from qrsip.quant import Signal
from qrsip.simulation.engine import SimulationConfig, run_simulation
from qrsip.validation import (
    ParameterPoint,
    SurvivorshipUniverseSnapshot,
    ValidationPolicy,
    ValidationRunner,
    ValidationStatus,
    WalkForwardFold,
    analyze_parameter_sensitivity,
    deflated_sharpe_ratio,
    expected_max_standard_normal,
    holm_bonferroni,
    normal_cdf,
    p_value_two_sided,
    sample_kurtosis_excess,
    sample_skewness,
    t_statistic,
    verify_look_ahead,
    verify_survivorship,
    walk_forward_validation,
)

_T0 = datetime(2024, 1, 1, tzinfo=UTC)
_RETURNS = (0.01, -0.005, 0.02, 0.003, -0.002, 0.015, 0.01, -0.004, 0.008, 0.006)


class _AlwaysLong:
    def target_signal(self, closes: tuple[float, ...]) -> Signal:
        return Signal.LONG


def _dataset(count: int = 6) -> MarketDataset:
    bars = tuple(
        Bar(
            timestamp=_T0 + timedelta(days=index),
            instrument="AAA",
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1_000.0,
        )
        for index in range(count)
    )
    descriptor = DatasetDescriptor(
        dataset_id="validation-data",
        version="1.0.0",
        source="fixture",
        instruments=("AAA",),
        is_fixture=True,
    )
    handle = DatasetHandle(descriptor=descriptor, checksum="a" * 64, row_count=len(bars))
    return MarketDataset(handle, bars)


def _simulation():
    dataset = _dataset()
    result = run_simulation(
        dataset,
        {"AAA": _AlwaysLong()},
        SimulationConfig(initial_cash=100_000.0, order_quantity=2.0),
    )
    return dataset, result


def test_statistical_calculations_and_bounds() -> None:
    assert normal_cdf(0.0) == pytest.approx(0.5)
    assert t_statistic(_RETURNS) > 1.0
    assert 0.0 < p_value_two_sided(t_statistic(_RETURNS)) < 1.0
    assert -1.0 <= sample_skewness(_RETURNS) <= 10.0
    assert sample_kurtosis_excess(_RETURNS) >= -3.0
    assert expected_max_standard_normal(1) == 0.0
    assert expected_max_standard_normal(100) == pytest.approx(math.sqrt(2 * math.log(100)))
    dsr = deflated_sharpe_ratio(2.0, trials=20, returns=_RETURNS)
    assert 0.0 <= dsr <= 1.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_statistics_fail_closed(value: float) -> None:
    with pytest.raises(MetricError):
        normal_cdf(value)
    with pytest.raises(MetricError):
        p_value_two_sided(value)


@pytest.mark.parametrize("returns", [(), (0.1,), (0.1, 0.1)])
def test_undefined_moments_fail_closed(returns: tuple[float, ...]) -> None:
    with pytest.raises(MetricError):
        t_statistic(returns)


def test_dsr_invalid_inputs_fail_closed() -> None:
    with pytest.raises(MetricError):
        deflated_sharpe_ratio(1.0, trials=0, returns=_RETURNS)
    with pytest.raises(MetricError):
        deflated_sharpe_ratio(float("nan"), trials=1, returns=_RETURNS)


def test_holm_correction_is_monotone_and_deterministic() -> None:
    corrected = holm_bonferroni({"b": 0.01, "a": 0.04, "c": 0.20}, alpha=0.05)
    assert [item.name for item in corrected] == ["a", "b", "c"]
    assert [item.adjusted_p_value for item in corrected] == pytest.approx([0.08, 0.03, 0.20])
    assert corrected[1].rejected_at_alpha is True
    assert corrected[0].rejected_at_alpha is False
    assert corrected == holm_bonferroni({"c": 0.20, "b": 0.01, "a": 0.04})


def test_multiple_testing_invalid_inputs_fail_closed() -> None:
    with pytest.raises(QRSIPError):
        holm_bonferroni({})
    with pytest.raises(QRSIPError):
        holm_bonferroni({"x": 1.1})
    with pytest.raises(QRSIPError):
        holm_bonferroni({"x": 0.1}, alpha=0.0)


def test_look_ahead_checks_recorded_fill_timing() -> None:
    dataset, result = _simulation()
    evidence = verify_look_ahead(result, dataset)
    assert evidence.status is ValidationStatus.PASS
    assert evidence.fill_count == evidence.causal_fill_count > 0
    assert evidence.observed.endswith("recorded causal checks")


def test_look_ahead_absent_fills_is_not_verifiable() -> None:
    dataset = _dataset(1)
    result = run_simulation(
        dataset,
        {"AAA": _AlwaysLong()},
        SimulationConfig(initial_cash=100_000.0, order_quantity=2.0),
    )
    evidence = verify_look_ahead(result, dataset)
    assert evidence.status is ValidationStatus.NOT_VERIFIABLE
    assert evidence.limitations


def test_survivorship_requires_point_in_time_evidence() -> None:
    dataset = _dataset()
    absent = verify_survivorship(dataset, ())
    assert absent.status is ValidationStatus.NOT_VERIFIABLE
    present = verify_survivorship(
        dataset,
        (SurvivorshipUniverseSnapshot(timestamp=_T0, instruments=("AAA",), source="archive"),),
    )
    assert present.status is ValidationStatus.PASS
    missing = verify_survivorship(
        dataset,
        (
            SurvivorshipUniverseSnapshot(
                timestamp=_T0, instruments=("AAA", "DELISTED"), source="archive"
            ),
        ),
    )
    assert missing.status is ValidationStatus.FAIL
    assert missing.missing_instruments == ("DELISTED",)


def test_sensitivity_is_deterministic_and_descriptive() -> None:
    points = (
        ParameterPoint(parameter="fast", value=3, score=0.1),
        ParameterPoint(parameter="fast", value=5, score=0.2),
        ParameterPoint(parameter="fast", value=7, score=-0.1),
    )
    result = analyze_parameter_sensitivity(points)
    assert result.point_count == 3
    assert result.best_value == 5
    assert result.worst_value == 7
    assert result.negative_fraction == pytest.approx(1 / 3)
    assert result == analyze_parameter_sensitivity(tuple(reversed(points)))


@pytest.mark.parametrize(
    "points",
    [
        (),
        (ParameterPoint(parameter="fast", value=3, score=0.1),),
        (
            ParameterPoint(parameter="fast", value=3, score=0.1),
            ParameterPoint(parameter="slow", value=7, score=0.2),
        ),
        (
            ParameterPoint(parameter="fast", value=3, score=0.1),
            ParameterPoint(parameter="fast", value=3, score=0.2),
        ),
    ],
)
def test_sensitivity_invalid_grids_fail_closed(points: tuple[ParameterPoint, ...]) -> None:
    with pytest.raises(QRSIPError):
        analyze_parameter_sensitivity(points)


def test_walk_forward_requires_contiguous_ordered_folds() -> None:
    folds = (
        WalkForwardFold(
            fold=1,
            train_start=_T0,
            train_end=_T0 + timedelta(days=2),
            validation_start=_T0 + timedelta(days=3),
            validation_end=_T0 + timedelta(days=5),
            score=0.2,
        ),
        WalkForwardFold(
            fold=2,
            train_start=_T0,
            train_end=_T0 + timedelta(days=5),
            validation_start=_T0 + timedelta(days=6),
            validation_end=_T0 + timedelta(days=8),
            score=0.1,
        ),
    )
    assert walk_forward_validation(folds).mean_score == pytest.approx(0.15)
    bad = (folds[0], folds[0].model_copy(update={"fold": 2}))
    with pytest.raises(QRSIPError, match="overlap"):
        walk_forward_validation(bad)
    with pytest.raises(QRSIPError):
        walk_forward_validation(())


def test_validation_runner_records_missing_robustness_as_not_verifiable() -> None:
    dataset, result = _simulation()
    summary = ValidationRunner().run(
        experiment_id="EXP-001",
        result=result,
        dataset=dataset,
        returns=_RETURNS,
        observed_sharpe=2.0,
    )
    assert summary.check("look_ahead").status is ValidationStatus.PASS
    assert summary.check("survivorship").status is ValidationStatus.NOT_VERIFIABLE
    assert summary.check("parameter_sensitivity").status is ValidationStatus.NOT_VERIFIABLE
    assert summary.overall_status is ValidationStatus.FAIL


def test_validation_runner_can_consume_holm_and_robustness_evidence() -> None:
    dataset, result = _simulation()
    folds = (
        WalkForwardFold(
            fold=1,
            train_start=_T0,
            train_end=_T0 + timedelta(days=2),
            validation_start=_T0 + timedelta(days=3),
            validation_end=_T0 + timedelta(days=5),
            score=0.2,
        ),
    )
    summary = ValidationRunner(ValidationPolicy(trials=10)).run(
        experiment_id="EXP-001",
        result=result,
        dataset=dataset,
        returns=_RETURNS,
        observed_sharpe=2.0,
        p_values={"primary": 0.001, "secondary": 0.4},
        snapshots=(
            SurvivorshipUniverseSnapshot(timestamp=_T0, instruments=("AAA",), source="archive"),
        ),
        sensitivity_points=(
            ParameterPoint(parameter="fast", value=3, score=0.1),
            ParameterPoint(parameter="fast", value=5, score=0.2),
        ),
        walk_forward_folds=folds,
    )
    assert summary.check("multiple_testing").evidence["tests"][0]["adjusted_p_value"] == 0.002
    assert summary.check("parameter_sensitivity").status is ValidationStatus.PASS
    assert summary.check("walk_forward").status is ValidationStatus.PASS


def test_validation_policy_and_missing_lookups_fail_closed() -> None:
    with pytest.raises(ValueError):
        ValidationPolicy(significance_level=1.0)
    dataset, result = _simulation()
    summary = ValidationRunner().run(
        experiment_id="EXP-001",
        result=result,
        dataset=dataset,
        returns=_RETURNS,
        observed_sharpe=2.0,
    )
    with pytest.raises(QRSIPError, match="not found"):
        summary.check("missing")
