# QRSIP — PROJECT_STATUS.md
#
# This is the operational source of truth for the P02 implementation.
# It is continuously updated to reflect actual code, tests, and git state.
#
# Do not claim completion without evidence. See the acceptance provenance matrix.

# P02 — Quantitative Research & Strategy Intelligence Platform
# ============================================================

**Status:** BLOCKED — local implementation and verification pass; external acceptance gates remain incomplete (container runtime and production P01 reference)

**Current Phase:** Final acceptance verification

**Last Verified Baseline Commit:** `8fc4590` (pushed to `origin/main`; CI run `36135583631` and Security run `36135583745` passed)

**Last Verification Timestamp:** 2026-09-25

**Acceptance provenance:** See [`docs/operations/acceptance_provenance_matrix.md`](docs/operations/acceptance_provenance_matrix.md).

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
| | | Parquet/Arrow Dataset Loader (`parquet.py`) | **Implemented** | **Tested** | Checksum-bound Parquet P01 adapter; schema, row-count, instrument, coverage, and bar-quality checks |
| **L3 Quant** | Causal Features (`features.py`) | **Implemented** | **Tested** (part of quant) | SMA, EMA, simple/log returns, rolling volatility, momentum; warm-up is `None` |
| | Strategy Signals (`signals.py`) | **Implemented** | **Tested** (part of quant) | `SignalStrategy` protocol, `MovingAverageCrossStrategy`, `ConstantStrategy` |
| | Financial Metrics (`metrics.py`) | **Implemented** | **Tested** (part of quant) | Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Profit Factor, `PerformanceMetrics` |
| **L4 Simulation** | Execution Model (`execution.py`) | **Implemented** | **Tested** (simulation suite) | Orders, fills at next-bar open $T+1$ (ADR-0005), commission + slippage cost model |
| | Portfolio Accounting (`portfolio.py`)| **Implemented** | **Tested** (simulation suite) | Double-entry accounting, verified equity invariant; unmarked valuation fails closed |
| | Risk Engine (`risk.py`) | **Implemented** | **Tested** (simulation suite) | Pre-trade order limits (notional, position, gross exposure), drawdown circuit breaker |
| | Event-Loop Engine (`engine.py`) | **Implemented** | **Tested** (simulation suite) | `run_simulation` deterministic loop connecting dataset, signals, risk, execution, portfolio |
| | Module Entrypoint (`__init__.py`) | **Implemented** | **Import smoke-tested** | Clean package exports for the simulation layer |
| | **L5 Validation** | Validation Math (`stats.py`) | **Implemented** | **Dedicated tests** | t-statistic, normal approximation p-value, skewness, kurtosis, Deflated Sharpe Ratio |
| | Validation Runner & Bias Checks | **Implemented** | **Tested** | Look-ahead bias verification, multiple-testing correction, survivorship evidence |
| | Robustness Suite | **Implemented** | **Tested** | Parameter sensitivity and walk-forward validation evidence |
| **L6 Intelligence** | Research Report Generator | **Implemented** | **Tested** | Deterministic Markdown/JSON reports with lineage, metrics, validation, assumptions, and limitations |
| | Experiment Artifact & Reproduction | **Implemented** | **Tested** | Canonical JSON run artifact, lineage records, deterministic digest, and fail-closed rerun |
| | AI Copilot / Assistant | **Deferred** | N/A | Deferred per architecture spec until deterministic foundations are complete |
| **L7 Presentation** | CLI Skeleton (`cli.py`) | **Implemented** | **Tested** | `qrsip init`, `qrsip doctor`, `qrsip status` |
| | Research CLI Commands | **Implemented** | **Tested** | `qrsip experiment run`, `qrsip experiment rerun`, `qrsip report show`, `qrsip promote` |
| | FastAPI REST API | **Deferred** | N/A | Deferred per ADR-0003 until an external HTTP consumer requires it |
| | Dashboard UI | **Excluded** | N/A | Explicitly out of scope for P02 (spec §4.1, §47) |

---

## 2. Test Suite & Verification Status

* **Total Automated Tests Passing:** **352** (repository environment, Python 3.12 / pytest 8.4.2)
* **Test Tier Breakdown:**
  * `tests/unit/`: 338 passed
  * `tests/contract/`: 3 passed
  * `tests/property/`: 2 passed
  * `tests/adversarial/`: 4 passed
  * `tests/integration/`: 2 passed
  * `tests/acceptance/`: 1 passed
  * `tests/regression/`: 2 passed
* **Linter & Formatter Status:**
  * `ruff format --check src tests`: Clean (63 files).
  * `ruff check src tests`: Clean (0 errors).
* **Type Checking Status:**
  * `mypy src`: Passing on all 36 source files.
* **Security Audit Status:**
  * `bandit -r src -c pyproject.toml -ll`: Passing (0 medium/high issues).
* **Local verification:** The repository harness passes all tiers, strict static checks, Bandit, and pip-audit after the dependency-freeze correction.

---

## 3. Implementation Inventory and Remaining WIP

### L4 Simulation Layer (`src/qrsip/simulation/`)
1. `src/qrsip/simulation/execution.py` (214 LOC): Implemented orders, next-bar open fills (ADR-0005), and explicit cost model (commissions + embedded slippage).
2. `src/qrsip/simulation/portfolio.py` (239 LOC): Implemented cash-first double-entry accounting enforcing the verified equity invariant ($\text{equity} = \text{cash} + \text{realized} + \text{unrealized} - \text{commissions}$).
3. `src/qrsip/simulation/risk.py` (197 LOC): Implemented pre-trade limit checks and peak-to-trough drawdown circuit breaker.
4. `src/qrsip/simulation/engine.py` (484 LOC): Implemented deterministic `run_simulation` event loop connecting `MarketDataset`, strategies, risk, execution, and portfolio state.
5. `src/qrsip/simulation/__init__.py` (60 LOC): Implemented clean package exports.
6. `tests/unit/test_simulation.py` (735 LOC): 35 unit tests covering execution timing, costs, accounting, risk, short selling, multi-instrument behavior, point-in-time causality, and determinism.

### L5 Validation Layer (`src/qrsip/validation/`)
1. `stats.py`: Significance math, p-values, skewness, kurtosis, expected maximum normal, and Deflated Sharpe Ratio.
2. `bias.py`: Look-ahead and survivorship evidence models and checks.
3. `multiple_testing.py`: Deterministic Holm correction.
4. `robustness.py`: Parameter sensitivity and walk-forward evidence.
5. `runner.py`: Fail-closed validation orchestration and immutable summaries.
6. `tests/unit/test_validation.py`: Boundary, invalid-input, numerical, deterministic, and failure-mode coverage.

### L6 Intelligence & L7 Presentation
1. `intelligence.py`: Resolved settings, P01/fixture and Parquet loading, deterministic simulation, metrics, validation, lineage joins, canonical artifacts, reports, and rerun verification.
2. `cli.py`: `experiment run`, `experiment rerun`, `report show`, and human-controlled `promote` workflows.
3. `tests/contract/`, `tests/integration/`, `tests/property/`, `tests/adversarial/`, `tests/acceptance/`, and `tests/regression/`: Executable contract and higher-order verification.

---

## 4. Acceptance Criteria & Quality Gates Still Outstanding

According to the repository acceptance checklist, the platform is considered **working** only when all of the following hold:
- [x] Source code exists and architecture is implemented (L0–L7)
- [x] Storage contracts work (`StoragePort` + `FileStorage` verified with SHA-256 canonical JSON)
- [x] P01 data contract works (enforced via `P01DataContract`, fixtures, and `PointInTimeView`)
- [x] Strategy execution works (deterministic L4 event loop with next-bar fills)
- [x] Portfolio accounting is verified by unit tests
- [x] Risk engine is verified by unit tests
- [x] Metrics and validation evidence are tested
- [x] Bias checks, multiple-testing correction, sensitivity, and walk-forward evidence are tested
- [x] Adversarial, property, contract, integration, acceptance, and regression tests are executable
- [x] Reproduction is verified by canonical digest comparison
- [x] Local verification harness passes (`scripts/validation/run_checks.sh`)
- [x] CI and Security workflows passed on verified baseline `8fc4590` (runs `36135583631` and `36135583745`)
- [ ] Fresh-environment acceptance test passes in a clean container (blocked: Docker/Podman/nerdctl unavailable)
- [ ] External checksum-bound P01 production reference is verified (blocked: no production dataset source/checksum/artifact is documented or available)

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

## 7. Release Verification Work

The current in-scope implementation is locally verified. Final acceptance is blocked only by external evidence gates:
1. Run the acceptance workflow in a clean, reproducible container.
2. Supply an authoritative external P01 production artifact and manifest, if that artifact is required by a future acceptance decision, and verify its checksum/schema.
