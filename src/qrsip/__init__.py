"""QRSIP — Quantitative Research & Strategy Intelligence Platform.

P02: a research-grade, deterministic and auditable system for transforming
quantitative trading hypotheses into reproducible experiments, simulated
portfolios, risk measurements, robustness analysis, bias validation, and
evidence-backed research reports.

Architecture layers (dependencies flow downward only):

    L7 Presentation      CLI / reports
    L6 Intelligence      experiment orchestration, comparison, promotion gates
    L5 Validation        bias / robustness / statistical validation
    L4 Simulation        execution / portfolio / risk
    L3 Quant             features / signals / metrics
    L2 Data              P01 adapter / dataset contracts / point-in-time access
    L1 Domain            research entities
    L0 Infrastructure    configuration / logging / filesystem / CI
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
