# QRSIP — Quantitative Research & Strategy Intelligence Platform

> **Project Status:** `IN PROGRESS / NOT COMPLETE` (Alpha stage)
>
> **Development Phase:** Phase 4 (Simulation) & Phase 5 (Validation) in progress.
>
> **Test Suite:** 272 automated unit tests passing in 1.54s.
>
> *Notice: QRSIP is under active engineering development. It is **not** production-ready, **not** feature-complete, and **not** yet verified for live portfolio management.*

---

## 1. What QRSIP Is

**QRSIP** (Quantitative Research & Strategy Intelligence Platform — Project P02) is a research-grade, deterministic, and auditable Python system designed to transform quantitative trading hypotheses into verified, bias-tested trading strategies.

It provides the computational and validation scaffolding that sits between raw historical market data infrastructure and future live execution systems:

$$\text{Research Question} \longrightarrow \text{Hypothesis} \longrightarrow \text{Strategy Spec} \longrightarrow \text{Point-in-Time Data} \longrightarrow \text{Simulation} \longrightarrow \text{Validation} \longrightarrow \text{Research Report} \longrightarrow \text{Human Decision}$$

### What This Is Not
* **Not a toy tutorial backtester**: It does not make unrealistic assumptions like perfect fills, zero commissions, or instant zero-latency executions.
* **Not an ad-hoc Jupyter notebook collection**: Experiments are reproducible entities with immutable configs, dataset manifests, and seeds.
* **Not a live broker execution engine**: Live trading is strictly out of scope (reserved for downstream platforms).
* **Not a dashboard UI**: Unaudited visual dashboards are deliberately excluded in favor of auditable, versioned research reports.

---

## 2. Why It Exists

Most quantitative strategy failures originate from subtle research methodological errors:
1. **Look-ahead bias**: Strategy logic observing information before it was officially published or closed.
2. **Unrealistic fill assumptions**: Assuming market orders fill at the decision bar's close price or at zero spread/cost.
3. **Broken accounting**: Fabricating cash or valuing unmarked positions without fail-closed accounting identities.
4. **Data leakage & p-hacking**: Running multiple parameter variations and selecting optimal outcomes without multiple-testing penalties (such as Deflated Sharpe Ratios).
5. **Irreproducibility**: Inability to rerun a historical backtest and obtain bit-for-bit identical results due to untracked environment dependencies or random seeds.

QRSIP exists to enforce mathematical and software engineering rigor to eliminate these failure modes structurally.

---

## 3. Core Architectural Principles

* **Fail-Closed by Design**: If required data, configuration, marks, or validation rules are missing or ambiguous, the system raises an explicit `QRSIPError` with actionable structured context. It never guesses or fabricates prices.
* **Point-in-Time Safety**: Strict causality is enforced at the data layer. Decisions at timestamp $T$ can only view market data up to $T$.
* **Deterministic Execution**: Given the same dataset, configuration, and random seed, simulation outputs are bit-for-bit identical.
* **Explicit Cost & Slippage Modeling**: Commissions (basis points and fixed fees) and slippage penalties are explicitly applied to fills.
* **Verified Accounting Invariants**: Every cash movement and fill is accounted for via double-entry arithmetic.
* **Separation of Concerns**: Strategy logic never touches disk storage, network sockets, or presentation interfaces.
* **Human-in-the-Loop Promotion**: Machine-automated pipelines can reject candidate strategies, but promotion to production candidacy requires explicit human sign-off (`PromotionDecision`).

---

## 4. Architecture & Layer Model

The system follows a strict downward-only dependency model across 8 conceptual layers:

```mermaid
flowchart TD
    L7["L7: Presentation (CLI)"] --> L6["L6: Intelligence & Reports"]
    L6 --> L5["L5: Validation (Significance & Robustness)"]
    L5 --> L4["L4: Simulation (Execution, Portfolio, Risk)"]
    L4 --> L3["L3: Quant (Features, Signals, Metrics)"]
    L3 --> L2["L2: Data (P01 Contract, Point-in-Time Dataset)"]
    L2 --> L1["L1: Domain (Entities, Lifecycle, Registry)"]
    L1 --> L0["L0: Infrastructure (Errors, Config, Logging, StoragePort)"]
```

| Layer | Responsibility | Primary Modules | Implementation Status |
|---|---|---|:---:|
| **L0 Infrastructure** | Base exceptions, YAML configuration, structured logging, system health checks, portable file storage | `errors.py`, `config.py`, `logging.py`, `doctor.py`, `infrastructure/storage.py` | **100% Implemented & Tested** |
| **L1 Domain** | Research entities, 12-state research lifecycle state machine, append-only entity registry | `domain/base.py`, `domain/entities.py`, `domain/lifecycle.py`, `domain/registry.py`, `domain/results.py` | **100% Implemented & Tested** |
| **L2 Data** | Market data contract (P01 boundary), bar quality validator, point-in-time views, deterministic test fixtures | `data/contract.py`, `data/validation.py`, `data/dataset.py`, `data/fixtures.py` | **90% Implemented & Tested** |
| **L3 Quant** | Causal feature calculation, signal strategy protocols, fail-closed financial metrics | `quant/features.py`, `quant/signals.py`, `quant/metrics.py` | **90% Implemented & Tested** |
| **L4 Simulation** | Order models, deterministic fill simulator, double-entry portfolio accounting, pre-trade risk engine, event loop | `simulation/execution.py`, `simulation/portfolio.py`, `simulation/risk.py`, `simulation/engine.py` | **~60% (WIP / Untracked)** |
| **L5 Validation** | Statistical significance, Deflated Sharpe Ratio, bias validation, walk-forward analysis | `validation/stats.py` | **~30% (WIP / Untracked)** |
| **L6 Intelligence** | Research report synthesis, experiment comparison & lineage | `domain/results.py` | **~20% (Partial scaffold)** |
| **L7 Presentation** | Command-line interface (`qrsip`) | `cli.py` | **~30% (Skeleton implemented)** |

---

## 5. P01 $\to$ P02 Relationship & Data Boundary

QRSIP (P02) does **not** ingest raw vendor data, clean messy exchange feeds, or manage real-time websocket connections. That responsibility belongs strictly to upstream market data infrastructure (**P01**).

* P02 consumes market data exclusively through the [`P01DataContract`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/data/contract.py) protocol.
* Data is exchanged as validated, ordered sequences of [`Bar`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/data/contract.py) records, where `timestamp` represents the UTC **close** of the bar.
* For standalone testing and development without a live P01 instance, P02 provides deterministic fixtures via [`FixtureP01Provider`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/data/fixtures.py), explicitly labeled as test fixtures (ADR-0007).

---

## 6. Point-in-Time Safety (Zero Look-Ahead Bias)

To prevent look-ahead bias, strategy code never interacts with raw bar arrays or future data slices. All data access must pass through [`PointInTimeView`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/data/dataset.py):

* A bar with closing timestamp $T$ becomes visible to the strategy **only** when `as_of >= T`.
* Any query or indexing operation attempting to inspect bars with timestamps $> T$ immediately raises a fail-closed [`LookAheadError`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/data/dataset.py).
* Causal feature calculations ([`features.py`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/quant/features.py)) require explicit warm-up periods and return `None` during warm-up rather than backfilling from future data.

---

## 7. Deterministic Execution Model (ADR-0005)

To guarantee realism, QRSIP adheres to an explicit timing convention:

1. **Signal Decision**: At the **close** of bar $T$ (`decision_time = T`), strategy logic evaluates available data and issues a target order.
2. **Order Execution**: Market orders fill at the **open of the subsequent bar** $T+1$ (`fill_time > decision_time`). Same-bar close execution is strictly forbidden.
3. **Explicit Cost Model**:
   * **Commissions**: Calculated as basis points of traded value plus an optional fixed fee per fill.
   * **Slippage**: Applied as an adverse basis-point penalty embedded directly into the execution price (buyers pay more; sellers receive less).

---

## 8. Portfolio Accounting & Invariants (spec §25)

Simulation accounting is cash-first and double-entry ([`portfolio.py`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/simulation/portfolio.py)):

* **Verified Equity Identity**:
  $$\text{equity} = \text{initial\_cash} + \text{realized\_pnl} + \text{unrealized\_pnl} - \text{commissions}$$
* **No Unmarked Valuation**: Every open position must have a verifiable current market price. If a mark is missing, valuation fails closed with [`PortfolioError`](file:///home/mrcn2/quant-research-strategy-intelligence-platform/src/qrsip/errors.py) rather than defaulting to cost basis.
* **Cash Solvency**: Purchases exceeding available cash are rejected rather than allowing negative cash balances.

---

## 9. Current Testing Evidence

The platform currently includes **272 passing automated unit tests**:

```bash
$ pytest
============================= 272 passed in 1.54s ==============================
```

* **Coverage Across Completed Layers**:
  * `test_cli.py` (10 tests): Command-line argument parsing and subcommands.
  * `test_config.py` (31 tests): YAML configuration, path resolution, env overrides, and sanitization.
  * `test_data.py` (67 tests): Bar schema validation, point-in-time access, lookahead prevention, and fixture generation.
  * `test_doctor.py` (14 tests): System diagnostic checks and health report formatting.
  * `test_domain.py` (59 tests): Research entities, 12-stage lifecycle transitions, and registry storage.
  * `test_errors.py` (16 tests): Error inheritance, structured context verification, and fail-closed behaviors.
  * `test_logging.py` (11 tests): JSON structured logging and timed events.
  * `test_quant.py` (64 tests): Causal moving averages, signal generators, and financial metrics (Sharpe, Sortino, Drawdown, etc.).
* **Static Analysis**:
  * `ruff check src tests`: Clean (0 errors).
  * `mypy src`: Strict type-checking passing on all committed source files.
  * `bandit -r src -c pyproject.toml -ll`: Passing with zero medium/high security issues.

---

## 10. Current Implementation Status & Known Limitations

### Current Status
* **Phases 0–3 (Foundation, Domain, Data, Quant)**: Fully completed, strictly typed, and thoroughly covered by automated unit tests.
* **Phase 4 (Simulation)**: Core execution, portfolio accounting, and risk checks are written in working directory; the central event loop (`engine.py`) and simulation test suite are in progress.
* **Phase 5 (Validation)**: Statistical significance functions are written; validation runner and bias checks are in progress.

### Known Limitations & Defects
* **WIP Untracked Files**: `src/qrsip/simulation/` and `src/qrsip/validation/` are currently untracked in git.
* **Defective Import in Simulation**: `src/qrsip/simulation/__init__.py` contains a broken reference to `qrsip.dirty_exec` and attempts to import an uncreated `engine.py`.
* **Missing Event Loop**: The unified `run_simulation()` function connecting data feeds to orders and portfolios is not yet implemented.
* **PostgreSQL Deferred**: Durable entity persistence currently uses `FileStorage` with SHA-256 canonical JSON. Relational database storage is deferred (ADR-0002).
* **Higher-Order Tests Pending**: `tests/adversarial/`, `tests/property/`, `tests/integration/`, and `tests/acceptance/` currently contain only architectural README specifications.

---

## 11. Remaining Engineering Work

To achieve full architecture baseline completion:
1. **Simulation Event Loop**: Author `src/qrsip/simulation/engine.py` (`run_simulation`) and resolve import dependencies.
2. **Simulation Unit Tests**: Author `tests/unit/test_simulation.py` covering fill timing, cash accounting, and risk breach handling.
3. **Validation Runner**: Implement bias verification (look-ahead and survivorship tests) and parameter sensitivity analysis.
4. **Research Report Generator**: Implement Markdown and JSON report rendering from experiment outcomes.
5. **Research CLI Commands**: Wire experiment execution (`qrsip experiment run`) into `src/qrsip/cli.py`.
6. **Property & Adversarial Test Suites**: Author tests in `tests/property/` and `tests/adversarial/`.

---

## 12. Local Development & Quick Start

### Prerequisites
* Python 3.11 or Python 3.12
* Git
* Make (optional, but recommended)

### Setup & Bootstrap

```bash
# Clone repository
git clone https://github.com/naresh-cn2/quant-research-strategy-intelligence-platform.git
cd quant-research-strategy-intelligence-platform

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package in editable mode with development dependencies
pip install -e ".[dev]"
```

### Running Health Checks & Status

```bash
# Run environment diagnostics
qrsip doctor

# View current operational project status
qrsip status
```

### Running Quality Checks & Tests

```bash
# Run the test suite
pytest

# Run linter
ruff check src tests

# Check code formatting
ruff format --check src tests

# Run strict type checking
mypy src

# Run security checks
bandit -r src -c pyproject.toml -ll
```

---

## 13. Project Maturity & License

* **Maturity**: Alpha (`Development Status :: 3 - Alpha`).
* **License**: Proprietary (licensing decision pending per ADR-0004).
