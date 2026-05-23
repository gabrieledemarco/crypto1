"""
api/mcp_server.py — Pareto Quant MCP Server
============================================
Exposes engine computation functions as MCP tools for LLM clients.
Run standalone: python -m api.mcp_server
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pandas as pd
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pareto-quant", instructions=(
    "Pareto Terminal quantitative analysis tools. "
    "Use these tools to run backtests, Monte Carlo simulations, "
    "and statistical analysis on crypto assets."
))


@mcp.tool()
def compute_hurst_exponent(prices: list[float]) -> dict:
    """
    Compute the Hurst exponent for a price series.
    H < 0.5 = mean-reverting, H ≈ 0.5 = random walk, H > 0.5 = trending.
    Useful for choosing between momentum and mean-reversion strategies.
    """
    try:
        from engine.quant_stats import compute_hurst
        return compute_hurst(np.array(prices))
    except ImportError:
        return {"error": "quant_stats module not yet available"}


@mcp.tool()
def test_price_stationarity(prices: list[float]) -> dict:
    """
    Run ADF and KPSS stationarity tests on a price series.
    Returns p-values and interpretation. Stationary returns are
    a prerequisite for many quantitative models.
    """
    try:
        from engine.quant_stats import test_stationarity
        return test_stationarity(np.array(prices))
    except ImportError:
        return {"error": "quant_stats module not yet available"}


@mcp.tool()
def compute_risk_metrics(returns: list[float], confidence: float = 0.95) -> dict:
    """
    Compute historical VaR and CVaR (Expected Shortfall).
    Returns the worst-case loss at the given confidence level.
    confidence: float between 0 and 1 (e.g. 0.95 for 95% VaR).
    """
    try:
        from engine.quant_stats import compute_var_cvar
        return compute_var_cvar(np.array(returns), confidence=confidence)
    except ImportError:
        return {"error": "quant_stats module not yet available"}


@mcp.tool()
def run_monte_carlo(
    trade_pnls: list[float],
    n_sims: int = 1000,
    n_bars: int = 0,
    initial_capital: float = 10_000.0,
) -> dict:
    """
    Bootstrap Monte Carlo simulation on a list of historical trade P&L values.
    Returns percentile paths, probability of profit, and risk metrics.
    n_bars: number of trades per simulated path (0 = same as historical).
    """
    from engine.montecarlo import run_bootstrap
    pnl = np.array(trade_pnls, dtype=float)
    if len(pnl) < 3:
        return {"error": "Need at least 3 trades"}
    result = run_bootstrap(pnl, n_sims=min(n_sims, 5000), n_bars=n_bars or None,
                           initial_capital=initial_capital)
    finals = result["final_capital"]
    pcts = np.percentile(finals, [5, 25, 50, 75, 95])
    return {
        "p_profit": round(float((finals > initial_capital).mean()), 4),
        "p_ruin":   round(float((finals < initial_capital * 0.5).mean()), 4),
        "p5_final":  round(float(pcts[0]), 2),
        "p50_final": round(float(pcts[2]), 2),
        "p95_final": round(float(pcts[4]), 2),
        "var_95":    round(float(result.get("var_95", 0)), 2),
        "cvar_95":   round(float(result.get("cvar_95", 0)), 2),
        "mean_max_dd_pct": round(float(result["max_dd_pct"].mean()), 2),
    }


@mcp.tool()
def quick_backtest(
    ticker: str = "BTC-USD",
    sl_mult: float = 2.0,
    tp_mult: float = 4.0,
    risk_per_trade: float = 0.01,
    direction: str = "ALL",
    n_bars: int = 2000,
) -> dict:
    """
    Run a quick backtest using the default momentum strategy on synthetic/last-known data.
    Returns key metrics: Sharpe, CAGR, max drawdown, trade count.
    For a full backtest with real data use the /runs API endpoint.
    """
    from engine.strategy_core import compute_indicators_v2, generate_signals_v2, backtest_v2, compute_metrics
    # Generate synthetic walk for demo (real data requires DB access)
    np.random.seed(42)
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="h")
    prices = 40_000 * np.cumprod(1 + np.random.randn(n_bars) * 0.005)
    df = pd.DataFrame({
        "Open": prices * 0.999,
        "High": prices * 1.003,
        "Low":  prices * 0.997,
        "Close": prices,
        "Volume": 1e8,
    }, index=idx)
    df_ind = compute_indicators_v2(df, fit_garch=False)
    df_sig = generate_signals_v2(df_ind, atr_mult_sl=sl_mult, atr_mult_tp=tp_mult)
    if direction == "LONG":
        df_sig.loc[df_sig["signal"] == -1, "signal"] = 0
    elif direction == "SHORT":
        df_sig.loc[df_sig["signal"] == 1, "signal"] = 0
    res = backtest_v2(df_sig, 10_000, risk_per_trade)
    m = compute_metrics(res, 10_000)
    return {
        "ticker": ticker,
        "sl_mult": sl_mult,
        "tp_mult": tp_mult,
        "n_trades":    m.get("n_trades", 0),
        "sharpe":      round(m.get("sharpe_ratio", 0), 3),
        "cagr_pct":    round(m.get("cagr_pct", 0), 2),
        "max_dd_pct":  round(m.get("max_drawdown_pct", 0), 2),
        "win_rate_pct":round(m.get("win_rate_pct", 0), 1),
        "profit_factor":round(m.get("profit_factor", 0), 2),
        "note": "Synthetic data — for real backtest use POST /runs",
    }


if __name__ == "__main__":
    mcp.run()
