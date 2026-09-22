"""
Tests for qrsip.errors — error model (fail-closed design, spec 4.8, NFR-010).
"""

from __future__ import annotations

import pytest

from qrsip.errors import (
    ConfigurationError,
    DataValidationError,
    ExecutionError,
    LineageError,
    MetricError,
    PointInTimeViolationError,
    PortfolioError,
    PromotionGateError,
    QRSIPError,
    ReproducibilityError,
    RiskViolationError,
    StrategyContractError,
    ValidationError,
)


class TestQRSIPError:
    def test_base_error_carries_message(self) -> None:
        err = QRSIPError("something went wrong")
        assert err.message == "something went wrong"
        assert str(err) == "something went wrong"

    def test_base_error_carries_context(self) -> None:
        err = QRSIPError("failed", path="/tmp/x", code=42)
        assert err.message == "failed"
        assert err.context == {"path": "/tmp/x", "code": 42}
        rendered = str(err)
        assert "path=" in rendered
        assert "code=42" in rendered

    def test_base_error_is_exception(self) -> None:
        err = QRSIPError("oh no")
        with pytest.raises(QRSIPError):
            raise err


class TestConfigurationError:
    def test_configuration_error_inherits(self) -> None:
        err = ConfigurationError("bad config", path="/etc/qrsip.yaml")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, ConfigurationError)
        assert err.context["path"] == "/etc/qrsip.yaml"


class TestDataValidationError:
    def test_data_validation_error_inherits(self) -> None:
        err = DataValidationError("invalid OHLC", field="high", value=-1.0)
        assert isinstance(err, QRSIPError)
        assert isinstance(err, DataValidationError)
        assert err.context["field"] == "high"


class TestPointInTimeViolationError:
    def test_point_in_time_violation_error_inherits(self) -> None:
        err = PointInTimeViolationError(
            "future data accessed",
            decision_timestamp="2020-01-01",
            data_timestamp="2020-01-02",
        )
        assert isinstance(err, QRSIPError)
        assert isinstance(err, PointInTimeViolationError)
        assert err.context["decision_timestamp"] == "2020-01-01"


class TestStrategyContractError:
    def test_strategy_contract_error_inherits(self) -> None:
        err = StrategyContractError("strategy accessed database directly")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, StrategyContractError)


class TestExecutionError:
    def test_execution_error_inherits(self) -> None:
        err = ExecutionError("fill without order", order_id="O-001")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, ExecutionError)
        assert err.context["order_id"] == "O-001"


class TestPortfolioError:
    def test_portfolio_error_inherits(self) -> None:
        err = PortfolioError("invariant violated", cash=100.0, equity=90.0)
        assert isinstance(err, QRSIPError)
        assert isinstance(err, PortfolioError)
        assert err.context["cash"] == 100.0


class TestRiskViolationError:
    def test_risk_violation_error_inherits(self) -> None:
        err = RiskViolationError("daily loss limit breached", limit=0.03, realized=0.05)
        assert isinstance(err, QRSIPError)
        assert isinstance(err, RiskViolationError)
        assert err.context["limit"] == 0.03


class TestMetricError:
    def test_metric_error_inherits(self) -> None:
        err = MetricError("cannot compute Sharpe", reason="no trades")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, MetricError)
        assert err.context["reason"] == "no trades"


class TestValidationError:
    def test_validation_error_inherits(self) -> None:
        err = ValidationError("bias check failed", check="lookahead", detail="future data")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, ValidationError)
        assert err.context["check"] == "lookahead"


class TestReproducibilityError:
    def test_reproducibility_error_inherits(self) -> None:
        err = ReproducibilityError("reproduction mismatch", metric="total_return", tolerance=1e-6)
        assert isinstance(err, QRSIPError)
        assert isinstance(err, ReproducibilityError)
        assert err.context["tolerance"] == 1e-6


class TestLineageError:
    def test_lineage_error_inherits(self) -> None:
        err = LineageError("missing dataset checksum", experiment_id="EXP-0001")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, LineageError)
        assert err.context["experiment_id"] == "EXP-0001"


class TestPromotionGateError:
    def test_promotion_gate_error_inherits(self) -> None:
        err = PromotionGateError("risk review not passed", gate="risk_review")
        assert isinstance(err, QRSIPError)
        assert isinstance(err, PromotionGateError)
        assert err.context["gate"] == "risk_review"


class TestErrorHierarchy:
    def test_all_errors_share_base(self) -> None:
        errors = [
            ConfigurationError("x"),
            DataValidationError("x"),
            PointInTimeViolationError("x"),
            StrategyContractError("x"),
            ExecutionError("x"),
            PortfolioError("x"),
            RiskViolationError("x"),
            MetricError("x"),
            ValidationError("x"),
            ReproducibilityError("x"),
            LineageError("x"),
            PromotionGateError("x"),
        ]
        for err in errors:
            assert isinstance(err, QRSIPError)
