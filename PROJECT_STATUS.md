# QRSIP — PROJECT_STATUS.md
#
# This is the operational source of truth for the P02 implementation.
# It is continuously updated to reflect actual code, tests, and git state.
#
# Do not claim completion without evidence. See spec §35.

# P02 — Quantitative Research & Strategy Intelligence Platform
# ============================================================

**Status:** IN PROGRESS — NOT COMPLETE (Phases 0–4 Complete & Tested; Phase 5 WIP)

**Current Phase:** Phase 5 (Validation) — In Progress

**Last Verified Baseline Commit:** `e4f45e6` ("docs: synchronize P02 architecture and project status")

**Last Verification Timestamp:** 2026-09-24

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
| **L4 Simulation** | Execution Model (`execution.py`) | **Implemented** | **Tested** (simulation suite) | Orders, fills at next-bar open $T+1$ (ADR-0005), commission + slippage cost model |
| | Portfolio Accounting (`portfolio.py`)| **Implemented** | **Tested** (simulation suite) | Double-entry accounting, verified equity invariant; unmarked valuation fails closed |
| | Risk Engine (`risk.py`) | **Implemented** | **Tested** (simulation suite) | Pre-trade order limits (notional, position, gross exposure), drawdown circuit breaker |
| | Event-Loop Engine (`engine.py`) | **Implemented** | **Tested** (simulation suite) | `run_simulation` deterministic loop connecting dataset, signals, risk, execution, portfolio |
| | Module Entrypoint (`__init__.py`) | **Implemented** | **Import smoke-tested** | Clean package exports for the simulation layer |
| **L5 Validation** | Validation Math (`stats.py`) | **Implemented** | **Dedicated tests pending** | t-statistic, normal approximation p-value, skewness, kurtosis, Deflated Sharpe Ratio |
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

* **Total Automated Tests Passing:** **307** (in 0.98s via Python 3.12 / pytest 8.4.2)
* **Unit Test Breakdown by Suite:**
  * `tests/unit/test_cli.py`: 10 passed
  * `tests/unit/test_config.py`: 31 passed
  * `tests/unit/test_data.py`: 67 passed
  * `tests/unit/test_doctor.py`: 14 passed
  * `tests/unit/test_domain.py`: 59 passed
  * `tests/unit/test_errors.py`: 16 passed
  * `tests/unit/test_logging.py`: 11 passed
  * `tests/unit/test_quant.py`: 64 passed
  * `tests/unit/test_simulation.py`: 35 passed
* **Higher-Order Test Suites (Status: SKELETON ONLY — 0 tests written yet):**
  * `tests/contract/`: SKELETON (only `README.md`)
  * `tests/property/`: SKELETON (only `README.md`)
  * `tests/adversarial/`: SKELETON (only `README.md`)
  * `tests/integration/`: SKELETON (only `README.md`)
  * `tests/acceptance/`: SKELETON (only `README.md`)
  * `tests/regression/`: SKELETON (only `README.md`)
* **Linter & Formatter Status:**
  * `ruff format --check src tests`: Clean (48 files).
  * `ruff check src tests`: Clean (0 errors).
* **Type Checking Status:**
  * `mypy src`: Passing on all 30 source files.
* **Security Audit Status:**
  * `bandit -r src -c pyproject.toml -ll`: Passing (0 medium/high issues across 3,879 LOC).

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
1. `src/qrsip/validation/stats.py` (148 LOC): Statistical significance math implemented (t-stat, normal approximation p-value, skewness, excess kurtosis, expected max normal, Deflated Sharpe Ratio).
2. `src/qrsip/validation/__init__.py` (30 LOC): Exports statistical functions. Clean import.
3. `mypy src` passes after the explicit `float(...)` conversion in `sample_skewness`.
4. Dedicated validation tests, bias checks, and walk-forward robustness engine remain outstanding.

### L6 Intelligence & L7 Presentation
1. Research report generation engine: **MISSING** (entities defined in `domain/results.py`, but generator logic is unwritten).
2. Experiment run CLI subcommands (`qrsip experiment run`, `qrsip experiment rerun`): **MISSING**.

---

## 4. Acceptance Criteria & Quality Gates Still Outstanding

Per spec §50, the platform is considered **working** only when all of the following hold:
- [x] Source code exists and architecture is implemented (L0–L4 complete; L5 in progress)
- [x] Storage contracts work (`StoragePort` + `FileStorage` verified with SHA-256 canonical JSON)
- [x] P01 data contract works (enforced via `P01DataContract` and `PointInTimeView`)
- [x] Strategy execution works (deterministic L4 event loop with next-bar fills)
- [x] Portfolio accounting is verified by unit tests
- [x] Risk engine is verified by unit tests
- [x] Metrics are tested (307 unit tests passing across completed layers)
- [ ] Bias checks work (lookahead / multiple testing checks pending)
- [ ] Adversarial tests work (`tests/adversarial/` contains only its skeleton specification)
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

1. **Write Validation Tests**: Create `tests/unit/test_validation.py` asserting numerical bounds and deflated Sharpe ratio calculations.
2. **Implement Validation Runner**: Add bias verification (look-ahead and survivorship tests) and parameter sensitivity analysis.
3. **Implement Research CLI & Reports**: Add experiment execution and Markdown report generation to `src/qrsip/cli.py`.
4. **Add Higher-Order Tests**: Populate `tests/property/` and `tests/adversarial/` with invariant and failure-mode coverage.
