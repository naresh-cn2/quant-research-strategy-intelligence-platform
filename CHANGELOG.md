# QRSIP — CHANGELOG.md

All notable changes to QRSIP are recorded here. The project follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Added

- Complete L0–L7 research-platform architecture with downward-only dependencies.
- Immutable domain entities, lifecycle validation, registry persistence, and human-controlled promotion records.
- P01 data contract, point-in-time market datasets, deterministic synthetic fixtures, and checksum-bound Parquet loading.
- Causal features, signal strategies, financial metrics, deterministic next-bar execution, explicit commissions/slippage, portfolio accounting, and risk controls.
- L5 validation evidence for significance, Deflated Sharpe Ratio, look-ahead bias, survivorship, multiple testing, parameter sensitivity, and walk-forward robustness.
- L6 canonical run artifacts, Markdown/JSON research reports, deterministic rerun verification, and experiment lineage.
- L7 research CLI workflows: `experiment run`, `experiment rerun`, `report show`, and `promote`.
- Unit, contract, property, adversarial, integration, acceptance, and regression test tiers.
- Developer tooling: strict mypy, Ruff, Bandit, pip-audit, Make targets, Docker definitions, and GitHub Actions workflows.
- Professional repository documentation, career engineering materials, security policy, contribution guide, and acceptance provenance matrix.

### Verified locally

- 352 automated tests pass.
- Unit, contract, property, adversarial, integration, acceptance, and regression suites pass.
- `ruff check src tests`, `ruff format --check src tests`, and `mypy src` pass.
- Bandit reports no medium- or high-severity findings.
- The frozen dependency audit reports no known vulnerabilities after excluding the local package from PyPI resolution.
- The fixture-backed research workflow produces canonical artifacts and reproduces the same result digest on rerun.
- Failed validation cannot be automatically approved.

### External acceptance status

- Clean-container acceptance: blocked because no supported container runtime is available in the current environment.
- Current-tree GitHub Actions CI and Security: passed for commit `8251ebc` (runs `36135187982` and `36135187979`).
- Canonical production P01 reference: unresolved because the repository contains the contract and adapter but no authoritative production artifact, manifest, or canonical checksum.

### Known limitations

- QRSIP is Alpha-stage research software, not a live trading or production deployment.
- Synthetic fixtures are explicitly labeled and are not production market data.
- The checked-in master specification is an incomplete historical preamble; missing section text was not reconstructed.
- Licensing remains unresolved under ADR-0004; no license file is added by this release preparation.

### Deferred

- FastAPI external API.
- PostgreSQL storage.
- Dashboard/UI.
- AI Research Copilot.
- Rust performance layer.
- Live broker execution and automated trading.
- P03 functionality and distributed microservices.
