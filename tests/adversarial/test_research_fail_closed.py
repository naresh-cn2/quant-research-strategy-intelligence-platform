"""Adversarial tests for fail-closed research behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from qrsip.cli import main
from qrsip.errors import PromotionGateError, ReproducibilityError
from qrsip.infrastructure.storage import FileStorage, StorageError
from qrsip.intelligence import ExperimentSettings, rerun_experiment, run_experiment


def _settings() -> ExperimentSettings:
    return ExperimentSettings.model_validate(
        {
            "id": "EXP-ADVERSARIAL",
            "question": "question",
            "hypothesis": "hypothesis",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "ADV",
                "instruments": ["AAA"],
                "periods": 8,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )


def test_tampered_digest_fails_reproduction(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path / "artifacts")
    run_experiment(_settings(), base_dir=tmp_path, storage=storage)
    payload = storage.read_json("experiments/EXP-ADVERSARIAL/run.json")
    assert isinstance(payload, dict)
    payload["result_digest"] = "0" * 64
    storage.write_json("experiments/EXP-ADVERSARIAL/run.json", payload)
    with pytest.raises(ReproducibilityError):
        rerun_experiment(_settings(), base_dir=tmp_path, storage=storage)


def test_promotion_cannot_bypass_failed_validation(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path / "artifacts")
    run_experiment(_settings(), base_dir=tmp_path, storage=storage)
    with pytest.raises(PromotionGateError):
        main(
            [
                "promote",
                "--experiment-id",
                "EXP-ADVERSARIAL",
                "--decision",
                "APPROVE",
                "--reviewer",
                "researcher",
                "--rationale",
                "attempted approval",
                "--artifacts",
                str(tmp_path / "artifacts"),
            ]
        )


def test_human_rejection_is_recorded_and_visible_in_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = FileStorage(tmp_path / "artifacts")
    run_experiment(_settings(), base_dir=tmp_path, storage=storage)
    assert (
        main(
            [
                "promote",
                "--experiment-id",
                "EXP-ADVERSARIAL",
                "--decision",
                "REJECT",
                "--reviewer",
                "researcher",
                "--rationale",
                "Validation evidence is not sufficient",
                "--artifacts",
                str(tmp_path / "artifacts"),
            ]
        )
        == 0
    )
    promotion = storage.read_json("experiments/EXP-ADVERSARIAL/promotion.json")
    assert isinstance(promotion, dict)
    assert promotion["decision"] == "REJECT"
    assert promotion["decided_by"] == "researcher"
    assert (
        main(
            [
                "report",
                "show",
                "--experiment-id",
                "EXP-ADVERSARIAL",
                "--artifacts",
                str(tmp_path / "artifacts"),
            ]
        )
        == 0
    )
    assert "Human decision: REJECT" in capsys.readouterr().out


def test_missing_report_artifact_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(StorageError):
        main(
            [
                "report",
                "show",
                "--experiment-id",
                "MISSING",
                "--artifacts",
                str(tmp_path / "artifacts"),
            ]
        )
