"""Tests for api/models.py — input validation and normalization.

normalize_risk is a field_validator on RunParams.risk_per_trade.
It converts values >= 0.1 from percentage form to decimal form (divides by 100).
Values < 0.1 are returned unchanged.
"""
import sys
import os

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.models import RunParams, RunCreate


def _normalize_risk(v: float) -> float:
    """Helper that exercises the normalize_risk validator via RunParams."""
    # We need tp_mult > sl_mult and risk_per_trade to isolate that field.
    # Use tp_mult=5.0, sl_mult=2.0 (defaults) to avoid tp_gt_sl validation error.
    params = RunParams(risk_per_trade=v)
    return params.risk_per_trade


class TestNormalizeRisk:
    def test_small_decimal_passthrough(self):
        """Values <= 0.1 are returned unchanged (already in decimal form)."""
        result = _normalize_risk(0.01)
        assert result == pytest.approx(0.01)

    def test_percentage_converted(self):
        """Values > 0.1 are divided by 100 (treated as percentage)."""
        # 1.0 % → 0.01 decimal
        result = _normalize_risk(1.0)
        assert result == pytest.approx(0.01)

    def test_10_percent_converted(self):
        """10.0 % → 0.10 decimal."""
        result = _normalize_risk(10.0)
        assert result == pytest.approx(0.10)

    def test_boundary_at_0_1_is_converted(self):
        """Exactly 0.1 triggers conversion (rule is v >= 0.1).

        0.1 is treated as 10% and converted to 0.001 decimal.
        """
        result = _normalize_risk(0.1)
        assert result == pytest.approx(0.001)

    def test_very_small_value_passthrough(self):
        """Values well below 0.1 (e.g. 0.005) pass through unchanged."""
        result = _normalize_risk(0.005)
        assert result == pytest.approx(0.005)

    def test_max_allowed_value(self):
        """100.0 is the max allowed; converts to 1.0 decimal."""
        result = _normalize_risk(100.0)
        assert result == pytest.approx(1.0)

    def test_below_min_raises(self):
        """Values below 0.0001 (ge=0.0001) should raise ValidationError."""
        with pytest.raises(ValidationError):
            RunParams(risk_per_trade=0.00001)

    def test_above_max_raises(self):
        """Values above 100.0 (le=100.0) should raise ValidationError."""
        with pytest.raises(ValidationError):
            RunParams(risk_per_trade=101.0)


class TestRunParamsValidation:
    def test_default_params_valid(self):
        params = RunParams()
        assert params.ticker == "BTC-USD"
        assert params.timeframe == "1h"
        assert params.direction == "ALL"

    def test_tp_must_be_greater_than_sl(self):
        """tp_mult must be > sl_mult."""
        with pytest.raises(ValidationError):
            RunParams(sl_mult=5.0, tp_mult=3.0)

    def test_tp_equal_to_sl_raises(self):
        with pytest.raises(ValidationError):
            RunParams(sl_mult=2.0, tp_mult=2.0)

    def test_valid_ticker_pattern(self):
        params = RunParams(ticker="ETH-USD")
        assert params.ticker == "ETH-USD"

    def test_invalid_ticker_pattern_raises(self):
        with pytest.raises(ValidationError):
            RunParams(ticker="eth-usd")  # lowercase not allowed

    def test_valid_timeframe_values(self):
        for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]:
            params = RunParams(timeframe=tf)
            assert params.timeframe == tf

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValidationError):
            RunParams(timeframe="2h")

    def test_active_hours_must_be_two_elements(self):
        with pytest.raises(ValidationError):
            RunParams(active_hours=[6])

    def test_active_hours_must_not_be_same(self):
        with pytest.raises(ValidationError):
            RunParams(active_hours=[12, 12])

    def test_active_hours_must_be_0_to_23(self):
        with pytest.raises(ValidationError):
            RunParams(active_hours=[0, 24])

    def test_direction_must_be_valid(self):
        with pytest.raises(ValidationError):
            RunParams(direction="BOTH")

    def test_mc_bars_zero_becomes_none(self):
        """mc_bars=0 should be normalized to None."""
        params = RunParams(mc_bars=0)
        assert params.mc_bars is None

    def test_mc_bars_none_stays_none(self):
        params = RunParams(mc_bars=None)
        assert params.mc_bars is None

    def test_mc_bars_positive_value_kept(self):
        params = RunParams(mc_bars=500)
        assert params.mc_bars == 500


class TestRunCreate:
    def test_default_run_create(self):
        rc = RunCreate()
        assert rc.params is not None
        assert rc.name is None
        assert rc.strategy_id is None

    def test_strategy_id_must_be_hex(self):
        with pytest.raises(ValidationError):
            RunCreate(strategy_id="not-hex!")

    def test_valid_strategy_id(self):
        rc = RunCreate(strategy_id="abcdef12")
        assert rc.strategy_id == "abcdef12"
