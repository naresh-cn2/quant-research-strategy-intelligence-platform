"""QRSIP quant layer (L3): deterministic, causal feature computation (spec §16).

Every function here is:

- **Pure** — no I/O, no globals, no randomness, no wall-clock time.
- **Causal** — the value at index ``i`` depends only on inputs at indices
  ``<= i``. This is what makes look-ahead structurally impossible when features
  are computed over a point-in-time history (spec §17).
- **Fail-closed** — inputs that cannot produce an honest value raise; the code
  never pads, interpolates, or invents numbers.

Alignment convention: rolling functions return one value per input element;
positions without enough history are ``None`` rather than a fabricated number.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

from qrsip.errors import MetricError, QRSIPError

__all__ = [
    "ema",
    "log_returns",
    "momentum",
    "rolling_volatility",
    "simple_returns",
    "sma",
]


def _require_window(window: int, name: str) -> None:
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise QRSIPError(f"{name} must be a positive integer", **{name: window})


def _require_len(values: Sequence[float], minimum: int, name: str) -> None:
    if len(values) < minimum:
        raise MetricError(
            "not enough values to compute",
            series=name,
            provided=len(values),
            required=minimum,
        )


def sma(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    """Simple moving average aligned to ``values``; ``None`` before warm-up.

    Position ``i`` uses only ``values[i - window + 1 .. i]`` — causal by
    construction.
    """
    _require_window(window, "window")
    out: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        out.append(running / window if index >= window - 1 else None)
    return tuple(out)


def ema(values: Sequence[float], span: int) -> tuple[float | None, ...]:
    """Exponential moving average seeded with the first value; ``alpha=2/(span+1)``.

    Uses only past inputs at each position (causal). ``values`` must be
    non-empty.
    """
    _require_window(span, "span")
    _require_len(values, 1, "ema_input")
    alpha = 2.0 / (span + 1.0)
    out: list[float | None] = []
    previous: float | None = None
    for value in values:
        previous = value if previous is None else (alpha * value + (1.0 - alpha) * previous)
        out.append(previous)
    return tuple(out)


def simple_returns(closes: Sequence[float]) -> tuple[float, ...]:
    """``c[i]/c[i-1] - 1``; length ``n - 1``. Fails closed on short/zero input."""
    _require_len(closes, 2, "closes")
    result: list[float] = []
    for previous, current in itertools.pairwise(closes):
        if previous == 0.0:
            raise MetricError("cannot compute return from a zero price", index=len(result))
        result.append(current / previous - 1.0)
    return tuple(result)


def log_returns(closes: Sequence[float]) -> tuple[float, ...]:
    """``ln(c[i]/c[i-1])``; length ``n - 1``. Requires strictly positive prices."""
    _require_len(closes, 2, "closes")
    result: list[float] = []
    for index, (previous, current) in enumerate(itertools.pairwise(closes)):
        if previous <= 0.0 or current <= 0.0:
            raise MetricError("log return requires positive prices", index=index)
        result.append(math.log(current / previous))
    return tuple(result)


def rolling_volatility(
    closes: Sequence[float],
    window: int,
    *,
    periods_per_year: int = 252,
) -> tuple[float | None, ...]:
    """Annualized sample stdev of simple returns, aligned to ``closes``.

    Position ``i`` uses returns of ``closes[i - window .. i]`` (which span
    closes up to index ``i``) — causal. ``None`` before warm-up. A zero-variance
    window yields ``0.0`` (an honest fact, not an undefined ratio).
    """
    _require_window(window, "window")
    if periods_per_year < 1:
        raise QRSIPError("periods_per_year must be positive", periods_per_year=periods_per_year)
    returns = simple_returns(closes)
    out: list[float | None] = [None] * len(closes)
    for index in range(window, len(closes)):
        chunk = returns[index - window : index]
        mean = sum(chunk) / window
        variance = sum((r - mean) ** 2 for r in chunk) / (window - 1) if window > 1 else 0.0
        out[index] = math.sqrt(variance) * math.sqrt(float(periods_per_year))
    return tuple(out)


def momentum(closes: Sequence[float], lookback: int) -> tuple[float | None, ...]:
    """``c[i]/c[i-lookback] - 1`` aligned to ``closes``; ``None`` before warm-up."""
    _require_window(lookback, "lookback")
    out: list[float | None] = [None] * len(closes)
    for index in range(lookback, len(closes)):
        base = closes[index - lookback]
        if base == 0.0:
            raise MetricError("cannot compute momentum from a zero price", index=index)
        out[index] = closes[index] / base - 1.0
    return tuple(out)
