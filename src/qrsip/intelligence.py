"""L6 research orchestration: run, reproduce, validate, and report experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qrsip.config import load_yaml_document
from qrsip.data.contract import P01DataContract
from qrsip.data.dataset import DatasetManifest, MarketDataset
from qrsip.data.fixtures import FixtureP01Provider, FixtureSpec
from qrsip.data.parquet import ParquetP01Adapter
from qrsip.domain.entities import (
    DatasetRef,
    Experiment,
    ExperimentRun,
    Hypothesis,
    ResearchQuestion,
    StrategySpec,
)
from qrsip.domain.results import ResearchReport
from qrsip.errors import ConfigurationError, QRSIPError, ReproducibilityError
from qrsip.infrastructure.storage import FileStorage, canonical_json_bytes, sha256_hex
from qrsip.quant.metrics import PerformanceMetrics, compute_performance_metrics, period_returns
from qrsip.quant.signals import ConstantStrategy, MovingAverageCrossStrategy, Signal, SignalStrategy
from qrsip.simulation.engine import SimulationConfig, SimulationResult, run_simulation
from qrsip.simulation.execution import CostModel
from qrsip.simulation.risk import RiskLimits
from qrsip.validation.robustness import ParameterPoint, WalkForwardFold
from qrsip.validation.runner import ValidationPolicy, ValidationRunner, ValidationSummary

__all__ = [
    "ExperimentComparison",
    "ExperimentSettings",
    "ResearchRun",
    "compare_experiment_runs",
    "load_experiment_settings",
    "render_markdown",
    "rerun_experiment",
    "run_experiment",
]


class CostSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    commission_bps: float = Field(default=0.0, ge=0.0)
    fixed_commission: float = Field(default=0.0, ge=0.0)
    slippage_bps: float = Field(default=0.0, ge=0.0)


class RiskSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_order_notional: float | None = Field(default=None, gt=0.0)
    max_position_notional: float | None = Field(default=None, gt=0.0)
    max_gross_exposure: float | None = Field(default=None, gt=0.0)
    max_drawdown: float | None = Field(default=None, gt=0.0)
    policy: Literal["REJECT", "FAIL_CLOSED"] = "REJECT"


class SimulationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_cash: float = Field(default=100_000.0, gt=0.0)
    order_quantity: float = Field(default=1.0, gt=0.0)
    allow_short: bool = False
    cost: CostSettings = Field(default_factory=CostSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)


class DataSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["fixture", "parquet"] = "fixture"
    dataset_id: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    instruments: tuple[str, ...] = ("FIXTURE-EQ",)
    start: datetime = Field(default_factory=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    periods: int = Field(default=504, ge=1)
    seed: int = 42
    path: str | None = None
    manifest_path: str | None = None

    @model_validator(mode="after")
    def _check_paths(self) -> DataSettings:
        if self.provider == "parquet" and (not self.path or not self.manifest_path):
            raise ValueError("parquet provider requires path and manifest_path")
        if self.provider == "fixture" and (self.path or self.manifest_path):
            raise ValueError("fixture provider does not accept path or manifest_path")
        if not self.instruments or len(set(self.instruments)) != len(self.instruments):
            raise ValueError("instruments must be non-empty and unique")
        if self.start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
        return self


class StrategySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["moving_average_cross", "constant"] = "moving_average_cross"
    fast: int = Field(default=20, ge=1)
    slow: int = Field(default=50, ge=1)
    signal: Literal["LONG", "SHORT", "FLAT"] = "LONG"

    @model_validator(mode="after")
    def _check_windows(self) -> StrategySettings:
        if self.kind == "moving_average_cross" and self.slow <= self.fast:
            raise ValueError("slow window must exceed fast window")
        return self


class ValidationSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    significance_level: float = Field(default=0.05, gt=0.0, lt=1.0)
    trials: int = Field(default=1, ge=1)
    periods_per_year: int = Field(default=252, ge=1)
    require_survivorship: bool = False
    require_sensitivity: bool = False
    require_walk_forward: bool = False
    p_values: dict[str, float] = Field(default_factory=dict)
    parameter_points: tuple[dict[str, Any], ...] = ()
    walk_forward_folds: tuple[dict[str, Any], ...] = ()

    @model_validator(mode="after")
    def _check_p_values(self) -> ValidationSettings:
        for name, value in self.p_values.items():
            if not name or not 0.0 <= value <= 1.0:
                raise ValueError("p_values must have names and values between zero and one")
        return self


class ExperimentSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    hypothesis: str = Field(..., min_length=1)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    data: DataSettings
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    seed: int = 42
    code_commit: str = "unknown"
    environment_id: str = "unknown"


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    left_experiment_id: str
    right_experiment_id: str
    metric_deltas: dict[str, float | None]
    validation_statuses: tuple[str, str]
    result_digests: tuple[str, str]
    datasets: tuple[str, str]

    def payload(self) -> dict[str, Any]:
        return {
            "left_experiment_id": self.left_experiment_id,
            "right_experiment_id": self.right_experiment_id,
            "metric_deltas": self.metric_deltas,
            "validation_statuses": list(self.validation_statuses),
            "result_digests": list(self.result_digests),
            "datasets": list(self.datasets),
        }


@dataclass(frozen=True, slots=True)
class ResearchRun:
    question: ResearchQuestion
    hypothesis: Hypothesis
    strategy: StrategySpec
    dataset_ref: DatasetRef
    experiment: Experiment
    run_record: ExperimentRun
    dataset: DatasetManifest
    metrics: PerformanceMetrics
    validation: ValidationSummary
    result: SimulationResult
    report: ResearchReport
    result_digest: str

    def payload(self) -> dict[str, Any]:
        return {
            "question": self.question.model_dump(mode="json"),
            "hypothesis": self.hypothesis.model_dump(mode="json"),
            "strategy": self.strategy.model_dump(mode="json"),
            "dataset_ref": self.dataset_ref.model_dump(mode="json"),
            "experiment": self.experiment.model_dump(mode="json"),
            "run_record": self.run_record.model_dump(mode="json"),
            "dataset": self.dataset.model_dump(mode="json"),
            "metrics": self.metrics.model_dump(mode="json"),
            "validation": self.validation.model_dump(mode="json"),
            "result": _simulation_payload(self.result),
            "report": self.report.model_dump(mode="json"),
            "result_digest": self.result_digest,
        }


def load_experiment_settings(path: Path) -> ExperimentSettings:
    """Load and validate a YAML experiment definition."""
    try:
        payload = load_yaml_document(path)
        return ExperimentSettings.model_validate(payload)
    except ValueError as exc:
        raise ConfigurationError(
            "invalid experiment configuration",
            path=str(path),
            reason=str(exc),
        ) from exc


def _load_dataset(
    settings: DataSettings, *, base_dir: Path
) -> tuple[MarketDataset, P01DataContract]:
    if settings.provider == "parquet":
        if settings.path is None or settings.manifest_path is None:
            raise QRSIPError("parquet settings are incomplete")
        adapter = ParquetP01Adapter(
            base_dir / settings.path,
            base_dir / settings.manifest_path,
        )
        handle, bars = adapter.load(settings.dataset_id, settings.version)
        return MarketDataset(handle, bars), adapter
    spec = FixtureSpec(
        dataset_id=settings.dataset_id,
        version=settings.version,
        instruments=settings.instruments,
        periods=settings.periods,
        start=settings.start,
        seed=settings.seed,
    )
    provider = FixtureP01Provider((spec,))
    handle, bars = provider.load(settings.dataset_id, settings.version)
    return MarketDataset(handle, bars), provider


def _make_strategy(settings: StrategySettings, *, allow_short: bool) -> SignalStrategy:
    if settings.kind == "constant":
        return ConstantStrategy(Signal[settings.signal])
    return MovingAverageCrossStrategy(
        fast=settings.fast,
        slow=settings.slow,
        allow_short=allow_short,
    )


def _make_simulation_config(settings: SimulationSettings) -> SimulationConfig:
    return SimulationConfig(
        initial_cash=settings.initial_cash,
        order_quantity=settings.order_quantity,
        allow_short=settings.allow_short,
        cost_model=CostModel(
            commission_bps=settings.cost.commission_bps,
            fixed_commission=settings.cost.fixed_commission,
            slippage_bps=settings.cost.slippage_bps,
        ),
        risk_limits=RiskLimits(
            max_order_notional=settings.risk.max_order_notional,
            max_position_notional=settings.risk.max_position_notional,
            max_gross_exposure=settings.risk.max_gross_exposure,
            max_drawdown=settings.risk.max_drawdown,
        ),
        risk_policy=settings.risk.policy,
    )


def _simulation_payload(result: SimulationResult) -> dict[str, Any]:
    return {
        "equity_curve": [asdict(point) for point in result.equity_curve],
        "fills": [asdict(item) for item in result.fills],
        "rejections": [asdict(item) for item in result.rejections],
        "halt": asdict(result.halt) if result.halt is not None else None,
        "final_portfolio": asdict(result.final_portfolio),
        "halted": result.halted,
        "config": asdict(result.config),
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "dataset_checksum": result.dataset_checksum,
        "is_fixture": result.is_fixture,
        "limitations": result.limitations,
        "bar_count": result.bar_count,
        "instrument_count": result.instrument_count,
    }


def _validation_inputs(
    settings: ValidationSettings,
) -> tuple[tuple[ParameterPoint, ...], tuple[WalkForwardFold, ...]]:
    points = tuple(ParameterPoint(**point) for point in settings.parameter_points)
    folds = tuple(WalkForwardFold(**fold) for fold in settings.walk_forward_folds)
    return points, folds


def _build_entities(
    settings: ExperimentSettings,
    dataset: DatasetManifest,
    config: dict[str, Any],
) -> tuple[ResearchQuestion, Hypothesis, StrategySpec, DatasetRef, Experiment]:
    created_at = dataset.coverage_start or datetime(1970, 1, 1, tzinfo=UTC)
    question = ResearchQuestion(
        id=f"RQ-{settings.id}",
        title=settings.question,
        created_at=created_at,
        updated_at=created_at,
    )
    hypothesis = Hypothesis(
        id=f"HYP-{settings.id}",
        question_id=question.id,
        null_hypothesis=settings.hypothesis,
        alternative_hypothesis=settings.hypothesis,
        created_at=created_at,
        updated_at=created_at,
    )
    strategy = StrategySpec(
        id=f"STR-{settings.id}",
        entry_rules=f"{settings.strategy.kind}:{settings.strategy.signal}",
        exit_rules="target state change",
        signal_timing="bar_close_T_to_next_open_Tplus1",
        cost_assumptions=settings.simulation.cost.model_dump(),
        risk_limits=settings.simulation.risk.model_dump(),
        created_at=created_at,
        updated_at=created_at,
    )
    dataset_ref = DatasetRef(
        id=dataset.dataset_id,
        source=dataset.source,
        source_version=dataset.source_version,
        coverage_start=dataset.coverage_start,
        coverage_end=dataset.coverage_end,
        instruments=list(dataset.instruments),
        frequency=dataset.frequency,
        timezone=dataset.timezone,
        schema_version=dataset.schema_version,
        checksum=dataset.checksum,
        created_at=created_at,
        updated_at=created_at,
    )
    experiment = Experiment(
        id=settings.id,
        hypothesis_id=hypothesis.id,
        strategy_id=strategy.id,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.version,
        dataset_checksum=dataset.checksum,
        code_commit=settings.code_commit,
        environment_id=settings.environment_id,
        config=config,
        seed=settings.seed,
        execution_model="deterministic_bar_close_next_open",
        cost_model=settings.simulation.cost.model_dump_json(),
        risk_model=settings.simulation.risk.model_dump_json(),
        created_at=created_at,
        updated_at=created_at,
    )
    return question, hypothesis, strategy, dataset_ref, experiment


def _make_report(
    experiment: Experiment,
    question: ResearchQuestion,
    hypothesis: Hypothesis,
    strategy: StrategySpec,
    dataset_ref: DatasetRef,
    dataset: DatasetManifest,
    metrics: PerformanceMetrics,
    validation: ValidationSummary,
) -> ResearchReport:
    return ResearchReport(
        id=f"REP-{experiment.id}",
        experiment_id=experiment.id,
        observed=[
            f"question={question.id}: {question.title}",
            f"hypothesis={hypothesis.id}: {hypothesis.alternative_hypothesis}",
            f"strategy={strategy.id}: {strategy.entry_rules}",
            f"dataset_reference={dataset_ref.id} ({dataset_ref.checksum})",
            f"dataset={dataset.identity_line()}",
            f"total_return={metrics.total_return:.12g}",
            f"sharpe={metrics.sharpe if metrics.sharpe is not None else 'UNDEFINED'}",
            f"validation={validation.overall_status.value}",
        ],
        inference=["Observed evidence only; no automated research conclusion or promotion."],
        assumptions=["Simulation uses the recorded cost, risk, dataset, and seed configuration."],
        limitations=list(dataset.limitations),
        human_decision="PENDING",
        created_at=dataset.coverage_start or datetime(1970, 1, 1, tzinfo=UTC),
        updated_at=dataset.coverage_start or datetime(1970, 1, 1, tzinfo=UTC),
    )


def _digest(payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(payload))


def run_experiment(
    settings: ExperimentSettings,
    *,
    base_dir: Path | None = None,
    storage: FileStorage | None = None,
) -> ResearchRun:
    """Run one deterministic experiment and optionally persist canonical artifacts."""
    base_dir = base_dir or Path.cwd()
    config = settings.model_dump(mode="json")
    dataset, _provider = _load_dataset(settings.data, base_dir=base_dir)
    manifest = DatasetManifest.from_dataset(dataset)
    created_at = manifest.coverage_start or dataset.start
    executable_strategy = _make_strategy(
        settings.strategy, allow_short=settings.simulation.allow_short
    )
    simulation_config = _make_simulation_config(settings.simulation)
    result = run_simulation(
        dataset,
        dict.fromkeys(dataset.instruments, executable_strategy),
        simulation_config,
    )
    equity = [point.equity for point in result.equity_curve]
    metrics = compute_performance_metrics(
        equity,
        periods_per_year=settings.validation.periods_per_year,
        trade_pnls=[item.realized_pnl for item in result.fills if item.realized_pnl != 0.0],
    )
    returns = period_returns(equity)
    observed_sharpe = metrics.sharpe if metrics.sharpe is not None else 0.0
    points, folds = _validation_inputs(settings.validation)
    validation = ValidationRunner(
        ValidationPolicy(
            significance_level=settings.validation.significance_level,
            trials=settings.validation.trials,
            periods_per_year=settings.validation.periods_per_year,
            require_survivorship=settings.validation.require_survivorship,
            require_sensitivity=settings.validation.require_sensitivity,
            require_walk_forward=settings.validation.require_walk_forward,
        )
    ).run(
        experiment_id=settings.id,
        result=result,
        dataset=dataset,
        returns=returns,
        observed_sharpe=observed_sharpe,
        p_values=settings.validation.p_values,
        sensitivity_points=points,
        walk_forward_folds=folds,
    )
    question, hypothesis, strategy, dataset_ref, experiment = _build_entities(
        settings, manifest, config
    )
    run_record = ExperimentRun(
        id=f"RUN-{settings.id}-001",
        experiment_id=settings.id,
        seed=settings.seed,
        code_commit=settings.code_commit,
        config_snapshot=config,
        status="COMPLETED",
        metrics={
            key: value
            for key, value in metrics.model_dump(mode="json").items()
            if value is not None
        },
        created_at=created_at,
        updated_at=created_at,
    )
    report = _make_report(
        experiment, question, hypothesis, strategy, dataset_ref, manifest, metrics, validation
    )
    core = {
        "question": question.model_dump(mode="json"),
        "hypothesis": hypothesis.model_dump(mode="json"),
        "strategy": strategy.model_dump(mode="json"),
        "dataset_ref": dataset_ref.model_dump(mode="json"),
        "experiment": experiment.model_dump(mode="json"),
        "run_record": run_record.model_dump(mode="json"),
        "dataset": manifest.model_dump(mode="json"),
        "metrics": metrics.model_dump(mode="json"),
        "validation": validation.model_dump(mode="json"),
        "result": _simulation_payload(result),
        "report": report.model_dump(mode="json"),
    }
    run = ResearchRun(
        question=question,
        hypothesis=hypothesis,
        strategy=strategy,
        dataset_ref=dataset_ref,
        experiment=experiment,
        run_record=run_record,
        dataset=manifest,
        metrics=metrics,
        validation=validation,
        result=result,
        report=report,
        result_digest=_digest(core),
    )
    if storage is not None:
        storage.write_json(f"experiments/{settings.id}/run.json", run.payload())
        storage.write_text(f"experiments/{settings.id}/report.md", render_markdown(run))
    return run


def compare_experiment_runs(left: ResearchRun, right: ResearchRun) -> ExperimentComparison:
    """Compare two recorded runs without drawing trading or promotion conclusions."""
    left_metrics = left.metrics.model_dump(mode="json")
    right_metrics = right.metrics.model_dump(mode="json")
    deltas: dict[str, float | None] = {}
    for name in sorted(set(left_metrics) | set(right_metrics)):
        left_value = left_metrics.get(name)
        right_value = right_metrics.get(name)
        if left_value is None or right_value is None:
            deltas[name] = None
        else:
            deltas[name] = right_value - left_value
    return ExperimentComparison(
        left_experiment_id=left.experiment.id,
        right_experiment_id=right.experiment.id,
        metric_deltas=deltas,
        validation_statuses=(
            left.validation.overall_status.value,
            right.validation.overall_status.value,
        ),
        result_digests=(left.result_digest, right.result_digest),
        datasets=(
            f"{left.dataset.dataset_id}@{left.dataset.version}#{left.dataset.checksum}",
            f"{right.dataset.dataset_id}@{right.dataset.version}#{right.dataset.checksum}",
        ),
    )


def render_markdown(run: ResearchRun) -> str:
    """Render a deterministic, evidence-only research report."""
    lines = [
        f"# Research Report: {run.experiment.id}",
        "",
        "## Status",
        "- Human decision: PENDING",
        f"- Validation: {run.validation.overall_status.value}",
        "",
        "## Observed",
    ]
    lines.extend(f"- {item}" for item in run.report.observed)
    lines.extend(["", "## Inference"])
    lines.extend(f"- {item}" for item in run.report.inference)
    lines.extend(["", "## Assumptions"])
    lines.extend(f"- {item}" for item in run.report.assumptions)
    lines.extend(["", "## Limitations"])
    lines.extend(
        f"- {item}" for item in run.report.limitations or ("No additional limitations recorded.",)
    )
    return "\n".join(lines) + "\n"


def rerun_experiment(
    settings: ExperimentSettings,
    *,
    base_dir: Path | None = None,
    storage: FileStorage,
) -> ResearchRun:
    """Rerun a recorded experiment and fail if its canonical digest changes."""
    original = storage.read_json(f"experiments/{settings.id}/run.json")
    if not isinstance(original, dict):
        raise ReproducibilityError("stored experiment artifact is not a JSON object")
    replay = run_experiment(settings, base_dir=base_dir)
    if replay.result_digest != original.get("result_digest"):
        raise ReproducibilityError(
            "experiment reproduction digest mismatch",
            experiment_id=settings.id,
            expected=original.get("result_digest"),
            actual=replay.result_digest,
        )
    return replay
