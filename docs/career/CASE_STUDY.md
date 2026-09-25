# QRSIP Engineering Case Study

## 1. Problem

Quantitative strategy research can produce misleading results when experiments depend on future information, unrealistic execution assumptions, incomplete accounting, unrecorded data identity, p-hacking, or automatic promotion without human review.

## 2. Requirements

The repository evidence supports requirements for a narrow P01 boundary, point-in-time causality, explicit next-bar execution, commissions and slippage, accounting and risk constraints, experiment/data lineage, deterministic artifacts, validation evidence, fail-closed behavior, human promotion, and local/container/CI/security verification paths.

The master specification file is incomplete as historical documentation; the provenance matrix records this limitation.

## 3. Architectural approach

QRSIP uses downward-only dependencies from L7 Presentation to L0 Infrastructure. Higher layers orchestrate lower-layer contracts; lower layers do not depend on presentation, web, or research-intelligence modules.

The architecture separates data validity from research logic, signal generation from execution, portfolio state from risk decisions, validation evidence from promotion, and artifact persistence from quantitative calculations.

## 4. Data architecture

`P01DataContract` describes dataset identity and ordered bars. `MarketDataset` validates ordering and instrument membership. `PointInTimeView` exposes only observations available at the decision clock and raises `LookAheadError` for future reads.

The Parquet adapter requires a manifest containing a descriptor, SHA-256 checksum, and row count. It validates payload checksum, OHLCV schema, bar quality, row count, instrument set, and coverage before returning data.

The fixture provider is deterministic and explicitly labels its output as synthetic. It is not a substitute for a production P01 reference.

## 5. Quantitative engine

The quant layer provides causal features, signal strategies, and financial metrics. Metrics include Sharpe, Sortino, Calmar, maximum drawdown, win rate, and profit factor, with explicit handling for undefined ratios.

The signal contract accepts only a causal close-history sequence. This makes the input available to a strategy explicit and testable.

## 6. Simulation engine

The simulation loop processes timestamps deterministically. At each event it fills eligible pending orders at the current open, marks the portfolio at the current close, verifies the accounting identity, records an equity point, evaluates the drawdown circuit breaker, and evaluates strategy signals when eligible.

Decisions are made at bar close T and fills occur at the next bar open T+1. Costs are explicit in `CostModel`.

## 7. Validation architecture

L5 produces structured validation checks for statistical significance, Deflated Sharpe Ratio, look-ahead evidence, survivorship evidence, multiple-testing correction, parameter sensitivity, and walk-forward evidence.

The validation runner does not promote a strategy. It produces evidence for review.

## 8. Research integrity

The project treats missing evidence as non-passing when policy requires it. It preserves unfavorable results, records limitations, labels synthetic data, and keeps the human decision explicit. The report generator separates observed evidence from inference.

## 9. Deterministic execution

Determinism is enforced at several boundaries: fixture data is generated from integer-based state transitions, dataset and portfolio iteration is ordered, simulation decisions receive only a causal close-history prefix, and persisted artifacts use canonical JSON. The L6 run record includes resolved configuration, dataset checksum, seed, metrics, validation evidence, report content, and a SHA-256 digest. A rerun must reproduce that digest; a changed digest is treated as a reproducibility failure.

## 10. Testing strategy

The repository has 352 passing tests across unit, contract, property, adversarial, integration, acceptance, and regression suites. The acceptance suite exercises CLI run, report display, and rerun. The adversarial suite covers tampered digests, missing artifacts, and attempts to approve failed validation.

## 11. Security

Security controls include Bandit, pip-audit, frozen requirements, Gitleaks workflow configuration, atomic file writes, storage path validation, structured failures, no live broker integration, and human-controlled promotion.

Security claims are limited to implemented controls and locally executed checks. External Security workflow execution remains separate.

## 12. Reproducibility

A run artifact records experiment configuration, seed, code commit, environment, dataset identity/checksum, simulation evidence, metrics, validation summary, report, and canonical digest.

A rerun is considered reproduced only when the digest matches. Missing artifacts and changed digests fail closed.

## 13. Failure handling

The system uses explicit errors for malformed configuration, invalid data, missing marks, accounting failures, risk breaches, invalid metrics, missing evidence, checksum mismatches, and reproduction mismatches. It does not silently substitute prices, marks, conclusions, or production data.

## 14. Acceptance process

The repository contains local verification scripts, test tiers, a Dockerfile, Compose configuration, Make targets, GitHub Actions workflows, a release checklist, and an acceptance provenance matrix.

Current status distinguishes local implementation verification, clean-container evidence, current-tree external CI evidence, canonical production P01 evidence, and deferred capabilities.

## 15. Current limitations

QRSIP is Alpha-stage research software. The local fixture workflow does not establish market-data production readiness, profitability, live execution capability, or production deployment. External container, CI, and P01 reference evidence is not available in the current environment.

## 16. Lessons demonstrated by the implementation

The implementation demonstrates how to make quantitative research constraints executable: encode timing in interfaces, keep data identity attached to results, verify accounting at runtime, expose uncertainty through validation evidence, and make the final promotion decision human-owned. It also demonstrates honest engineering communication by recording unresolved external evidence instead of converting missing infrastructure into claims.
