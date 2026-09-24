"""QRSIP simulation layer (L4): execution, portfolio accounting, and risk.

- :mod:`qrsip.simulation.execution` — orders, the explicit cost model, and
  deterministic fills at the next bar's open (ADR-0005).
- :mod:`qrsip.simulation.portfolio` — cash-first portfolio accounting with a
  verified equity identity (spec §25).
- :mod:`qrsip.simulation.risk` — pre-trade limit checks and the equity
  drawdown circuit breaker (spec §19).
- :mod:`qrsip.simulation.engine` — the deterministic event loop that ties the
  above together over a point-in-time dataset (spec §18, §20).

The layer never invents values: unaffordable trades are rejected, unmarked
positions refuse valuation, and every fill must occur strictly after the
decision that produced it.
"""

from __future__ import annotations

from qrsip.simulation.engine import (
    EquityPoint,
    FillRecord,
    HaltRecord,
    RejectionRecord,
    SimulationConfig,
    SimulationResult,
    run_simulation,
)
from qrsip.simulation.execution import (
    CostModel,
    Fill,
    Order,
    OrderSide,
    affordable_buy_quantity,
    execute_order,
)
from qrsip.simulation.portfolio import Portfolio, Position, RealizedEvent
from qrsip.simulation.risk import RiskCheck, RiskEngine, RiskLimits, RiskPolicy

__all__ = [
    "CostModel",
    "EquityPoint",
    "Fill",
    "FillRecord",
    "HaltRecord",
    "Order",
    "OrderSide",
    "Portfolio",
    "Position",
    "RealizedEvent",
    "RejectionRecord",
    "RiskCheck",
    "RiskEngine",
    "RiskLimits",
    "RiskPolicy",
    "SimulationConfig",
    "SimulationResult",
    "affordable_buy_quantity",
    "execute_order",
    "run_simulation",
]
