"""
Tests for engine/nautilus_engine.py — NautilusTrader integration.

Tests run in two modes:
  1. nautilus_trader installed: full integration tests
  2. nautilus_trader missing:   unit tests for is_enabled() / graceful fallback
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.nautilus_engine import NAUTILUS_AVAILABLE, is_enabled


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="1h")
    close = 30_000 + np.cumsum(rng.normal(0, 150, n))
    close = np.maximum(close, 500.0)
    high = close * (1 + rng.uniform(0.001, 0.012, n))
    low = close * (1 - rng.uniform(0.001, 0.012, n))
    open_ = close * (1 + rng.normal(0, 0.004, n))
    volume = rng.uniform(10, 500, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def _make_df_ind(n: int = 600) -> pd.DataFrame:
    from engine.strategy_core import compute_indicators_v2
    return compute_indicators_v2(_make_ohlcv(n), fit_garch=False)


def _base_cfg() -> dict:
    return {
        "ticker": "BTC-USD",
        "timeframe": "1h",
        "initial_capital": 10_000.0,
        "sl_mult": 1.5,
        "tp_mult": 3.0,
        "active_hours": [0, 23],
        "risk_per_trade": 0.01,
        "commission": 0.0004,
        "leverage": 1.0,
        "direction": "ALL",
        "position_size_method": "risk_pct",
        "use_garch_filter": False,
    }


# ── Availability and feature flag ─────────────────────────────────────────────

class TestAvailability:
    def test_is_enabled_false_without_env(self, monkeypatch):
        monkeypatch.delenv("USE_NAUTILUS_ENGINE", raising=False)
        assert is_enabled() is False

    def test_is_enabled_true_requires_nautilus(self, monkeypatch):
        monkeypatch.setenv("USE_NAUTILUS_ENGINE", "1")
        # can only be True if nautilus is actually installed
        result = is_enabled()
        assert result == NAUTILUS_AVAILABLE

    def test_is_enabled_accepts_true_string(self, monkeypatch):
        monkeypatch.setenv("USE_NAUTILUS_ENGINE", "true")
        assert is_enabled() == NAUTILUS_AVAILABLE

    def test_is_enabled_rejects_random_string(self, monkeypatch):
        monkeypatch.setenv("USE_NAUTILUS_ENGINE", "yes_please")
        assert is_enabled() is False


# ── Import-time safety ────────────────────────────────────────────────────────

class TestImportSafety:
    def test_module_importable(self):
        import engine.nautilus_engine as m
        assert hasattr(m, "NAUTILUS_AVAILABLE")
        assert hasattr(m, "is_enabled")
        assert hasattr(m, "run_nautilus_backtest")

    def test_run_raises_without_nautilus(self):
        if NAUTILUS_AVAILABLE:
            pytest.skip("nautilus_trader is installed")
        from engine.nautilus_engine import run_nautilus_backtest
        with pytest.raises(RuntimeError, match="nautilus_trader"):
            run_nautilus_backtest(_make_df_ind(), _base_cfg())


# ── Full integration (only when nautilus_trader is installed) ─────────────────

@pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")
class TestNautilusBacktest:
    def test_returns_expected_keys(self):
        from engine.nautilus_engine import run_nautilus_backtest
        result = run_nautilus_backtest(_make_df_ind(), _base_cfg())
        assert "trades" in result
        assert "equity" in result
        assert "final_capital" in result

    def test_equity_is_series(self):
        from engine.nautilus_engine import run_nautilus_backtest
        result = run_nautilus_backtest(_make_df_ind(), _base_cfg())
        assert isinstance(result["equity"], pd.Series)
        assert len(result["equity"]) > 0

    def test_final_capital_is_positive_float(self):
        from engine.nautilus_engine import run_nautilus_backtest
        result = run_nautilus_backtest(_make_df_ind(), _base_cfg())
        assert isinstance(result["final_capital"], float)
        assert result["final_capital"] > 0

    def test_trades_dataframe_columns(self):
        from engine.nautilus_engine import run_nautilus_backtest
        result = run_nautilus_backtest(_make_df_ind(), _base_cfg())
        trades = result["trades"]
        if not trades.empty:
            required = {"entry_time", "exit_time", "direction", "entry_price",
                        "exit_price", "qty", "pnl", "exit_reason"}
            assert required.issubset(set(trades.columns))

    def test_direction_long_only(self):
        from engine.nautilus_engine import run_nautilus_backtest
        cfg = {**_base_cfg(), "direction": "LONG"}
        result = run_nautilus_backtest(_make_df_ind(), cfg)
        trades = result["trades"]
        if not trades.empty:
            assert (trades["direction"] == "LONG").all()

    def test_direction_short_only(self):
        from engine.nautilus_engine import run_nautilus_backtest
        cfg = {**_base_cfg(), "direction": "SHORT"}
        result = run_nautilus_backtest(_make_df_ind(), cfg)
        trades = result["trades"]
        if not trades.empty:
            assert (trades["direction"] == "SHORT").all()

    def test_compatible_with_compute_metrics(self):
        from engine.nautilus_engine import run_nautilus_backtest
        from engine.strategy_core import compute_metrics
        result = run_nautilus_backtest(_make_df_ind(), _base_cfg())
        if result["trades"].empty:
            pytest.skip("no trades generated in synthetic data")
        metrics = compute_metrics(result, 10_000.0)
        assert "sharpe_ratio" in metrics
        assert "n_trades" in metrics
        assert isinstance(metrics["sharpe_ratio"], float)

    def test_empty_df_raises(self):
        from engine.nautilus_engine import run_nautilus_backtest
        with pytest.raises(ValueError):
            run_nautilus_backtest(pd.DataFrame(), _base_cfg())

    def test_different_timeframes(self):
        from engine.nautilus_engine import run_nautilus_backtest
        for tf in ("1h", "4h", "1d"):
            cfg = {**_base_cfg(), "timeframe": tf}
            df = compute_indicators_v2 = None
            from engine.strategy_core import compute_indicators_v2
            n = 300 if tf == "1d" else 600
            ohlcv = _make_ohlcv(n)
            idx = pd.date_range("2023-01-01", periods=n, freq={"1h": "1h", "4h": "4h", "1d": "1D"}[tf])
            ohlcv.index = idx
            df_ind = compute_indicators_v2(ohlcv, fit_garch=False)
            result = run_nautilus_backtest(df_ind, cfg)
            assert "equity" in result

    def test_registry_cleanup(self):
        """Signal registry must be empty after backtest (no memory leaks)."""
        from engine.nautilus_engine import run_nautilus_backtest, _SIGNAL_REGISTRY
        initial_len = len(_SIGNAL_REGISTRY)
        run_nautilus_backtest(_make_df_ind(), _base_cfg())
        assert len(_SIGNAL_REGISTRY) == initial_len
