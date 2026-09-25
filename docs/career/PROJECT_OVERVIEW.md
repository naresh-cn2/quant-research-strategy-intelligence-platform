# QRSIP Project Overview

## Project title

QRSIP — Quantitative Research & Strategy Intelligence Platform

## Project category

Quantitative software engineering, research engineering, deterministic simulation, and auditable strategy research.

## Problem statement

Quantitative strategy research can produce misleading results when experiments depend on future information, unrealistic execution assumptions, incomplete accounting, unrecorded data lineage, or unreproducible configurations. QRSIP is designed to make those failure modes explicit and testable.

The repository transforms a research question and hypothesis into a configured experiment, a point-in-time dataset, a deterministic simulation, validation evidence, an auditable report, and a human promotion decision.

## Technical objective

Build a Python research system with:

- downward-only architectural dependencies;
- fail-closed data and configuration contracts;
- explicit execution timing and transaction costs;
- accounting and risk invariants;
- validation evidence rather than unsupported conclusions;
- canonical artifacts and deterministic reruns;
- local and external verification gates;
- a human-controlled promotion boundary.

## Architecture

QRSIP follows the existing L0–L7 model:

```text
L7 Presentation
        ↓
L6 Intelligence
        ↓
L5 Validation
        ↓
L4 Simulation
        ↓
L3 Quant
        ↓
L2 Data
        ↓
L1 Domain
        ↓
L0 Infrastructure
```

See `docs/architecture/overview.md` for dependency rules and workflow.

## Main engineering challenges

- Preventing look-ahead information access.
- Preserving causal signal and fill timing.
- Modeling commissions and slippage explicitly.
- Verifying portfolio accounting after every simulation step.
- Keeping data and experiment lineage auditable.
- Separating validation evidence from promotion decisions.
- Producing deterministic artifacts and detecting reproduction drift.
- Failing visibly when data, configuration, or evidence is incomplete.

## Key engineering decisions

- P02 consumes P01 through a narrow contract rather than reimplementing ingestion.
- Synthetic fixtures are clearly labeled and never represented as production data.
- Docker is a reproducible verification environment, not the only development method.
- FastAPI, PostgreSQL, dashboards, AI copilot, Rust, and live execution remain deferred.
- Promotion remains a human-controlled decision and cannot be inferred from a passing metric alone.
- ADR-0005 fixes the signal/fill convention: decision at close T, fill at next open T+1.
- ADR-0006 distinguishes byte identity from documented floating-point tolerance.

## Quantitative research capabilities

The repository implements causal features, signal strategies, OHLCV data contracts, point-in-time views, order/fill simulation, commissions, slippage, portfolio accounting, risk limits, drawdown handling, performance metrics, statistical validation, Deflated Sharpe Ratio, multiple-testing correction, bias checks, parameter sensitivity, and walk-forward evidence.

These are implementation and testing claims. They are not claims of profitability or production investment performance.

## Reliability mechanisms

- Dataset checksums and manifests.
- Deterministic fixture generation.
- Canonical JSON artifact serialization.
- Experiment configuration snapshots.
- Stable dataset and portfolio ordering.
- Explicit numerical tolerance policy.
- Reproduction digest comparison.
- Fail-closed behavior for missing marks, malformed data, invalid risk inputs, and incomplete evidence.

## Security mechanisms

- Bandit static analysis.
- pip-audit dependency analysis.
- Frozen requirements generation.
- Gitleaks workflow configuration.
- Structured error context.
- Storage path validation and atomic writes.
- No live broker integration.
- No automatic strategy promotion.

## Testing strategy

The repository has 352 passing tests across unit, contract, property, adversarial, integration, acceptance, and regression suites. Tests cover the domain, data, quant, simulation, validation, CLI, intelligence, reporting, reproduction, and promotion-gate behavior.


## Reproducibility strategy

Experiments record resolved configuration, seed, dataset identity/checksum, code commit, environment identifier, validation evidence, report content, and a canonical result digest. `qrsip experiment rerun` re-executes the recorded configuration and fails when the digest changes or required artifacts are unavailable.

## Current implementation state

- L0–L7: implemented.
- Local tests and quality checks: passing.
- Fixture-backed research workflow: passing.
- Deterministic reproduction: passing locally.
- Clean-container acceptance: blocked by unavailable container runtime in the current environment.
- Current-tree external CI: blocked by unavailable authenticated GitHub Actions capability.
- Canonical production P01 reference: unresolved; the generic checksum-bound adapter is implemented, but the authoritative production artifact is external and absent.

## Known limitations

- The repository is Alpha-stage research software.
- Synthetic fixtures are not production market data.
- No production trading performance is claimed.
- The authoritative production P01 dataset is not present.
- The master specification is a short preamble with missing historical section text.
- No external clean-container or current-tree CI result is available in the current environment.

## Deferred roadmap

The following are explicitly outside the current implementation:

- FastAPI HTTP API.
- PostgreSQL storage.
- Dashboard/UI.
- AI Research Copilot.
- Rust performance layer.
- Live broker execution and automated trading.
- P03 functionality.
- Distributed microservices.

## Why this project demonstrates engineering ability

The repository demonstrates engineering ability through the relationship between code and evidence: architectural boundaries are explicit, financial semantics are tested, data lineage is recorded, unfavorable or incomplete validation is not hidden, reproduction is checked by digest, promotion is human-controlled, and acceptance status distinguishes local evidence from external evidence. The project is a defensible quantitative software engineering case study rather than a claim of production trading performance.
