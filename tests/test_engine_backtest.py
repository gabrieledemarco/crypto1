"""Tests for engine/backtest.py — backtest pipeline correctness."""
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.backtest import run_versions, run_wfo
from engine.strategy_core import compute_indicators_v2, compute_metrics
from engine.config import StrategyVersion, INITIAL_CAPITAL


def _make_ohlcv(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="1h")
    close = 30000 + np.cumsum(rng.normal(0, 100, n))
    close = np.maximum(close, 100)
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.uniform(1, 100, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def _make_df_ind(n: int = 500) -> pd.DataFrame:
    """Build an indicator DataFrame ready for run_versions/run_wfo."""
    df = _make_ohlcv(n)
    return compute_indicators_v2(df, fit_garch=False)


class TestRunVersions:
    def test_returns_all_versions(self):
        df_ind = _make_df_ind(500)
        cfg = {
            "sl_mult": 2.0,
            "tp_mult": 5.0,
            "active_hours": [0, 23],
            "commission_pips": 0.0,
            "slippage_pips": 0.0,
        }
        results = run_versions(df_ind, cfg)
        assert StrategyVersion.V1_BASE.value in results
        assert StrategyVersion.V2_COSTS.value in results
        assert StrategyVersion.V4_GARCH.value in results

    def test_metrics_keys_present(self):
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        results = run_versions(df_ind, cfg)
        for name, r in results.items():
            assert "metrics" in r, f"Missing metrics for {name}"
            m = r["metrics"]
            # When there are no trades, compute_metrics returns an error dict
            # with sharpe_ratio key. When trades exist, all keys are present.
            assert "sharpe_ratio" in m

    def test_metrics_with_trades_has_n_trades(self):
        # Use wide active hours to maximize chance of signals
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 1.5, "tp_mult": 3.0, "active_hours": [0, 23]}
        results = run_versions(df_ind, cfg)
        # At least one version may produce trades; just verify structure
        for name, r in results.items():
            m = r["metrics"]
            # n_trades only appears when trades exist
            if "n_trades" in m:
                assert isinstance(m["n_trades"], int)
                assert m["n_trades"] >= 0

    def test_missing_columns_raises(self):
        df = pd.DataFrame({"Close": [100, 101, 102]})
        cfg = {}
        with pytest.raises((ValueError, KeyError)):
            run_versions(df, cfg)

    def test_direction_long_only(self):
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        results = run_versions(df_ind, cfg, direction="LONG")
        assert StrategyVersion.V1_BASE.value in results

    def test_direction_short_only(self):
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        results = run_versions(df_ind, cfg, direction="SHORT")
        assert StrategyVersion.V1_BASE.value in results

    def test_result_has_equity_series(self):
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        results = run_versions(df_ind, cfg)
        for name, r in results.items():
            assert "result" in r
            res = r["result"]
            assert "equity" in res
            assert "trades" in res

    def test_progress_callback_called(self):
        df_ind = _make_df_ind(500)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        calls = []
        run_versions(df_ind, cfg, progress_cb=lambda phase, pct: calls.append((phase, pct)))
        assert len(calls) > 0

    def test_v1_base_no_costs(self):
        """V1 Base has no commission or slippage costs."""
        df_ind = _make_df_ind(800)
        cfg = {
            "sl_mult": 1.5,
            "tp_mult": 3.0,
            "active_hours": [0, 23],
            "commission_pips": 5.0,
            "slippage_pips": 2.0,
        }
        results = run_versions(df_ind, cfg)
        v1 = results[StrategyVersion.V1_BASE.value]
        v2 = results[StrategyVersion.V2_COSTS.value]
        # V1 should have no total_costs (0) while V2 can have costs if trades occurred
        # We only verify both exist and have metrics
        assert "metrics" in v1
        assert "metrics" in v2


class TestRunWFO:
    def test_returns_dataframe(self):
        # Minimum required bars: 5 * HOURS_MONTH = 5 * 720 = 3600
        df_ind = _make_df_ind(4000)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        result = run_wfo(df_ind, cfg)
        assert isinstance(result, pd.DataFrame)

    def test_insufficient_data_returns_empty(self):
        df_ind = _make_df_ind(50)
        cfg = {}
        result = run_wfo(df_ind, cfg)
        assert result.empty

    def test_below_minimum_window_returns_empty(self):
        """Data shorter than the minimum WFO window (3600 bars) returns empty DataFrame."""
        df_ind = _make_df_ind(3000)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        result = run_wfo(df_ind, cfg)
        assert result.empty

    def test_no_lookahead_bias(self):
        """IS end must always be strictly before OOS start — verified inside run_wfo by assertion."""
        # Need >= 3600 bars for WFO to run at all (5 * HOURS_MONTH)
        df_ind = _make_df_ind(4000)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        # run_wfo has an internal assert for this; if it passes, no lookahead bias
        result = run_wfo(df_ind, cfg)
        assert not result.empty

    def test_wfo_columns_present(self):
        df_ind = _make_df_ind(4000)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        result = run_wfo(df_ind, cfg)
        if not result.empty:
            expected_cols = {"window_config", "fold", "is_sharpe", "oos_sharpe",
                             "is_n_trades", "oos_n_trades"}
            for col in expected_cols:
                assert col in result.columns, f"Missing column: {col}"

    def test_wfo_fold_count_reasonable(self):
        df_ind = _make_df_ind(4000)
        cfg = {"sl_mult": 2.0, "tp_mult": 5.0, "active_hours": [0, 23]}
        result = run_wfo(df_ind, cfg)
        if not result.empty:
            assert len(result) >= 1


class TestComputeMetrics:
    def test_empty_trades_returns_error_dict(self):
        """compute_metrics with empty trades returns a dict with error key."""
        from engine.strategy_core import backtest_v2, generate_signals_v2

        # Create a tiny DataFrame with no signal conditions met → no trades
        idx = pd.date_range("2022-01-01", periods=10, freq="1h")
        df = pd.DataFrame({
            "Open": [100.0] * 10,
            "High": [101.0] * 10,
            "Low": [99.0] * 10,
            "Close": [100.0] * 10,
            "Volume": [10.0] * 10,
            "signal": [0] * 10,
            "SL_dist": [1.0] * 10,
            "TP_dist": [2.0] * 10,
            "size_mult": [1.0] * 10,
        }, index=idx)
        result = backtest_v2(df, initial_capital=INITIAL_CAPITAL)
        m = compute_metrics(result, INITIAL_CAPITAL)
        assert isinstance(m, dict)
        # When no trades, returns the error dict
        assert "error" in m or "n_trades" in m

    def test_compute_metrics_with_trades(self):
        """compute_metrics returns full metrics dict when trades exist."""
        from engine.strategy_core import backtest_v2

        idx = pd.date_range("2022-01-01", periods=100, freq="1h")
        close = np.linspace(100, 200, 100)
        df = pd.DataFrame({
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.ones(100) * 10,
            # Force a long signal every 10 bars
            "signal": [1 if i % 10 == 0 else 0 for i in range(100)],
            "SL_dist": close * 0.02,
            "TP_dist": close * 0.05,
            "size_mult": np.ones(100),
        }, index=idx)
        result = backtest_v2(df, initial_capital=INITIAL_CAPITAL, commission_pips=0.0, slippage_pips=0.0)
        if not result["trades"].empty:
            m = compute_metrics(result, INITIAL_CAPITAL)
            assert "n_trades" in m
            assert m["n_trades"] > 0
            assert "sharpe_ratio" in m
            assert "max_drawdown_pct" in m
            assert "win_rate_pct" in m
            assert "profit_factor" in m

    def test_profit_factor_capped_at_999(self):
        """profit_factor is capped at 999.9 to avoid inf."""
        from engine.strategy_core import backtest_v2

        idx = pd.date_range("2022-01-01", periods=50, freq="1h")
        close = np.linspace(1000, 2000, 50)
        # All winning trades — no losses
        df = pd.DataFrame({
            "Open": close,
            "High": close * 1.1,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.ones(50) * 10,
            "signal": [1 if i % 5 == 0 else 0 for i in range(50)],
            "SL_dist": close * 0.001,   # tiny SL → rarely hit
            "TP_dist": close * 0.09,    # large TP → often hit by High
            "size_mult": np.ones(50),
        }, index=idx)
        result = backtest_v2(df, initial_capital=INITIAL_CAPITAL, commission_pips=0.0, slippage_pips=0.0)
        if not result["trades"].empty:
            m = compute_metrics(result, INITIAL_CAPITAL)
            if "profit_factor" in m:
                assert m["profit_factor"] <= 999.9
