"""QRSIP signal layer (L3): deterministic strategy signal computation (spec §16).

A *signal* is the strategy's target state decided from information available at
the bar close of timestamp ``T``. The simulation layer (L4) turns signals into
orders that fill at the next bar's open (ADR-0005). Nothing in this module
touches prices, portfolios, or clocks — given the same close history it always
returns the same signal (spec §16 determinism).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol, runtime_checkable

from qrsip.errors import QRSIPError
from qrsip.quant.features import sma

__all__ = [
    "ConstantStrategy",
    "MovingAverageCrossStrategy",
    "Signal",
    "SignalStrategy",
]


class Signal(IntEnum):
    """Target position state decided at bar close."""

    SHORT = -1
    FLAT = 0
    LONG = 1


@runtime_checkable
class SignalStrategy(Protocol):
    """Executable strategy contract: close history in, target signal out."""

    def target_signal(self, closes: Sequence[float]) -> Signal:
        """Return the target state given closes up to and including now.

        Implementations must be causal and deterministic: the return value may
        depend only on the prefix passed in.
        """
        ...


@dataclass(frozen=True, slots=True)
class ConstantStrategy:
    """Always targets the same signal. Useful as a control and in tests."""

    signal: Signal = Signal.FLAT

    def target_signal(self, closes: Sequence[float]) -> Signal:
        return self.signal


@dataclass(frozen=True, slots=True)
class MovingAverageCrossStrategy:
    """Fast/slow SMA crossover.

    - ``len(closes) < slow`` → :attr:`Signal.FLAT` (insufficient history; fail
      closed rather than act on a partial estimate).
    - fast SMA > slow SMA → :attr:`Signal.LONG`
    - fast SMA < slow SMA → :attr:`Signal.SHORT` when ``allow_short`` else
      :attr:`Signal.FLAT`
    - equal → :attr:`Signal.FLAT` (no trade on an exact tie)
    """

    fast: int = 20
    slow: int = 50
    allow_short: bool = False

    def __post_init__(self) -> None:
        for name, value in (("fast", self.fast), ("slow", self.slow)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise QRSIPError(f"{name} window must be a positive integer", **{name: value})
        if self.slow <= self.fast:
            raise QRSIPError(
                "slow window must exceed fast window",
                fast=self.fast,
                slow=self.slow,
            )

    def target_signal(self, closes: Sequence[float]) -> Signal:
        if len(closes) < self.slow:
            return Signal.FLAT
        fast_series = sma(closes, self.fast)
        slow_series = sma(closes, self.slow)
        fast_value = fast_series[-1]
        slow_value = slow_series[-1]
        if fast_value is None or slow_value is None:  # unreachable by construction
            raise QRSIPError(
                "moving average unavailable despite sufficient history",
                length=len(closes),
                fast=self.fast,
                slow=self.slow,
            )
        if fast_value > slow_value:
            return Signal.LONG
        if fast_value < slow_value:
            return Signal.SHORT if self.allow_short else Signal.FLAT
        return Signal.FLAT
