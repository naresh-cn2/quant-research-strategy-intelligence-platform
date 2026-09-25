"""Behavioral tests for L6 experiment artifacts and report generation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from qrsip.errors import ReproducibilityError
from qrsip.infrastructure.storage import FileStorage
from qrsip.intelligence import (
    ExperimentSettings,
    compare_experiment_runs,
    render_markdown,
    rerun_experiment,
    run_experiment,
)


def _settings(root: Path) -> ExperimentSettings:
    return ExperimentSettings.model_validate(
        {
            "id": "EXP-TEST",
            "question": "Does a deterministic fixture produce a stable result?",
            "hypothesis": "The recorded result is reproducible.",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "TEST-FIXTURE",
                "instruments": ["AAA"],
                "periods": 12,
                "seed": 7,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )


def test_run_writes_canonical_artifacts_and_report(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path / "artifacts")
    run = run_experiment(_settings(tmp_path), base_dir=tmp_path, storage=storage)
    assert storage.exists("experiments/EXP-TEST/run.json")
    assert storage.exists("experiments/EXP-TEST/report.md")
    assert run.experiment.dataset_checksum == run.dataset.checksum
    assert run.question.id == "RQ-EXP-TEST"
    assert run.hypothesis.question_id == run.question.id
    assert run.strategy.id == run.experiment.strategy_id
    assert run.dataset_ref.checksum == run.dataset.checksum
    assert run.validation.experiment_id == "EXP-TEST"
    assert run.report.human_decision == "PENDING"
    assert "Human decision: PENDING" in render_markdown(run)


def test_comparison_reports_evidence_without_conclusion(tmp_path: Path) -> None:
    left = run_experiment(_settings(tmp_path), base_dir=tmp_path)
    right = run_experiment(_settings(tmp_path), base_dir=tmp_path)
    comparison = compare_experiment_runs(left, right)
    assert comparison.left_experiment_id == right.experiment.id
    assert comparison.result_digests == (left.result_digest, right.result_digest)
    assert set(comparison.metric_deltas) >= {"sharpe", "total_return"}
    assert "conclusion" not in comparison.payload()


def test_rerun_requires_matching_digest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    storage = FileStorage(tmp_path / "artifacts")
    first = run_experiment(settings, base_dir=tmp_path, storage=storage)
    assert (
        rerun_experiment(settings, base_dir=tmp_path, storage=storage).result_digest
        == first.result_digest
    )
    stored = storage.read_json("experiments/EXP-TEST/run.json")
    assert isinstance(stored, dict)
    stored["result_digest"] = "0" * 64
    storage.write_json("experiments/EXP-TEST/run.json", stored)
    with pytest.raises(ReproducibilityError, match="digest mismatch"):
        rerun_experiment(settings, base_dir=tmp_path, storage=storage)


def test_invalid_configuration_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExperimentSettings.model_validate(
            {"id": "EXP", "question": "q", "hypothesis": "h", "data": {}}
        )
