"""Integration tests for the research artifact and CLI vertical slice."""

from __future__ import annotations

from pathlib import Path

from qrsip.cli import main
from qrsip.infrastructure.storage import FileStorage
from qrsip.intelligence import ExperimentSettings, run_experiment


def _write_config(root: Path) -> Path:
    config = root / "experiment.yaml"
    config.write_text(
        """
id: EXP-INTEGRATION
question: Does the deterministic pipeline preserve lineage?
hypothesis: The experiment run and report retain the same dataset checksum.
strategy:
  kind: constant
  signal: LONG
data:
  provider: fixture
  dataset_id: INTEGRATION-FIXTURE
  instruments: [AAA]
  periods: 8
  seed: 3
simulation:
  initial_cash: 10000
  order_quantity: 1
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_experiment_artifact_joins_lineage_and_report(tmp_path: Path) -> None:
    settings = ExperimentSettings.model_validate(
        {
            "id": "EXP-INTEGRATION",
            "question": "question",
            "hypothesis": "hypothesis",
            "strategy": {"kind": "constant", "signal": "LONG"},
            "data": {
                "provider": "fixture",
                "dataset_id": "DS",
                "instruments": ["AAA"],
                "periods": 8,
            },
            "simulation": {"initial_cash": 10_000, "order_quantity": 1},
        }
    )
    run = run_experiment(settings, base_dir=tmp_path)
    assert run.experiment.hypothesis_id.startswith("HYP-")
    assert run.experiment.strategy_id.startswith("STR-")
    assert run.experiment.dataset_checksum == run.dataset.checksum
    assert run.validation.experiment_id == run.experiment.id
    assert run.run_record.experiment_id == run.experiment.id
    assert run.report.experiment_id == run.experiment.id
    assert run.report.human_decision == "PENDING"


def test_cli_run_show_and_rerun(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    artifacts = tmp_path / "artifacts"
    assert (
        main(
            [
                "experiment",
                "run",
                "--config",
                str(config),
                "--artifacts",
                str(artifacts),
            ]
        )
        == 0
    )
    assert FileStorage(artifacts).exists("experiments/EXP-INTEGRATION/report.md")
    assert (
        main(
            [
                "report",
                "show",
                "--experiment-id",
                "EXP-INTEGRATION",
                "--artifacts",
                str(artifacts),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "experiment",
                "rerun",
                "--experiment-id",
                "EXP-INTEGRATION",
                "--config",
                str(config),
                "--artifacts",
                str(artifacts),
            ]
        )
        == 0
    )
