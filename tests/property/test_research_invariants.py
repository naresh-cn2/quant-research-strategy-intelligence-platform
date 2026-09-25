"""Invariant tests for deterministic research artifacts."""

from __future__ import annotations

from pathlib import Path

from qrsip.infrastructure.storage import canonical_json_bytes
from qrsip.intelligence import ExperimentSettings, run_experiment


def _settings(periods: int = 10) -> ExperimentSettings:
    return ExperimentSettings.model_validate(
        {
            "id": "EXP-PROPERTY",
            "question": "question",
            "hypothesis": "hypothesis",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "PROPERTY",
                "instruments": ["AAA"],
                "periods": periods,
                "seed": 5,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )


def test_run_is_byte_stable_across_repeated_executions(tmp_path: Path) -> None:
    first = run_experiment(_settings(), base_dir=tmp_path)
    second = run_experiment(_settings(), base_dir=tmp_path)
    assert first.result_digest == second.result_digest
    assert canonical_json_bytes(first.payload()) == canonical_json_bytes(second.payload())


def test_fixture_dataset_membership_is_preserved(tmp_path: Path) -> None:
    run = run_experiment(_settings(periods=9), base_dir=tmp_path)
    assert run.dataset.instruments == ("AAA",)
    assert run.dataset.row_count == 9
    assert run.result.instrument_count == 1
    assert run.result.bar_count == 9
