"""QRSIP research lifecycle states (spec section 14).

DRAFT -> SPECIFIED -> DATA_READY -> IMPLEMENTED -> TESTED -> BACKTESTED
-> VALIDATED -> ROBUSTNESS_TESTED -> REVIEWED
-> {REJECTED | INVESTIGATE | PROMOTION_CANDIDATE}

No silent skipping. Promotion requires human approval (FR-016).
"""

from __future__ import annotations

from enum import StrEnum

from qrsip.errors import QRSIPError

__all__ = [
    "TERMINAL_STATES",
    "LifecycleViolation",
    "ResearchLifecycleState",
    "allowed_transitions",
    "can_transition",
    "require_transition",
]


class LifecycleViolation(QRSIPError):  # noqa: N818 - "Violation" is the domain term
    """Raised when a lifecycle transition would skip or reverse a state."""


class ResearchLifecycleState(StrEnum):
    """Canonical research lifecycle states."""

    DRAFT = "DRAFT"
    SPECIFIED = "SPECIFIED"
    DATA_READY = "DATA_READY"
    IMPLEMENTED = "IMPLEMENTED"
    TESTED = "TESTED"
    BACKTESTED = "BACKTESTED"
    VALIDATED = "VALIDATED"
    ROBUSTNESS_TESTED = "ROBUSTNESS_TESTED"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    INVESTIGATE = "INVESTIGATE"
    PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"


TERMINAL_STATES = frozenset(
    {
        ResearchLifecycleState.REJECTED,
        ResearchLifecycleState.INVESTIGATE,
        ResearchLifecycleState.PROMOTION_CANDIDATE,
    }
)

_ALLOWED: dict[ResearchLifecycleState, frozenset[ResearchLifecycleState]] = {
    ResearchLifecycleState.DRAFT: frozenset({ResearchLifecycleState.SPECIFIED}),
    ResearchLifecycleState.SPECIFIED: frozenset({ResearchLifecycleState.DATA_READY}),
    ResearchLifecycleState.DATA_READY: frozenset({ResearchLifecycleState.IMPLEMENTED}),
    ResearchLifecycleState.IMPLEMENTED: frozenset({ResearchLifecycleState.TESTED}),
    ResearchLifecycleState.TESTED: frozenset({ResearchLifecycleState.BACKTESTED}),
    ResearchLifecycleState.BACKTESTED: frozenset({ResearchLifecycleState.VALIDATED}),
    ResearchLifecycleState.VALIDATED: frozenset({ResearchLifecycleState.ROBUSTNESS_TESTED}),
    ResearchLifecycleState.ROBUSTNESS_TESTED: frozenset({ResearchLifecycleState.REVIEWED}),
    ResearchLifecycleState.REVIEWED: frozenset(
        {
            ResearchLifecycleState.REJECTED,
            ResearchLifecycleState.INVESTIGATE,
            ResearchLifecycleState.PROMOTION_CANDIDATE,
        }
    ),
    ResearchLifecycleState.REJECTED: frozenset(),
    ResearchLifecycleState.INVESTIGATE: frozenset(),
    ResearchLifecycleState.PROMOTION_CANDIDATE: frozenset(),
}


def allowed_transitions(state: ResearchLifecycleState) -> frozenset[ResearchLifecycleState]:
    """Return the set of states directly reachable from ``state``."""
    return _ALLOWED[state]


def can_transition(current: ResearchLifecycleState, target: ResearchLifecycleState) -> bool:
    """Return True iff ``target`` is directly reachable from ``current``.

    No silent skipping: a transition is legal only when it is the immediate
    successor in the canonical chain (or one of the three terminal outcomes
    from REVIEWED). Terminal states have no outgoing transitions.
    """
    return target in _ALLOWED[current]


def require_transition(current: ResearchLifecycleState, target: ResearchLifecycleState) -> None:
    """Raise :class:`LifecycleViolation` unless the transition is legal.

    This is the fail-closed gate used by orchestration code: a state may only
    move to its immediate successor in the canonical chain, and terminal states
    cannot move at all (spec §14: no state may be skipped).
    """
    if current == target:
        raise LifecycleViolation("no-op transition is not a state change", current=current, target=target)
    if not can_transition(current, target):
        allowed = sorted(state.value for state in _ALLOWED[current])
        raise LifecycleViolation(
            "illegal lifecycle transition",
            current=current.value,
            target=target.value,
            allowed=allowed,
        )
