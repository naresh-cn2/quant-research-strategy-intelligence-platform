# QRSIP — Quantitative Research & Strategy Intelligence Platform

**QRSIP** is a research-grade, deterministic and auditable system for transforming
quantitative trading hypotheses into reproducible experiments, simulated portfolios,
risk measurements, robustness analysis, bias validation, and evidence-backed
research reports.

It consumes trustworthy market-data infrastructure (P01) and forms the research
layer between historical data infrastructure and future portfolio/execution systems.

## What this is (and is not)

This is **not** a tutorial backtester, a notebook collection, a single-strategy
script, a toy Python project, or a dashboard whose calculations cannot be
reproduced.

This **is** a controlled research system whose fundamental workflow is:

Research Question → Hypothesis → Formal Strategy Specification → Data Contract →
Point-in-Time Dataset → Feature/Signal Computation → Deterministic Simulation →
Execution + Cost Model → Risk/Portfolio Model → Experiment Record →
Statistical & Robustness Validation → Research Report → Human Decision →
Candidate Promotion / Rejection.

## Repository layout

    quant-research-strategy-intelligence-platform/
    ├── src/qrsip/          # Python package source
    ├── tests/              # pytest suite (unit, integration, contract,
    │                         property, adversarial, acceptance, regression)
    ├── configs/            # YAML configuration layers
    ├── examples/           # example strategies, experiments, reports
    ├── docs/               # architecture, specifications, ADRs, operations
    ├── data/               # data directory (never commit raw datasets)
    └── .github/workflows/  # CI: ci.yml, security.yml

## Quick start

```bash
# Bootstrap a development environment
make bootstrap

# Health check
qrsip doctor

# Show current project status
qrsip status
```

## Development

```bash
make test        # run the pytest suite
make lint        # ruff lint
make format      # ruff format
make typecheck   # mypy strict
make security    # bandit + pip-audit
make ci          # local mirror of the CI pipeline
make build       # build the wheel
```

## Quality standard

This project is judged at five levels — **Starts**, **Correct**, **Reproducible**,
**Adversarially validated**, **Portfolio-grade**. A green dashboard is not evidence.
Every material result must be traceable to experiment_id, strategy_version,
data_version, configuration, code_commit, seed, cost assumptions, risk
configuration, and a result artifact.

See `docs/architecture/overview.md` and the full P02 Master Architecture
Specification for the complete system definition.

## License

Proprietary. See `LICENSE` and the ADR-0004 licensing decision.
