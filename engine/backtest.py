"""
engine/backtest.py
==================
run_versions, run_wfo, run_optimization — parameterised, no file IO.
All functions receive DataFrames and config dicts; return dicts/DataFrames.
"""
import numpy as np
import pandas as pd
from .strategy_core import (
    generate_signals_v2, backtest_v2, compute_metrics, apply_garch_to_fold,
)
from .indicators import make_ind

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
    comm = cfg.get("commission_pips", 1.0)
    slip = cfg.get("slippage_pips",   0.5)
    risk = cfg.get("risk_per_trade", 0.01)
    lvg  = cfg.get("leverage", 1.0)
    max_pos  = int(cfg.get("max_positions", 1))
    cooldown = int(cfg.get("cooldown_bars", 0))
    cap      = float(cfg.get("initial_capital", INITIAL_CAPITAL))
    ts_on    = bool(cfg.get("trailing_stop", False))
    ts_meth  = cfg.get("trailing_stop_method", "atr")
    ts_val   = float(cfg.get("trailing_stop_value", 1.5))
    ps_meth  = cfg.get("position_size_method", "risk_pct")

    results = {}
    versions = [
        ("V1 Base",         {"use_garch_filter": False, "commission_pips": 0.0,  "slippage_pips": 0.0}),
        ("V2 +Costi",       {"use_garch_filter": False, "commission_pips": comm, "slippage_pips": slip}),
        ("V4 +GARCH+Costi", {"use_garch_filter": True,  "commission_pips": comm, "slippage_pips": slip}),
    ]
    for i, (name, vcfg) in enumerate(versions):
        if progress_cb:
            progress_cb("versions", int(20 + i * 15))
        df_s = generate_signals_v2(df_ind, atr_mult_sl=sl, atr_mult_tp=tp,
                                    active_hours=hrs,
                                    use_garch_filter=vcfg["use_garch_filter"])
        df_s = _apply_direction_filter(df_s, direction)
        res  = backtest_v2(df_s, cap, risk,
                           commission_pips=vcfg["commission_pips"],
                           slippage_pips=vcfg["slippage_pips"],
                           max_positions=max_pos, cooldown_bars=cooldown, leverage=lvg,
                           trailing_stop=ts_on, trailing_stop_method=ts_meth,
                           trailing_stop_value=ts_val, position_size_method=ps_meth)
        results[name] = {"result": res, "metrics": compute_metrics(res, cap)}

    # V_Agent: use provided agent_fn if any
    agent_fn = cfg.get("agent_fn")
    if agent_fn:
        if progress_cb:
            progress_cb("agent", 65)
        try:
            import inspect as _inspect
            from .indicators import make_ind as _make_ind
            _ind = _make_ind(df_ind)
            _sig_params = list(_inspect.signature(agent_fn).parameters)
            _call_args  = (df_ind, _ind) if len(_sig_params) >= 2 else (df_ind,)
            df_a = _apply_cfg_overrides(_apply_direction_filter(agent_fn(*_call_args), direction),
                                         sl, tp, hrs)
            res_a = backtest_v2(df_a, cap, risk,
                                commission_pips=comm, slippage_pips=slip,
                                max_positions=max_pos, cooldown_bars=cooldown, leverage=lvg,
                                trailing_stop=ts_on, trailing_stop_method=ts_meth,
                                trailing_stop_value=ts_val, position_size_method=ps_meth)
            results["V_Agent"] = {"result": res_a, "metrics": compute_metrics(res_a, cap)}
        except Exception as exc:
            results["V_Agent"] = {"error": str(exc)}

    return results


_WFO_SL_GRID: list[float] = [1.5, 2.0, 2.5, 3.0]
_WFO_TP_GRID: list[float] = [2.0, 3.0, 4.0, 5.0, 6.0]


def _best_params_on_is(
    is_data: pd.DataFrame,
    hrs: tuple,
    direction: str,
) -> tuple[float, float]:
    """Grid-search (sl, tp) on IS window; return pair maximising Sharpe.

    Uses V1-Base settings (no GARCH, no commission) for speed.
    """
    best_sharpe = float("-inf")
    best_sl, best_tp = _WFO_SL_GRID[1], _WFO_TP_GRID[1]   # sensible default
    for sl_c in _WFO_SL_GRID:
        for tp_c in _WFO_TP_GRID:
            df_s = generate_signals_v2(
                is_data, atr_mult_sl=sl_c, atr_mult_tp=tp_c,
                active_hours=hrs, use_garch_filter=False,
            )
            df_s = _apply_direction_filter(df_s, direction)
            res  = backtest_v2(df_s, INITIAL_CAPITAL, 0.01,
                               commission_pips=0.0, slippage_pips=0.0)
            sharpe = compute_metrics(res, INITIAL_CAPITAL).get("sharpe_ratio", float("-inf"))
            if sharpe > best_sharpe:
                best_sharpe, best_sl, best_tp = sharpe, sl_c, tp_c
    return best_sl, best_tp


def run_wfo(df_ind: pd.DataFrame, cfg: dict, agent_fn=None,
            direction: str = "ALL", progress_cb=None,
            per_fold_opt: bool = False) -> pd.DataFrame:
    """Walk-Forward Optimization. Returns DataFrame of fold results.

    Parameters
    ----------
    per_fold_opt:
        When True, each fold's IS window is used to grid-search the best
        (sl_mult, tp_mult) pair (20 combinations).  Those optimal params are
        then used for both IS and OOS evaluation of that fold.  Adds
        ``best_sl`` / ``best_tp`` columns to the result.
        When False (default) behaviour is identical to the original implementation.
    """
    comm = cfg.get("commission_pips", 1.0)
    slip = cfg.get("slippage_pips",   0.5)
    risk = cfg.get("risk_per_trade", 0.01)
    lvg  = cfg.get("leverage", 1.0)
    sl   = cfg.get("sl_mult", 2.0)
    tp   = cfg.get("tp_mult", 5.0)
    hrs  = tuple(cfg.get("active_hours", [6, 22]))
    max_pos  = int(cfg.get("max_positions", 1))
    cooldown = int(cfg.get("cooldown_bars", 0))
    cap      = float(cfg.get("initial_capital", INITIAL_CAPITAL))
    ts_on    = bool(cfg.get("trailing_stop", False))
    ts_meth  = cfg.get("trailing_stop_method", "atr")
    ts_val   = float(cfg.get("trailing_stop_value", 1.5))
    ps_meth  = cfg.get("position_size_method", "risk_pct")

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
            is_data  = df_ind.iloc[i : i + is_len].copy()
            oos_data = df_ind.iloc[i + is_len : i + is_len + oos_len].copy()
            # Refit GARCH on IS only — eliminates lookahead bias in WFO folds
            if "garch_h" in df_ind.columns and "Close" in df_ind.columns:
                try:
                    is_data, oos_data = apply_garch_to_fold(is_data, oos_data)
                except Exception:
                    pass  # fall back to pre-computed garch_h if anything fails

            # --- per-fold IS optimisation (optional) ---
            if per_fold_opt:
                fold_sl, fold_tp = _best_params_on_is(is_data, hrs, direction)
            else:
                fold_sl, fold_tp = sl, tp

            df_is  = _apply_cfg_overrides(
                _apply_direction_filter(agent_fn(is_data), direction),
                fold_sl, fold_tp, hrs,
            )
            res_is = backtest_v2(df_is, cap, risk, comm, slip,
                                 max_positions=max_pos, cooldown_bars=cooldown, leverage=lvg,
                                 trailing_stop=ts_on, trailing_stop_method=ts_meth,
                                 trailing_stop_value=ts_val, position_size_method=ps_meth)
            m_is   = compute_metrics(res_is, cap)

            df_os  = _apply_cfg_overrides(
                _apply_direction_filter(agent_fn(oos_data), direction),
                fold_sl, fold_tp, hrs,
            )
            res_os = backtest_v2(df_os, cap, risk, comm, slip,
                                 max_positions=max_pos, cooldown_bars=cooldown, leverage=lvg,
                                 trailing_stop=ts_on, trailing_stop_method=ts_meth,
                                 trailing_stop_value=ts_val, position_size_method=ps_meth)
            m_os   = compute_metrics(res_os, cap)

            row: dict = {
                "window_config": wcfg["label"],
                "fold":          fold,
                "is_sharpe":     m_is.get("sharpe_ratio", 0),
                "oos_sharpe":    m_os.get("sharpe_ratio", 0),
                "is_cagr":       m_is.get("cagr_pct", 0),
                "oos_cagr":      m_os.get("cagr_pct", 0),
                "is_return":     m_is.get("total_return_pct", 0),
                "oos_return":    m_os.get("total_return_pct", 0),
                "is_n_trades":   m_is.get("n_trades", 0),
                "oos_n_trades":  m_os.get("n_trades", 0),
                "is_max_dd":     m_is.get("max_drawdown_pct", 0),
                "oos_max_dd":    m_os.get("max_drawdown_pct", 0),
                "best_sl":       fold_sl if per_fold_opt else None,
                "best_tp":       fold_tp if per_fold_opt else None,
                "efficiency_factor": round(m_os.get("sharpe_ratio", 0) / m_is.get("sharpe_ratio", 1), 3) if m_is.get("sharpe_ratio", 0) != 0 else 0.0,
            }
            rows.append(row)
            fold += 1
            i    += step
            done += 1
            if progress_cb:
                progress_cb("wfo", int(70 + done / max(total, 1) * 20))

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def run_optimization(df_ind: pd.DataFrame, cfg: dict,
                      progress_cb=None) -> pd.DataFrame:
    """Grid-search SL/TP/hours. Returns sorted DataFrame."""
    comm = cfg.get("commission_pips", 1.0)
    slip = cfg.get("slippage_pips",   0.5)
    risk = cfg.get("risk_per_trade", 0.01)
    lvg  = cfg.get("leverage", 1.0)
    cap  = float(cfg.get("initial_capital", INITIAL_CAPITAL))

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
        res  = backtest_v2(df_s, cap, risk, comm, slip, leverage=lvg)
        m    = compute_metrics(res, cap)
        rows.append({
            "sl_mult":          sl,
            "tp_mult":          tp,
            "active_hours":     f"{h[0]}-{h[1]}",
            "sharpe_ratio":     m.get("sharpe_ratio", 0),
            "cagr_pct":         m.get("cagr_pct", 0),
            "max_drawdown_pct": m.get("max_drawdown_pct", 0),
            "n_trades":         m.get("n_trades", 0),
            "win_rate_pct":     m.get("win_rate_pct", 0),
            "profit_factor":    m.get("profit_factor", 0),
        })

    df_opt = pd.DataFrame(rows)
    return df_opt.sort_values("sharpe_ratio", ascending=False) if not df_opt.empty else df_opt
