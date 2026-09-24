"""QRSIP risk engine (L4: simulation → risk; spec §19).

Limits are explicit configuration, checked before orders are queued and
continuously against the equity curve:

- ``max_order_notional`` — a single order's notional at decision price.
- ``max_position_notional`` — projected position notional after the fill.
- ``max_gross_exposure`` — projected gross exposure as a fraction of equity.
- ``max_drawdown`` — equity circuit breaker: halt when the peak-to-trough
  decline reaches this fraction (checked after every mark).

Two response policies (spec §19):

- ``REJECT`` (default): the offending order is dropped with recorded reasons;
  existing positions are untouched and research continues.
- ``FAIL_CLOSED``: :class:`~qrsip.errors.RiskViolationError` is raised instead
  — for pipelines that must not silently continue past a breach.

A drawdown breach always halts new risk-taking (``halted`` in the engine
result), and pending orders are cancelled — halting conservatively is the
fail-closed behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from qrsip.errors import RiskViolationError
from qrsip.simulation.execution import Order, OrderSide
from qrsip.simulation.portfolio import Portfolio

__all__ = ["RiskCheck", "RiskEngine", "RiskLimits", "RiskPolicy"]


class RiskPolicy:
    """Namespace for the two supported breach responses."""

    REJECT = "REJECT"
    FAIL_CLOSED = "FAIL_CLOSED"

    _VALID = frozenset({REJECT, FAIL_CLOSED})

    def __init__(self, value: str) -> None:
        if value not in self._VALID:
            raise RiskViolationError(
                "unknown risk policy", value=value, allowed=sorted(self._VALID)
            )
        self.value = value

    def __repr__(self) -> str:
        return f"RiskPolicy({self.value!r})"


def _optional_positive(name: str, value: float | None) -> None:
    if value is None:
        return
    if not math.isfinite(value) or value <= 0.0:
        raise RiskViolationError(f"{name} must be finite and positive when set", **{name: value})


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Validated risk limits; ``None`` disables that check."""

    max_order_notional: float | None = None
    max_position_notional: float | None = None
    max_gross_exposure: float | None = None  # fraction of equity
    max_drawdown: float | None = None  # fraction, e.g. 0.25 = 25% peak-to-trough

    def __post_init__(self) -> None:
        _optional_positive("max_order_notional", self.max_order_notional)
        _optional_positive("max_position_notional", self.max_position_notional)
        _optional_positive("max_gross_exposure", self.max_gross_exposure)
        _optional_positive("max_drawdown", self.max_drawdown)

    def to_dict(self) -> dict[str, float | None]:
        """JSON-serializable snapshot for experiment configs."""
        return {
            "max_order_notional": self.max_order_notional,
            "max_position_notional": self.max_position_notional,
            "max_gross_exposure": self.max_gross_exposure,
            "max_drawdown": self.max_drawdown,
        }


@dataclass(frozen=True, slots=True)
class RiskCheck:
    """Outcome of a pre-trade risk check; ``reasons`` explains any rejection."""

    approved: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def approve(cls) -> RiskCheck:
        return cls(approved=True)

    @classmethod
    def reject(cls, *reasons: str) -> RiskCheck:
        return cls(approved=False, reasons=tuple(reasons))


class RiskEngine:
    """Pre-trade limit checks and the equity circuit breaker (spec §19).

    ``policy`` decides what happens when a check fails:

    - ``RiskPolicy.REJECT`` — return a rejected :class:`RiskCheck` with reasons;
      the engine records the rejection and research continues.
    - ``RiskPolicy.FAIL_CLOSED`` — raise :class:`RiskViolationError`.
    """

    def __init__(self, limits: RiskLimits, *, policy: str = RiskPolicy.REJECT) -> None:
        if policy not in RiskPolicy._VALID:
            raise RiskViolationError(
                "unknown risk policy", value=policy, allowed=sorted(RiskPolicy._VALID)
            )
        self.limits = limits
        self.policy = policy

    def check_order(self, order: Order, *, portfolio: Portfolio) -> RiskCheck:
        """Evaluate ``order`` against every configured limit (fail closed).

        The instrument's mark must already be present on the portfolio (the
        engine marks to the bar close before deciding); a missing mark raises
        :class:`RiskViolationError` because an unverifiable trade is a breach.
        """
        mark = portfolio.marks.get(order.instrument)
        if mark is None or not math.isfinite(mark) or mark <= 0.0:
            message = "no valid mark for instrument; risk cannot be verified"
            if self.policy == RiskPolicy.FAIL_CLOSED:
                raise RiskViolationError(message, instrument=order.instrument, mark=mark)
            return RiskCheck.reject(message)

        reasons: list[str] = []
        order_notional = order.quantity * mark
        limits = self.limits

        if limits.max_order_notional is not None and order_notional > limits.max_order_notional:
            reasons.append(
                f"order notional {order_notional:.2f} exceeds max_order_notional "
                f"{limits.max_order_notional:.2f}"
            )

        current = portfolio.position(order.instrument).quantity
        signed = order.quantity if order.side is OrderSide.BUY else -order.quantity
        projected_quantity = current + signed
        projected_notional = abs(projected_quantity) * mark

        if (
            limits.max_position_notional is not None
            and projected_notional > limits.max_position_notional
        ):
            reasons.append(
                f"projected position notional {projected_notional:.2f} exceeds "
                f"max_position_notional {limits.max_position_notional:.2f}"
            )

        if limits.max_gross_exposure is not None:
            equity = portfolio.equity()
            if equity <= 0.0:
                reasons.append(f"equity {equity:.2f} is not positive; gross exposure unverifiable")
            else:
                gross = portfolio.gross_exposure() - abs(current * mark) + projected_notional
                ratio = gross / equity
                if ratio > limits.max_gross_exposure:
                    reasons.append(
                        f"projected gross exposure {ratio:.4f} exceeds "
                        f"max_gross_exposure {limits.max_gross_exposure:.4f}"
                    )

        if not reasons:
            return RiskCheck.approve()

        if self.policy == RiskPolicy.FAIL_CLOSED:
            raise RiskViolationError(
                "risk limit breached under FAIL_CLOSED policy",
                reasons=reasons,
                instrument=order.instrument,
                decision_time=order.decision_time.isoformat(),
            )
        return RiskCheck.reject(*reasons)

    def drawdown_breach(self, *, equity: float, peak_equity: float) -> bool:
        """True when the peak-to-trough decline reaches ``max_drawdown``.

        A non-positive peak is treated as a breach (an equity curve that cannot
        be measured against its peak has already destroyed the limit's meaning).
        """
        limit = self.limits.max_drawdown
        if limit is None:
            return False
        if peak_equity <= 0.0 or not math.isfinite(equity):
            return True
        # Tolerance per ADR-0006: float imprecision at exact boundary
        # (e.g. 80000/100000 - 1.0 = -0.19999…96, not -0.20).
        return (equity / peak_equity - 1.0) <= -limit + 1e-9
