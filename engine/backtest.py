"""
engine/backtest.py
==================
run_versions, run_wfo, run_optimization — parameterised, no file IO.
All functions receive DataFrames and config dicts; return dicts/DataFrames.
"""
import numpy as np
import pandas as pd
from .strategy_core import (
    generate_signals_v2, backtest_v2, compute_metrics,
)

INITIAL_CAPITAL = 10_000
HOURS_MONTH = 24 * 30


def _apply_direction_filter(df: pd.DataFrame, direction: str = "ALL") -> pd.DataFrame:
    """Zero out signals for excluded directions."""
    if direction == "LONG":
        df = df.copy(); df.loc[df["signal"] == -1, "signal"] = 0
    elif direction == "SHORT":
        df = df.copy(); df.loc[df["signal"] == 1, "signal"] = 0
    return df


def _apply_cfg_overrides(df: pd.DataFrame, sl_mult: float, tp_mult: float,
                          active_hours: tuple) -> pd.DataFrame:
    """Override SL_dist/TP_dist/active_hours in a signal DataFrame.
    Makes parametric config actually affect agent-generated signal columns."""
    df = df.copy()
    df["SL_dist"] = df["ATR14"] * sl_mult
    df["TP_dist"] = df["ATR14"] * tp_mult
    hour = pd.to_datetime(df.index).hour
    time_ok = (hour >= active_hours[0]) & (hour <= active_hours[1])
    df.loc[~time_ok, "signal"] = 0
    return df


def run_versions(df_ind: pd.DataFrame, cfg: dict, direction: str = "ALL",
                 progress_cb=None) -> dict:
    """
    Run V1/V2/V4/V_Agent backtests.
    cfg: dict with sl_mult, tp_mult, active_hours, commission, slippage, risk_per_trade.
    progress_cb: optional callable(phase: str, pct: int) for SSE progress.
    Returns: dict of {version_name: {result, metrics}}
    """
    sl   = cfg.get("sl_mult", 2.0)
    tp   = cfg.get("tp_mult", 5.0)
    hrs  = tuple(cfg.get("active_hours", [6, 22]))
    comm = cfg.get("commission", 0.0004)
    slip = cfg.get("slippage",   0.0001)
    risk = cfg.get("risk_per_trade", 0.01)

    results = {}
    versions = [
        ("V1 Base",         {"use_garch_filter": False, "commission": 0.0,   "slippage": 0.0}),
        ("V2 +Costi",       {"use_garch_filter": False, "commission": comm,  "slippage": slip}),
        ("V4 +GARCH+Costi", {"use_garch_filter": True,  "commission": comm,  "slippage": slip}),
    ]
    for i, (name, vcfg) in enumerate(versions):
        if progress_cb:
            progress_cb("versions", int(20 + i * 15))
        df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                    active_hours=hrs,
                                    use_garch_filter=vcfg["use_garch_filter"])
        df_s = _apply_direction_filter(df_s, direction)
        res  = backtest_v2(df_s, INITIAL_CAPITAL, risk,
                           commission=vcfg["commission"], slippage=vcfg["slippage"])
        results[name] = {"result": res, "metrics": compute_metrics(res, INITIAL_CAPITAL)}

    # V_Agent: use provided agent_fn if any
    agent_fn = cfg.get("agent_fn")
    if agent_fn:
        if progress_cb:
            progress_cb("agent", 65)
        try:
            df_a = _apply_cfg_overrides(_apply_direction_filter(agent_fn(df_ind), direction),
                                         sl, tp, hrs)
            res_a = backtest_v2(df_a, INITIAL_CAPITAL, risk, commission=comm, slippage=slip)
            results["V_Agent"] = {"result": res_a, "metrics": compute_metrics(res_a, INITIAL_CAPITAL)}
        except Exception as exc:
            results["V_Agent"] = {"error": str(exc)}

    return results


def run_wfo(df_ind: pd.DataFrame, cfg: dict, agent_fn=None,
            direction: str = "ALL", progress_cb=None) -> pd.DataFrame:
    """Walk-Forward Optimization. Returns DataFrame of fold results."""
    comm = cfg.get("commission", 0.0004)
    slip = cfg.get("slippage",   0.0001)
    risk = cfg.get("risk_per_trade", 0.01)
    sl   = cfg.get("sl_mult", 2.0)
    tp   = cfg.get("tp_mult", 5.0)
    hrs  = tuple(cfg.get("active_hours", [6, 22]))

    if agent_fn is None:
        # fallback: use generate_signals_v2
        def agent_fn(df):
            return generate_signals_v2(df, atr_mult_sl=sl, atr_mult_tp=tp,
                                        active_hours=hrs, use_garch_filter=True)

    window_configs = [
        {"label": "IS=4m OOS=1m",  "train": 4 * HOURS_MONTH, "test": 1 * HOURS_MONTH},
        {"label": "IS=6m OOS=2m",  "train": 6 * HOURS_MONTH, "test": 2 * HOURS_MONTH},
        {"label": "IS=8m OOS=2m",  "train": 8 * HOURS_MONTH, "test": 2 * HOURS_MONTH},
        {"label": "IS=8m OOS=3m",  "train": 8 * HOURS_MONTH, "test": 3 * HOURS_MONTH},
    ]

    rows = []
    total = sum(max(0, len(df_ind) - c["train"] - c["test"]) // c["test"] + 1
                for c in window_configs)
    done = 0
    for wcfg in window_configs:
        is_len  = wcfg["train"]
        oos_len = wcfg["test"]
        step    = oos_len
        fold    = 0
        i       = 0
        while i + is_len + oos_len <= len(df_ind):
            is_data  = df_ind.iloc[i : i + is_len]
            oos_data = df_ind.iloc[i + is_len : i + is_len + oos_len]

            df_is  = _apply_cfg_overrides(_apply_direction_filter(agent_fn(is_data), direction),
                                           sl, tp, hrs)
            res_is = backtest_v2(df_is,  INITIAL_CAPITAL, risk, comm, slip)
            m_is   = compute_metrics(res_is, INITIAL_CAPITAL)

            df_os  = _apply_cfg_overrides(_apply_direction_filter(agent_fn(oos_data), direction),
                                           sl, tp, hrs)
            res_os = backtest_v2(df_os, INITIAL_CAPITAL, risk, comm, slip)
            m_os   = compute_metrics(res_os, INITIAL_CAPITAL)

            rows.append({
                "window_config": wcfg["label"],
                "fold":          fold,
                "is_sharpe":     m_is.get("sharpe_ratio", 0),
                "oos_sharpe":    m_os.get("sharpe_ratio", 0),
                "is_cagr":       m_is.get("cagr_pct", 0),
                "oos_cagr":      m_os.get("cagr_pct", 0),
                "is_n_trades":   m_is.get("n_trades", 0),
                "oos_n_trades":  m_os.get("n_trades", 0),
                "is_max_dd":     m_is.get("max_drawdown_pct", 0),
                "oos_max_dd":    m_os.get("max_drawdown_pct", 0),
            })
            fold += 1
            i    += step
            done += 1
            if progress_cb:
                progress_cb("wfo", int(70 + done / max(total, 1) * 20))

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def run_optimization(df_ind: pd.DataFrame, cfg: dict,
                      progress_cb=None) -> pd.DataFrame:
    """Grid-search SL/TP/hours. Returns sorted DataFrame."""
    comm = cfg.get("commission", 0.0004)
    slip = cfg.get("slippage",   0.0001)
    risk = cfg.get("risk_per_trade", 0.01)

    SL_RANGE = [1.0, 1.5, 2.0, 2.5, 3.0]
    TP_RANGE = [2.0, 3.0, 4.0, 5.0, 7.0]
    HOUR_WINDOWS = [(6, 22), (8, 20), (0, 23)]

    rows = []
    combos = [(sl, tp, h) for sl in SL_RANGE for tp in TP_RANGE for h in HOUR_WINDOWS if tp > sl]
    for idx, (sl, tp, h) in enumerate(combos):
        if progress_cb and idx % 5 == 0:
            progress_cb("sweep", int(idx / len(combos) * 100))
        df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                    active_hours=h, use_garch_filter=True)
        res  = backtest_v2(df_s, INITIAL_CAPITAL, risk, comm, slip)
        m    = compute_metrics(res, INITIAL_CAPITAL)
        rows.append({
            "sl_mult":          sl,
            "tp_mult":          tp,
            "active_hours":     f"{h[0]}-{h[1]}",
            "sharpe_ratio":     m.get("sharpe_ratio", 0),
            "cagr_pct":         m.get("cagr_pct", 0),
            "max_drawdown_pct": m.get("max_drawdown_pct", 0),
            "n_trades":         m.get("n_trades", 0),
            "win_rate_pct":     m.get("win_rate_pct", 0),
        })

    df_opt = pd.DataFrame(rows)
    return df_opt.sort_values("sharpe_ratio", ascending=False) if not df_opt.empty else df_opt
