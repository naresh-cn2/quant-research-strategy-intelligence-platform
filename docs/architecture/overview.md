# QRSIP — docs/architecture/overview.md
#
# This document is the canonical architecture overview for P02.
# It is derived from the P02 Master Architecture Specification.
#
# For the full specification, see:
# - docs/specifications/p02_master_architecture_specification.md
# - The repository root README.md
#
# Layer model:
#
#   L0 — Infrastructure
#   L1 — Domain
#   L2 — Data
#   L3 — Quant
#   L4 — Simulation
#   L5 — Validation
#   L6 — Intelligence
#   L7 — Presentation
#
# Dependencies must flow downward only.
# Presentation must not contain core financial calculations.
# Strategy code must not directly access infrastructure.
# Domain must remain independent of infrastructure.
# P02 must consume P01 through a contract and must not reimplement P01.
#
# Core workflow:
#
#   Research Question → Hypothesis → Strategy Specification →
#   Data Contract → Point-in-Time Dataset → Feature/Signal →
#   Deterministic Simulation → Execution + Costs → Portfolio →
#   Risk → Experiment Record → Validation → Robustness →
#   Research Report → Human Decision → Promotion / Rejection
#
# Definition of "working" (spec §50):
#
#   SOURCE CODE EXISTS
#   AND ARCHITECTURE IS IMPLEMENTED
#   AND STORAGE CONTRACTS WORK
#   AND P01 DATA CONTRACT WORKS
#   AND STRATEGY EXECUTION WORKS
#   AND PORTFOLIO ACCOUNTING IS VERIFIED
#   AND RISK ENGINE IS VERIFIED
#   AND METRICS ARE TESTED
#   AND BIAS CHECKS WORK
#   AND ADVERSARIAL TESTS WORK
#   AND REPRODUCTION WORKS
#   AND CI IS GREEN
#   AND DOCUMENTATION MATCHES REALITY
#   AND FRESH-ENVIRONMENT ACCEPTANCE TEST PASSES
#
# Quality levels (spec §5):
#
#   LEVEL 1 — Starts
#   LEVEL 2 — Correct
#   LEVEL 3 — Reproducible
#   LEVEL 4 — Adversarially validated
#   LEVEL 5 — Portfolio-grade
#
# Current implementation status (as of 2026-09-25):
#
#   - L0 Infrastructure: COMPLETE & TESTED (StoragePort + FileStorage; PostgreSQL deferred per ADR-0002)
#   - L1 Domain: COMPLETE & TESTED (Research entities, 12-state lifecycle, research registry)
#   - L2 Data: COMPLETE & TESTED (P01DataContract, PointInTimeView, bar validators, fixtures, Parquet adapter)
#   - L3 Quant: COMPLETE & TESTED (Causal features, signals, metrics)
#   - L4 Simulation: COMPLETE & TESTED (Execution, portfolio, risk, deterministic event loop)
#   - L5 Validation: COMPLETE & TESTED (significance, bias, multiple testing, robustness)
#   - L6 Intelligence: COMPLETE & TESTED (lineage artifacts, reports, reproduction)
#   - L7 Presentation: COMPLETE & TESTED (research CLI and human promotion gate)
#
# Repository-local acceptance and quality gates pass. Clean-container acceptance
# and external CI execution remain pending.
#
# Detailed operational matrix and verification evidence are tracked in
# PROJECT_STATUS.md.
