"""Regression tests for defects found during L5-L7 implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from qrsip.errors import ReproducibilityError
from qrsip.infrastructure.storage import FileStorage
from qrsip.intelligence import ExperimentSettings, rerun_experiment, run_experiment


def test_rerun_preserves_canonical_digest(tmp_path: Path) -> None:
    settings = ExperimentSettings.model_validate(
        {
            "id": "EXP-REGRESSION",
            "question": "question",
            "hypothesis": "hypothesis",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "REG",
                "instruments": ["AAA"],
                "periods": 8,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )
    storage = FileStorage(tmp_path / "artifacts")
    original = run_experiment(settings, base_dir=tmp_path, storage=storage)
    assert (
        rerun_experiment(settings, base_dir=tmp_path, storage=storage).result_digest
        == original.result_digest
    )


def test_corrupt_recorded_artifact_is_not_reproducible(tmp_path: Path) -> None:
    settings = ExperimentSettings.model_validate(
        {
            "id": "EXP-REGRESSION",
            "question": "question",
            "hypothesis": "hypothesis",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "REG",
                "instruments": ["AAA"],
                "periods": 8,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )
    storage = FileStorage(tmp_path / "artifacts")
    run_experiment(settings, base_dir=tmp_path, storage=storage)
    payload = storage.read_json("experiments/EXP-REGRESSION/run.json")
    assert isinstance(payload, dict)
    payload["result_digest"] = "0" * 64
    storage.write_json("experiments/EXP-REGRESSION/run.json", payload)
    with pytest.raises(ReproducibilityError):
        rerun_experiment(settings, base_dir=tmp_path, storage=storage)
