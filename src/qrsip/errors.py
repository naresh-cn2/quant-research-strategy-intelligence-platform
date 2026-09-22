"""QRSIP error model.

Design principle (spec 4.8): FAIL CLOSED. If required data, configuration,
validation, or tests are missing, the system must fail rather than invent
a result.

Every QRSIP error carries an actionable, structured context so failures are
visible and diagnosable (NFR-010 Failure Transparency).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ConfigurationError",
    "DataValidationError",
    "ExecutionError",
    "LineageError",
    "MetricError",
    "PointInTimeViolationError",
    "PortfolioError",
    "PromotionGateError",
    "QRSIPError",
    "ReproducibilityError",
    "RiskViolationError",
    "StrategyContractError",
    "ValidationError",
]


class QRSIPError(Exception):
    """Base class for all QRSIP errors.

    Attributes:
        context: Structured, actionable context (never contains secrets).
    """

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context

    def __str__(self) -> str:
        if not self.context:
            return self.message
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} [{rendered}]"


class ConfigurationError(QRSIPError):
    """Raised when configuration is missing, malformed, or violates a contract."""


class DataValidationError(QRSIPError):
    """Raised when a dataset violates the data contract (spec 21)."""


class PointInTimeViolationError(QRSIPError):
    """Raised when a decision attempts to access information unavailable at
    its decision timestamp (spec 17 — point-in-time safety)."""


class StrategyContractError(QRSIPError):
    """Raised when a strategy violates the strategy contract (spec 15)."""


class ExecutionError(QRSIPError):
    """Raised when the execution simulator encounters an invalid order or
    fill condition (spec 18)."""


class PortfolioError(QRSIPError):
    """Raised when portfolio accounting invariants are violated (spec 25)."""


class RiskViolationError(QRSIPError):
    """Raised when a risk limit is breached and the configured policy is to
    fail closed (spec 19)."""


class MetricError(QRSIPError):
    """Raised when a metric cannot be computed from the provided inputs."""


class ValidationError(QRSIPError):
    """Raised when a validation gate fails (spec 23)."""


class ReproducibilityError(QRSIPError):
    """Raised when reproduction of a prior experiment fails (spec 26)."""


class LineageError(QRSIPError):
    """Raised when experiment lineage is broken or incomplete (spec 4.6)."""


class PromotionGateError(QRSIPError):
    """Raised when a promotion gate is invoked without all required gates
    passing (spec FR-016)."""
