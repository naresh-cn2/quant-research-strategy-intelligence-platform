"""Acceptance tests for the documented deterministic research workflow."""

from __future__ import annotations

from pathlib import Path

from qrsip.cli import main
from qrsip.infrastructure.storage import FileStorage


def test_end_to_end_run_report_rerun(tmp_path: Path) -> None:
    config = tmp_path / "experiment.yaml"
    config.write_text(
        "id: EXP-ACCEPTANCE\n"
        "question: acceptance question\n"
        "hypothesis: acceptance hypothesis\n"
        "strategy:\n"
        "  kind: constant\n"
        "  signal: LONG\n"
        "data:\n"
        "  provider: fixture\n"
        "  dataset_id: ACCEPTANCE\n"
        "  instruments: [AAA]\n"
        "  periods: 8\n"
        "  seed: 19\n"
        "simulation:\n"
        "  initial_cash: 10000\n"
        "  order_quantity: 1\n",
        encoding="utf-8",
    )
    artifacts = tmp_path / "artifacts"
    assert main(["experiment", "run", "--config", str(config), "--artifacts", str(artifacts)]) == 0
    storage = FileStorage(artifacts)
    run = storage.read_json("experiments/EXP-ACCEPTANCE/run.json")
    assert isinstance(run, dict)
    assert run["experiment"]["id"] == "EXP-ACCEPTANCE"
    assert run["validation"]["experiment_id"] == "EXP-ACCEPTANCE"
    assert (
        main(["report", "show", "--experiment-id", "EXP-ACCEPTANCE", "--artifacts", str(artifacts)])
        == 0
    )
    assert (
        main(
            [
                "experiment",
                "rerun",
                "--experiment-id",
                "EXP-ACCEPTANCE",
                "--config",
                str(config),
                "--artifacts",
                str(artifacts),
            ]
        )
        == 0
    )
