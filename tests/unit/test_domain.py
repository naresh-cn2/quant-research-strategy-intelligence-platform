"""
Tests for qrsip.domain — entities, lifecycle (spec §13-14, FR-001..FR-005).
"""

from __future__ import annotations

import itertools
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from qrsip.domain import (
    TERMINAL_STATES,
    BaseEntity,
    DatasetRef,
    Experiment,
    ExperimentRun,
    Hypothesis,
    LifecycleViolation,
    PromotionDecision,
    RegistryError,
    ResearchLifecycleState,
    ResearchQuestion,
    ResearchRegistry,
    ResearchReport,
    StrategySpec,
    ValidationResult,
    allowed_transitions,
    can_transition,
    require_transition,
)
from qrsip.domain.registry import _kind_of
from qrsip.errors import QRSIPError
from qrsip.infrastructure.storage import (
    FileStorage,
    StorageError,
    canonical_json_bytes,
    sha256_hex,
)


def _question(**overrides: object) -> ResearchQuestion:
    payload: dict[str, object] = {"id": "RQ-001", "title": "Does momentum persist?"}
    payload.update(overrides)
    return ResearchQuestion(**payload)  # type: ignore[arg-type]


def _hypothesis(**overrides: object) -> Hypothesis:
    payload: dict[str, object] = {
        "id": "HYP-001",
        "question_id": "RQ-001",
        "null_hypothesis": "Momentum has no predictive power",
        "alternative_hypothesis": "Momentum predicts forward returns",
    }
    payload.update(overrides)
    return Hypothesis(**payload)  # type: ignore[arg-type]


def _strategy(**overrides: object) -> StrategySpec:
    payload: dict[str, object] = {
        "id": "STR-001",
        "entry_rules": "fast SMA crosses above slow SMA",
        "exit_rules": "fast SMA crosses below slow SMA",
    }
    payload.update(overrides)
    return StrategySpec(**payload)  # type: ignore[arg-type]


def _experiment(**overrides: object) -> Experiment:
    payload: dict[str, object] = {
        "id": "EXP-001",
        "hypothesis_id": "HYP-001",
        "strategy_id": "STR-001",
        "dataset_id": "DS-001",
    }
    payload.update(overrides)
    return Experiment(**payload)  # type: ignore[arg-type]


ALL_ENTITY_SAMPLES: tuple[BaseEntity, ...] = (
    _question(),
    _hypothesis(),
    _strategy(),
    DatasetRef(id="DS-001", source="p01"),
    _experiment(),
    ExperimentRun(id="RUN-001", experiment_id="EXP-001"),
    ValidationResult(id="VAL-001", experiment_id="EXP-001", check="lookahead"),
    PromotionDecision(id="PRO-001", experiment_id="EXP-001"),
    ResearchReport(id="REP-001", experiment_id="EXP-001"),
)


class TestBaseEntity:
    def test_identity_defaults(self) -> None:
        entity = _question()
        assert entity.id == "RQ-001"
        assert entity.version == "1.0.0"
        assert entity.created_at.tzinfo is not None
        assert entity.updated_at.tzinfo is not None

    def test_entity_is_frozen(self) -> None:
        entity = _question()
        with pytest.raises(ValidationError):
            entity.id = "RQ-002"  # type: ignore[misc]

    def test_entity_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            _question(bogus_field=1)  # type: ignore[call-arg]

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ResearchQuestion(id="", title="x")

    def test_all_entity_samples_share_contract(self) -> None:
        ids = [entity.id for entity in ALL_ENTITY_SAMPLES]
        assert len(ids) == len(set(ids))
        for entity in ALL_ENTITY_SAMPLES:
            assert isinstance(entity, BaseEntity)
            assert entity.version == "1.0.0"
            assert entity.created_at <= datetime.now(UTC)


class TestLifecycle:
    def test_full_chain_is_walkable(self) -> None:
        chain = [
            ResearchLifecycleState.DRAFT,
            ResearchLifecycleState.SPECIFIED,
            ResearchLifecycleState.DATA_READY,
            ResearchLifecycleState.IMPLEMENTED,
            ResearchLifecycleState.TESTED,
            ResearchLifecycleState.BACKTESTED,
            ResearchLifecycleState.VALIDATED,
            ResearchLifecycleState.ROBUSTNESS_TESTED,
            ResearchLifecycleState.REVIEWED,
        ]
        for current, target in itertools.pairwise(chain):
            assert can_transition(current, target), f"{current} -> {target} must be legal"
            require_transition(current, target)  # must not raise

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (ResearchLifecycleState.DRAFT, frozenset({ResearchLifecycleState.SPECIFIED})),
            (
                ResearchLifecycleState.REVIEWED,
                frozenset(
                    {
                        ResearchLifecycleState.REJECTED,
                        ResearchLifecycleState.INVESTIGATE,
                        ResearchLifecycleState.PROMOTION_CANDIDATE,
                    }
                ),
            ),
            (ResearchLifecycleState.REJECTED, frozenset()),
            (ResearchLifecycleState.INVESTIGATE, frozenset()),
            (ResearchLifecycleState.PROMOTION_CANDIDATE, frozenset()),
        ],
    )
    def test_allowed_transitions(
        self,
        state: ResearchLifecycleState,
        expected: frozenset[ResearchLifecycleState],
    ) -> None:
        assert allowed_transitions(state) == expected

    def test_skip_is_forbidden(self) -> None:
        assert not can_transition(ResearchLifecycleState.DRAFT, ResearchLifecycleState.TESTED)
        with pytest.raises(LifecycleViolation) as excinfo:
            require_transition(ResearchLifecycleState.DRAFT, ResearchLifecycleState.TESTED)
        assert excinfo.value.context["current"] == "DRAFT"
        assert excinfo.value.context["target"] == "TESTED"
        assert excinfo.value.context["allowed"] == ["SPECIFIED"]

    def test_reverse_is_forbidden(self) -> None:
        with pytest.raises(LifecycleViolation):
            require_transition(ResearchLifecycleState.TESTED, ResearchLifecycleState.IMPLEMENTED)

    def test_noop_is_forbidden(self) -> None:
        with pytest.raises(LifecycleViolation):
            require_transition(ResearchLifecycleState.DRAFT, ResearchLifecycleState.DRAFT)

    @pytest.mark.parametrize(
        "terminal",
        [
            ResearchLifecycleState.REJECTED,
            ResearchLifecycleState.INVESTIGATE,
            ResearchLifecycleState.PROMOTION_CANDIDATE,
        ],
    )
    def test_terminal_states_have_no_exits(self, terminal: ResearchLifecycleState) -> None:
        assert allowed_transitions(terminal) == frozenset()
        with pytest.raises(LifecycleViolation):
            require_transition(terminal, ResearchLifecycleState.DRAFT)

    def test_terminal_set_contents(self) -> None:
        assert (
            frozenset(
                {
                    ResearchLifecycleState.REJECTED,
                    ResearchLifecycleState.INVESTIGATE,
                    ResearchLifecycleState.PROMOTION_CANDIDATE,
                }
            )
            == TERMINAL_STATES
        )

    def test_every_state_has_allowed_entry(self) -> None:
        for state in ResearchLifecycleState:
            allowed_transitions(state)  # must not KeyError


class TestEntityStatusAndTiming:
    def test_question_defaults_to_draft(self) -> None:
        assert _question().status is ResearchLifecycleState.DRAFT

    def test_experiment_status_transition_guard(self) -> None:
        exp = _experiment(status=ResearchLifecycleState.BACKTESTED)
        assert can_transition(exp.status, ResearchLifecycleState.VALIDATED)
        with pytest.raises(LifecycleViolation):
            require_transition(exp.status, ResearchLifecycleState.REVIEWED)

    def test_strategy_spec_signal_timing_default_matches_adr0005(self) -> None:
        assert _strategy().signal_timing == "bar_close_T_to_next_open_Tplus1"


# ---------------------------------------------------------------------------
# Storage contracts (ADR-0002) — the registry depends on these
# ---------------------------------------------------------------------------


class TestStoragePort:
    def test_write_read_roundtrip(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        digest = storage.write_bytes("a/b.json", b"hello")
        assert digest == sha256_hex(b"hello")
        assert storage.read_bytes("a/b.json") == b"hello"
        assert storage.exists("a/b.json")

    def test_read_missing_fails_closed(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        with pytest.raises(StorageError):
            storage.read_bytes("missing.json")

    @pytest.mark.parametrize(
        "bad_key",
        ["/etc/passwd", "../escape", "a\\b", "a/../b", "", "~/.ssh/id_rsa"],
    )
    def test_unsafe_keys_rejected(self, tmp_path: Path, bad_key: str) -> None:
        storage = FileStorage(tmp_path)
        with pytest.raises(StorageError):
            storage.write_bytes(bad_key, b"x")

    def test_list_keys_is_sorted_and_filtered(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        storage.write_bytes("z/2.json", b"2")
        storage.write_bytes("z/1.json", b"1")
        storage.write_bytes("other/0.json", b"0")
        assert storage.list_keys() == ["other/0.json", "z/1.json", "z/2.json"]
        assert storage.list_keys("z/") == ["z/1.json", "z/2.json"]

    def test_describe_reports_identity(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        storage.write_bytes("k.json", b"payload")
        info = storage.describe("k.json")
        assert info["size_bytes"] == len(b"payload")
        assert info["sha256"] == sha256_hex(b"payload")

    def test_json_roundtrip(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        storage.write_json("x.json", {"b": 1, "a": [1, 2]})
        assert storage.read_json("x.json") == {"a": [1, 2], "b": 1}

    def test_malformed_json_fails_closed(self, tmp_path: Path) -> None:
        storage = FileStorage(tmp_path)
        storage.write_bytes("bad.json", b"{not json")
        with pytest.raises(StorageError):
            storage.read_json("bad.json")


class TestCanonicalJson:
    def test_key_order_is_canonical(self) -> None:
        assert canonical_json_bytes({"b": 1, "a": 2}) == canonical_json_bytes({"a": 2, "b": 1})

    def test_single_trailing_newline(self) -> None:
        payload = canonical_json_bytes({"a": 1})
        assert payload.endswith(b"}\n")
        assert not payload.endswith(b"\n\n")

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError):
            canonical_json_bytes({"a": math.nan})

    def test_known_sha256(self) -> None:
        assert sha256_hex(b"abc") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )


# ---------------------------------------------------------------------------
# ResearchRegistry
# ---------------------------------------------------------------------------


class TestResearchRegistry:
    def test_put_get_roundtrip(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        question = _question()
        key = registry.put(question)
        assert key.endswith("research_questions/RQ-001/1.0.0.json")
        assert registry.get(ResearchQuestion, "RQ-001", "1.0.0") == question

    def test_put_same_content_is_idempotent(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        question = _question()
        assert registry.put(question) == registry.put(question)

    def test_equal_logical_entity_with_new_timestamp_conflicts(self, tmp_path: Path) -> None:
        # Two separately-constructed entities differ only in created_at; the
        # registry compares resolved bytes, so this must conflict (fail closed)
        # rather than silently rewriting history.
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question())
        with pytest.raises(RegistryError):
            registry.put(_question())

    def test_conflicting_content_fails_closed(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question())
        with pytest.raises(RegistryError) as excinfo:
            registry.put(_question(title="A different question entirely"))
        assert excinfo.value.context["entity_id"] == "RQ-001"

    def test_overwrite_allows_explicit_revision(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question())
        registry.put(_question(title="Revised title"), overwrite=True)
        assert registry.get(ResearchQuestion, "RQ-001", "1.0.0").title == "Revised title"

    def test_get_missing_fails_closed(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        with pytest.raises(RegistryError):
            registry.get(ResearchQuestion, "NOPE", "1.0.0")

    def test_unsafe_ids_rejected(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        with pytest.raises(RegistryError):
            registry.put(_question(id="../evil"))
        with pytest.raises(RegistryError):
            registry.get(ResearchQuestion, "a/b", "1.0.0")

    def test_versions_accumulate_and_list_sorted(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        for version in ("1.0.0", "0.9.0", "1.10.0"):
            registry.put(_question(version=version))
        assert registry.list_versions(ResearchQuestion, "RQ-001") == ["0.9.0", "1.0.0", "1.10.0"]

    def test_list_ids_sorted(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question(id="RQ-B", title="b"))
        registry.put(_question(id="RQ-A", title="a"))
        registry.put(_hypothesis(id="HYP-Z"))
        assert registry.list_ids(ResearchQuestion) == ["RQ-A", "RQ-B"]
        assert registry.list_ids(Hypothesis) == ["HYP-Z"]

    def test_list_all_is_deterministic_and_typed(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question(id="RQ-B", title="b"))
        registry.put(_question(id="RQ-A", title="a"))
        registry.put(_hypothesis())
        first = registry.list_all(ResearchQuestion)
        assert [entity.id for entity in first] == ["RQ-A", "RQ-B"]
        assert first == registry.list_all(ResearchQuestion)
        assert all(isinstance(entity, ResearchQuestion) for entity in first)

    @pytest.mark.parametrize(
        ("entity_cls", "directory"),
        [
            (ResearchQuestion, "research_questions"),
            (Hypothesis, "hypotheses"),
            (StrategySpec, "strategies"),
            (DatasetRef, "datasets"),
            (Experiment, "experiments"),
            (ExperimentRun, "experiment_runs"),
            (ValidationResult, "validation_results"),
            (ResearchReport, "reports"),
            (PromotionDecision, "promotion_decisions"),
        ],
    )
    def test_kind_directory_mapping(self, entity_cls: type[BaseEntity], directory: str) -> None:
        assert _kind_of(entity_cls) == directory

    def test_entity_kinds_are_isolated(self, tmp_path: Path) -> None:
        registry = ResearchRegistry(FileStorage(tmp_path))
        registry.put(_question(id="SAME"))
        registry.put(_hypothesis(id="SAME"))
        assert registry.get(ResearchQuestion, "SAME", "1.0.0").id == "SAME"
        assert registry.get(Hypothesis, "SAME", "1.0.0").question_id == "RQ-001"
        with pytest.raises(RegistryError):
            registry.get(StrategySpec, "SAME", "1.0.0")

    def test_registry_error_is_qrsip_error(self) -> None:
        assert issubclass(RegistryError, QRSIPError)
