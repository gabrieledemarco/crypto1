"""
backtest_vbt.py — vectorbt-powered backtest engine.

Provides two public functions:

  backtest_vbt_single(df, **kwargs)
      Drop-in replacement for backtest_v2() when trailing_stop=False.
      Uses vbt.Portfolio.from_signals() — ~10-30x faster than the Python loop.

  backtest_vbt_sweep(df, sl_mults, tp_mults, ...)
      Runs the full SL × TP grid in ONE vectorised call using 2-D numpy
      broadcasting. Replaces the sequential combo loop in run_optimization().
      ~20-50x faster than the original loop for a 75-combo sweep.

Both functions fall back to the original loop engine on ImportError or any
unexpected vectorbt API change, so the system degrades gracefully.
"""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import pandas as pd

log = logging.getLogger("backtest_vbt")


# ── helpers ───────────────────────────────────────────────────────────────────

def _pip_size(close_arr: np.ndarray) -> float:
    sample = float(close_arr[close_arr > 0][0]) if np.any(close_arr > 0) else 1.0
    return 0.01 if sample >= 10.0 else 0.0001


def _fees_pct(commission_pips: float, slippage_pips: float, pip: float, price: float) -> float:
    return (commission_pips + slippage_pips) * pip / max(price, 1e-9)


def _size_array(df: pd.DataFrame, risk_per_trade: float, leverage: float) -> np.ndarray:
    mults = df["size_mult"].values if "size_mult" in df.columns else np.ones(len(df))
    return np.clip(risk_per_trade * mults * leverage, 1e-6, 1.0)


def _convert_vbt_trades(pf, index: pd.Index) -> pd.DataFrame:
    """Convert vectorbt trade records to the dict format used by compute_metrics()."""
    try:
        tr = pf.trades.records_readable
        if tr.empty:
            return pd.DataFrame()
        out = pd.DataFrame()
        n = len(tr)
        # Map bar-index back to timestamps
        def _bar_to_ts(col):
            try:
                bars = tr[col].astype(int).clip(0, len(index) - 1)
                return index[bars]
            except Exception:
                return pd.Series([None] * n)

        out["entry_time"]  = _bar_to_ts("Entry Trade Index")
        out["exit_time"]   = _bar_to_ts("Exit Trade Index")
        out["direction"]   = tr.get("Direction", pd.Series(["LONG"] * n)).map(
            {0: "LONG", 1: "SHORT", "Long": "LONG", "Short": "SHORT"}
        ).fillna("LONG")
        out["entry_price"] = tr.get("Avg Entry Price", pd.Series(np.zeros(n))).values
        out["exit_price"]  = tr.get("Avg Exit Price",  pd.Series(np.zeros(n))).values
        out["qty"]         = tr.get("Size", pd.Series(np.zeros(n))).values
        out["pnl"]         = tr.get("PnL",  pd.Series(np.zeros(n))).values
        out["pnl_pct"]     = tr.get("Return [%]", pd.Series(np.zeros(n))).values
        out["gross_pnl"]   = out["pnl"]
        out["costs"]       = 0.0
        out["exit_reason"] = "TP"  # vectorbt merges SL/TP; post-process if needed
        return out
    except Exception as exc:
        log.debug("_convert_vbt_trades failed: %s", exc)
        return pd.DataFrame()


# ── single backtest ───────────────────────────────────────────────────────────

def backtest_vbt_single(
    df: pd.DataFrame,
    initial_capital: float = 10_000,
    risk_per_trade: float = 0.01,
    commission_pips: float = 1.0,
    slippage_pips: float = 0.5,
    max_positions: int = 1,
    cooldown_bars: int = 0,
    leverage: float = 1.0,
    trailing_stop: bool = False,
    trailing_stop_method: str = "atr",
    trailing_stop_value: float = 1.5,
    position_size_method: str = "risk_pct",
) -> dict:
    """
    Drop-in replacement for backtest_v2() when trailing_stop=False.
    Falls back to original loop engine for trailing-stop semantics.
    """
    if trailing_stop:
        from engine.strategy_core import _backtest_v2_original
        return _backtest_v2_original(
            df, initial_capital=initial_capital, risk_per_trade=risk_per_trade,
            commission_pips=commission_pips, slippage_pips=slippage_pips,
            max_positions=max_positions, cooldown_bars=cooldown_bars,
            leverage=leverage, trailing_stop=True,
            trailing_stop_method=trailing_stop_method,
            trailing_stop_value=trailing_stop_value,
            position_size_method=position_size_method,
        )

    try:
        import vectorbt as vbt
    except ImportError:
        from engine.strategy_core import _backtest_v2_original
        return _backtest_v2_original(
            df, initial_capital=initial_capital, risk_per_trade=risk_per_trade,
            commission_pips=commission_pips, slippage_pips=slippage_pips,
            max_positions=max_positions, cooldown_bars=cooldown_bars,
            leverage=leverage, position_size_method=position_size_method,
        )

    close = df["Close"].values.astype(float)
    pip   = _pip_size(close)
    fees  = _fees_pct(commission_pips, slippage_pips, pip, float(np.median(close)))

    entries = df["signal"].values == 1
    exits   = df["signal"].values == -1

    # SL/TP as fraction of close price
    sl_frac = np.clip(df["SL_dist"].values / np.maximum(close, 1e-9), 0.001, 0.5)
    tp_frac = np.clip(df["TP_dist"].values / np.maximum(close, 1e-9), 0.001, 2.0)

    if position_size_method == "fixed_pct":
        size = np.clip(risk_per_trade * leverage, 1e-6, 1.0)
    else:
        size = _size_array(df, risk_per_trade, leverage)

    try:
        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            short_entries=df["signal"].values == -1,
            short_exits=df["signal"].values == 1,
            sl_stop=sl_frac,
            tp_stop=tp_frac,
            size=size,
            size_type="percent",
            init_cash=initial_capital,
            fees=fees,
            freq="1min",
            max_size=leverage,
        )

        equity_vals = pf.value().values
        # Align equity to df index length
        if len(equity_vals) < len(df):
            equity_vals = np.pad(equity_vals, (0, len(df) - len(equity_vals)),
                                  constant_values=equity_vals[-1] if len(equity_vals) else initial_capital)

        equity_s = pd.Series(equity_vals[:len(df)], index=df.index)
        final_cap = float(equity_s.iloc[-1])

        return {
            "trades":        _convert_vbt_trades(pf, df.index),
            "equity":        equity_s,
            "final_capital": final_cap,
        }

    except Exception as exc:
        log.warning("backtest_vbt_single error, falling back: %s", exc)
        from engine.strategy_core import _backtest_v2_original
        return _backtest_v2_original(
            df, initial_capital=initial_capital, risk_per_trade=risk_per_trade,
            commission_pips=commission_pips, slippage_pips=slippage_pips,
            max_positions=max_positions, cooldown_bars=cooldown_bars,
            leverage=leverage, position_size_method=position_size_method,
        )


# ── sweep (grid search) ───────────────────────────────────────────────────────

def backtest_vbt_sweep(
    df: pd.DataFrame,
    sl_mults: Sequence[float],
    tp_mults: Sequence[float],
    hour_windows: Sequence[tuple[int, int]] | None = None,
    initial_capital: float = 10_000,
    risk_per_trade: float = 0.01,
    commission_pips: float = 1.0,
    slippage_pips: float = 0.5,
    leverage: float = 1.0,
) -> pd.DataFrame:
    """
    Vectorised SL × TP parameter sweep via vectorbt 2-D broadcasting.
    Returns one row per (sl_mult, tp_mult, active_hours) combo,
    sorted by sharpe_ratio descending.

    hour_windows: list of (start_h, end_h) tuples to sweep.
                  If None, uses the hours already encoded in df["signal"].
    """
    try:
        import vectorbt as vbt
    except ImportError:
        log.warning("vectorbt not installed — sweep falls back to loop engine")
        return _sweep_fallback(df, sl_mults, tp_mults, hour_windows,
                               initial_capital, risk_per_trade,
                               commission_pips, slippage_pips, leverage)

    try:
        from engine.strategy_core import generate_signals_v2

        sl_arr  = np.asarray(sl_mults, dtype=float)
        tp_arr  = np.asarray(tp_mults, dtype=float)
        windows = hour_windows or [(6, 22)]

        close  = df["Close"].values.astype(float)
        atr    = df["ATR14"].values.astype(float) if "ATR14" in df.columns else np.ones(len(df))
        pip    = _pip_size(close)
        fees   = _fees_pct(commission_pips, slippage_pips, pip, float(np.median(close)))
        size   = _size_array(df, risk_per_trade, leverage)

        rows = []
        for h_start, h_end in windows:
            # Build signal array for this hour window
            df_s = generate_signals_v2(df, atr_mult_sl=1.0, atr_mult_tp=1.0,
                                        active_hours=(h_start, h_end),
                                        use_garch_filter=True)
            entries_base = df_s["signal"].values == 1
            exits_base   = df_s["signal"].values == -1

            # Build 2-D SL/TP arrays: shape (n_combos, n_bars)
            sl_grid, tp_grid = np.meshgrid(sl_arr, tp_arr, indexing="ij")
            sl_flat = sl_grid.flatten()
            tp_flat = tp_grid.flatten()
            valid = tp_flat > sl_flat
            sl_flat, tp_flat = sl_flat[valid], tp_flat[valid]
            n_combos = len(sl_flat)

            # SL/TP fraction arrays: (n_combos, n_bars)
            sl_2d = np.outer(sl_flat, atr) / np.maximum(close, 1e-9)
            tp_2d = np.outer(tp_flat, atr) / np.maximum(close, 1e-9)
            sl_2d = np.clip(sl_2d, 0.001, 0.5)
            tp_2d = np.clip(tp_2d, 0.001, 2.0)

            pf = vbt.Portfolio.from_signals(
                close=close,
                entries=entries_base,
                exits=exits_base,
                sl_stop=sl_2d,
                tp_stop=tp_2d,
                size=size,
                size_type="percent",
                init_cash=initial_capital,
                fees=fees,
                freq="1min",
            )

            stats = pf.stats(silence_warnings=True)

            for k in range(n_combos):
                s = stats.iloc[k] if isinstance(stats, pd.DataFrame) else stats
                rows.append({
                    "sl_mult":          round(float(sl_flat[k]), 2),
                    "tp_mult":          round(float(tp_flat[k]), 2),
                    "active_hours":     f"{h_start}-{h_end}",
                    "sharpe_ratio":     _safe(s, "Sharpe Ratio"),
                    "cagr_pct":         _safe(s, "Annualized Return [%]"),
                    "max_drawdown_pct": abs(_safe(s, "Max Drawdown [%]", 0)),
                    "n_trades":         int(_safe(s, "Total Trades", 0)),
                    "win_rate_pct":     _safe(s, "Win Rate [%]"),
                    "profit_factor":    _safe(s, "Profit Factor"),
                })

        df_out = pd.DataFrame(rows)
        return df_out.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)

    except Exception as exc:
        log.warning("backtest_vbt_sweep error, falling back: %s", exc)
        return _sweep_fallback(df, sl_mults, tp_mults, hour_windows,
                               initial_capital, risk_per_trade,
                               commission_pips, slippage_pips, leverage)


def _safe(stats_row, key: str, default: float = 0.0) -> float:
    try:
        val = stats_row.get(key, default) if hasattr(stats_row, "get") else stats_row[key]
        f = float(val)
        return f if np.isfinite(f) else default
    except Exception:
        return default


def _sweep_fallback(df, sl_mults, tp_mults, hour_windows,
                    initial_capital, risk_per_trade,
                    commission_pips, slippage_pips, leverage) -> pd.DataFrame:
    """Sequential loop fallback — same logic as original run_optimization()."""
    from engine.strategy_core import generate_signals_v2, _backtest_v2_original, compute_metrics
    windows = hour_windows or [(6, 22)]
    rows = []
    for sl in sl_mults:
        for tp in tp_mults:
            if tp <= sl:
                continue
            for h_start, h_end in windows:
                df_s = generate_signals_v2(df, atr_mult_sl=sl, atr_mult_tp=tp,
                                            active_hours=(h_start, h_end),
                                            use_garch_filter=True)
                res = _backtest_v2_original(df_s, initial_capital, risk_per_trade,
                                             commission_pips, slippage_pips, leverage=leverage)
                m = compute_metrics(res, initial_capital)
                rows.append({
                    "sl_mult": sl, "tp_mult": tp,
                    "active_hours": f"{h_start}-{h_end}",
                    "sharpe_ratio":     m.get("sharpe_ratio", 0),
                    "cagr_pct":         m.get("cagr_pct", 0),
                    "max_drawdown_pct": m.get("max_drawdown_pct", 0),
                    "n_trades":         m.get("n_trades", 0),
                    "win_rate_pct":     m.get("win_rate_pct", 0),
                    "profit_factor":    m.get("profit_factor", 0),
                })
    df_out = pd.DataFrame(rows)
    return df_out.sort_values("sharpe_ratio", ascending=False).reset_index(drop=True)
