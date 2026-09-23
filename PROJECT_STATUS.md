# QRSIP — PROJECT_STATUS.md
#
# This is the operational source of truth for the P02 implementation.
# It is continuously updated to reflect actual code, tests, and git state.
#
# Do not claim completion without evidence. See spec §35.

# P02 — Quantitative Research & Strategy Intelligence Platform
# ============================================================

**Status:** IN PROGRESS — NOT COMPLETE (Phases 0–3 Complete & Tested; Phase 4 & 5 WIP)

**Current Phase:** Phase 4 (Simulation) & Phase 5 (Validation) — In Progress

**Last Verified Commit:** `bd890d3` ("Phase 3: L3 quant layer — causal features, deterministic signals, fail-closed metrics")

**Last Verification Timestamp:** 2026-09-23

---

## 1. Architectural Layer Status Matrix

| Layer | Component | Status | Test Status | Notes / Limitations |
|---|---|---|---|---|
| **L0 Infrastructure** | Error Model (`errors.py`) | **Implemented** | **Tested** (14 tests) | 12-class fail-closed hierarchy with structured diagnostic context |
| | Configuration (`config.py`) | **Implemented** | **Tested** (31 tests) | YAML loader, env overrides (`QRSIP_*`), path resolution, sanitization |
| | Structured Logging (`logging.py`) | **Implemented** | **Tested** (11 tests) | JSON structured formatter + human console output, `timed_event` |
| | System Diagnostics (`doctor.py`) | **Implemented** | **Tested** (14 tests) | Non-destructive health checks (`qrsip doctor`) |
| | Storage Port (`storage.py`) | **Implemented** | **Tested** (part of domain) | `StoragePort` protocol + `FileStorage` with SHA-256 canonical JSON |
| | Database (PostgreSQL) | **Deferred** | N/A | Deferred per ADR-0002 until registry/lineage scale requires it |
| **L1 Domain** | Base Entity (`base.py`) | **Implemented** | **Tested** (part of domain) | Immutable Pydantic v2 `BaseEntity` with stable ID, version, UTC stamps |
| | Research Entities (`entities.py`) | **Implemented** | **Tested** (part of domain) | `ResearchQuestion`, `Hypothesis`, `StrategySpec`, `DatasetRef`, `Experiment`, `ExperimentRun` |
| | Research Lifecycle (`lifecycle.py`) | **Implemented** | **Tested** (part of domain) | 12-state state machine; transition validator (`require_transition`) fails closed |
| | Entity Registry (`registry.py`) | **Implemented** | **Tested** (part of domain) | Append-only persistence backed by `StoragePort`, SHA-256 conflict detection |
| | Results & Promotion (`results.py`) | **Implemented** | **Tested** (part of domain) | `ValidationResult`, `PromotionDecision` (mandatory human gate), `ResearchReport` |
| **L2 Data** | P01 Data Contract (`contract.py`) | **Implemented** | **Tested** (part of data) | `Bar` dataclass (close-timestamped in UTC), `P01DataContract` protocol |
| | Bar Validation (`validation.py`) | **Implemented** | **Tested** (part of data) | Fail-closed OHLC, ordering, duplicate, and non-negative validators |
| | Point-in-Time Access (`dataset.py`) | **Implemented** | **Tested** (part of data) | `MarketDataset` + `PointInTimeView`; raises `LookAheadError` on future access |
| | Deterministic Fixtures (`fixtures.py`)| **Implemented** | **Tested** (part of data) | `FixtureP01Provider` generating reproducible multi-instrument bar sets |
| | Parquet/Arrow Dataset Loader | **Partial** | N/A | In-memory bar fixtures complete; disk-based Parquet reader pending |
| **L3 Quant** | Causal Features (`features.py`) | **Implemented** | **Tested** (part of quant) | SMA, EMA, simple/log returns, rolling volatility, momentum; warm-up is `None` |
| | Strategy Signals (`signals.py`) | **Implemented** | **Tested** (part of quant) | `SignalStrategy` protocol, `MovingAverageCrossStrategy`, `ConstantStrategy` |
| | Financial Metrics (`metrics.py`) | **Implemented** | **Tested** (part of quant) | Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Profit Factor, `PerformanceMetrics` |
| **L4 Simulation** | Execution Model (`execution.py`) | **WIP (untracked)** | **Missing** | Orders, fills at next-bar open $T+1$ (ADR-0005), commission + slippage cost model |
| | Portfolio Accounting (`portfolio.py`)| **WIP (untracked)** | **Missing** | Double-entry accounting, verified equity invariant; unmarked valuation fails closed |
| | Risk Engine (`risk.py`) | **WIP (untracked)** | **Missing** | Pre-trade order limits (notional, position, gross exposure), drawdown circuit breaker |
| | Event-Loop Engine (`engine.py`) | **Missing** | **Missing** | `run_simulation` deterministic loop connecting dataset, signals, risk, execution, portfolio |
| | Module Entrypoint (`__init__.py`) | **Broken** | **Missing** | Contains invalid import (`qrsip.dirty_exec`) and references unauthored `engine.py` |
| **L5 Validation** | Validation Math (`stats.py`) | **WIP (untracked)** | **Missing** | t-statistic, normal approximation p-value, skewness, kurtosis, Deflated Sharpe Ratio |
| | Validation Runner & Bias Checks | **Missing** | **Missing** | Look-ahead bias verification, multiple-testing correction, survivorship check |
| | Robustness Suite | **Missing** | **Missing** | Parameter sensitivity grid, walk-forward analysis, perturbation testing |
| **L6 Intelligence** | Research Report Generator | **Partial** | **Missing** | Domain entities defined in `results.py`; Markdown/JSON report synthesis engine missing |
| | Experiment Comparison / Diffing | **Missing** | **Missing** | Lineage and comparison engine across runs not yet implemented |
| | AI Copilot / Assistant | **Deferred** | N/A | Deferred per architecture spec until deterministic foundations are complete |
| **L7 Presentation** | CLI Skeleton (`cli.py`) | **Implemented** | **Tested** (10 tests) | `qrsip init`, `qrsip doctor`, `qrsip status` |
| | Research CLI Commands | **Missing** | **Missing** | `qrsip experiment run`, `qrsip experiment rerun`, `qrsip report show`, `qrsip promote` |
| | FastAPI REST API | **Deferred** | N/A | Deferred per ADR-0003 until an external HTTP consumer requires it |
| | Dashboard UI | **Excluded** | N/A | Explicitly out of scope for P02 (spec §4.1, §47) |

---

## 2. Test Suite & Verification Status

* **Total Automated Tests Passing:** **272** (in 1.54s via Python 3.12 / pytest 8.4.2)
* **Unit Test Breakdown by Suite:**
  * `tests/unit/test_cli.py`: 10 passed
  * `tests/unit/test_config.py`: 31 passed
  * `tests/unit/test_data.py`: 67 passed
  * `tests/unit/test_doctor.py`: 14 passed
  * `tests/unit/test_domain.py`: 59 passed
  * `tests/unit/test_errors.py`: 16 passed
  * `tests/unit/test_logging.py`: 11 passed
  * `tests/unit/test_quant.py`: 64 passed
* **Higher-Order Test Suites (Status: SKELETON ONLY — 0 tests written yet):**
  * `tests/contract/`: SKELETON (only `README.md`)
  * `tests/property/`: SKELETON (only `README.md`)
  * `tests/adversarial/`: SKELETON (only `README.md`)
  * `tests/integration/`: SKELETON (only `README.md`)
  * `tests/acceptance/`: SKELETON (only `README.md`)
  * `tests/regression/`: SKELETON (only `README.md`)
* **Linter & Formatter Status:**
  * `ruff check src tests`: Clean (0 errors) on committed files.
  * `ruff format --check src tests`: 2 untracked files (`simulation/portfolio.py`, `simulation/risk.py`) need formatting.
* **Type Checking Status:**
  * `mypy src`: Passing on all committed code (19 source files).
  * 3 errors currently reported on untracked WIP files:
    1. `src/qrsip/validation/stats.py:79`: `Returning Any from function declared to return "float"` (type annotation on fractional power).
    2. `src/qrsip/simulation/__init__.py:19`: `Cannot find implementation or library stub for module named "qrsip.dirty_exec"`.
    3. `src/qrsip/simulation/__init__.py:20`: `Cannot find implementation or library stub for module named "qrsip.simulation.engine"`.
* **Security Audit Status:**
  * `bandit -r src -c pyproject.toml -ll`: Passing (0 medium/high issues across 3,503 LOC).

---

## 3. Explicit Inventory of Current Work-in-Progress (WIP)

### L4 Simulation Layer (`src/qrsip/simulation/` — untracked in working directory)
1. `src/qrsip/simulation/execution.py` (215 LOC): Implemented orders, next-bar open fills (ADR-0005), and explicit cost model (commissions + embedded slippage). Untracked.
2. `src/qrsip/simulation/portfolio.py` (245 LOC): Implemented cash-first double-entry accounting enforcing the verified equity invariant ($\text{equity} = \text{cash} + \text{realized} + \text{unrealized} - \text{commissions}$). Untracked.
3. `src/qrsip/simulation/risk.py` (202 LOC): Implemented pre-trade limit checks and peak-to-trough drawdown circuit breaker. Untracked.
4. `src/qrsip/simulation/engine.py`: **MISSING**. The event loop orchestrating `MarketDataset` $\to$ `PointInTimeView` $\to$ `SignalStrategy` $\to$ `RiskEngine` $\to$ `CostModel` $\to$ `Portfolio` into a `SimulationResult` has not yet been authored.
5. `src/qrsip/simulation/__init__.py`: **DEFECTIVE**. Contains a broken import (`from qrsip.dirty_exec import DummyBacktestEngine`) and attempts to export missing symbols from `qrsip.simulation.engine`.
6. `tests/unit/test_simulation.py`: **MISSING**. Unit and property tests for simulation layer are not yet written.

### L5 Validation Layer (`src/qrsip/validation/` — untracked in working directory)
1. `src/qrsip/validation/stats.py` (149 LOC): Statistical significance math implemented (t-stat, normal approximation p-value, skewness, excess kurtosis, expected max normal, Deflated Sharpe Ratio). Untracked.
2. `src/qrsip/validation/__init__.py` (30 LOC): Exports statistical functions. Clean import. Untracked.
3. Known type defect: line 79 of `stats.py` returns `Any` from `m3 / (m2**1.5)` in strict mypy.
4. `tests/unit/test_validation.py`: **MISSING**. Validation tests not yet written.
5. Bias checks and walk-forward robustness engine: **MISSING**.

### L6 Intelligence & L7 Presentation
1. Research report generation engine: **MISSING** (entities defined in `domain/results.py`, but generator logic is unwritten).
2. Experiment run CLI subcommands (`qrsip experiment run`, `qrsip experiment rerun`): **MISSING**.

---

## 4. Acceptance Criteria & Quality Gates Still Outstanding

Per spec §50, the platform is considered **working** only when all of the following hold:
- [x] Source code exists and architecture is implemented (L0–L3 complete, L4–L5 in progress)
- [x] Storage contracts work (`StoragePort` + `FileStorage` verified with SHA-256 canonical JSON)
- [x] P01 data contract works (enforced via `P01DataContract` and `PointInTimeView`)
- [ ] Strategy execution works (L4 event loop `engine.py` pending)
- [ ] Portfolio accounting is verified by unit/property tests (code written, tests pending)
- [ ] Risk engine is verified by unit/property tests (code written, tests pending)
- [x] Metrics are tested (272 unit tests passing, covering quant metrics, features, signals)
- [ ] Bias checks work (lookahead / multiple testing checks pending)
- [ ] Adversarial tests work (`tests/adversarial/` empty)
- [ ] Reproduction works (automated reproduction verification command pending)
- [x] CI is configured (`.github/workflows/ci.yml`, `security.yml` exist)
- [x] Documentation matches reality (updated via this synchronization)
- [ ] Fresh-environment acceptance test passes (end-to-end acceptance run in clean container pending)

---

## 5. Architectural Principles Preserved

* **Fail-Closed**: If required data, configuration, marks, or risk checks are missing, the system raises an explicit `QRSIPError` with structured context rather than inventing a default or fabricating prices.
* **Point-in-Time Safety**: Strict causality enforced in `PointInTimeView`. Accessing bars past the decision timestamp raises `LookAheadError`.
* **Deterministic Execution (ADR-0005)**: Decisions occur at bar close at $T$; market order fills occur at next-bar open at $T+1$.
* **Verified Accounting Identity (spec §25)**: Double-entry cash/position tracking ensures $\text{equity} \equiv \text{cash} + \text{realized} + \text{unrealized} - \text{commissions}$.
* **Reproducibility (ADR-0008, NFR-001)**: Experiment configs record code commit, dataset checksum, environment, and seed.
* **Human Promotion Gate (FR-016)**: `PromotionDecision` requires explicit human approval; the system cannot auto-promote strategies.
* **Narrow P01 Boundary (ADR-0007)**: P02 consumes validated feeds through `P01DataContract` and does not reimplement vendor ingestion or data cleaning.

---

## 6. Deferred Capabilities (Architecture Boundary)

Per the P02 architecture specification and ADRs:
- **FastAPI API layer** — DEFERRED (ADR-0003: no external HTTP consumer yet; CLI is canonical).
- **PostgreSQL** — DEFERRED (ADR-0002: storage port abstraction is sufficient; PostgreSQL introduced only when lineage scale justifies it).
- **AI Research Copilot** — DEFERRED (introduced only after deterministic research foundations are stable).
- **Rust Performance Layer** — DEFERRED (introduced only if profiling identifies Python bottlenecks).
- **Live Broker Execution** — NEVER in P02 (belongs strictly to P03+ execution platform).
- **Dashboard UI** — NEVER in P02 (spec §4.1, §47: web dashboards introduce uninspected complexity; reports are file-based).

---

## 7. Immediate Next Engineering Steps

1. **Fix Simulation Init**: Remove `from qrsip.dirty_exec import DummyBacktestEngine` from `src/qrsip/simulation/__init__.py`.
2. **Implement Simulation Engine**: Author `src/qrsip/simulation/engine.py` with `run_simulation()`, connecting dataset, strategy, risk engine, execution, and portfolio into an event loop.
3. **Write Simulation Unit Tests**: Create `tests/unit/test_simulation.py` covering order fill timing, cost deduction, cash exhaustion, and risk rejections.
4. **Fix Validation Typing**: Fix `stats.py:79` to return `float(...)` to satisfy strict mypy.
5. **Write Validation Tests**: Create `tests/unit/test_validation.py` asserting numerical bounds and deflated Sharpe ratio calculations.
6. **Implement Research CLI & Reports**: Add experiment execution and Markdown report generation to `src/qrsip/cli.py`.
