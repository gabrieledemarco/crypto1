"""
strategy_core.py — Enhanced Strategy Engine (engine package version)
=====================================================================
Pure computation library — no file IO, no Streamlit, no matplotlib.
Provides:
  - fit_garch11(): GARCH(1,1) via MLE (scipy L-BFGS-B)
  - compute_garch_regime(): classifica regime vol LOW/MED/HIGH
  - compute_indicators_v2(): indicatori tecnici + GARCH h_t
  - generate_signals_v2(): segnali con filtro regime GARCH
  - backtest_v2(): backtest event-driven con commissioni e slippage
  - compute_metrics(): metriche di performance complete
"""

import re
import time
import numpy as np
import pandas as pd
from arch import arch_model
import warnings

warnings.filterwarnings("ignore", message=".*Maximum Likelihood.*", category=UserWarning)

# GARCH parameter cache: (n_bars, close_first, close_last) → (omega, alpha, beta, h_all, cached_at)
_GARCH_CACHE: dict = {}
_GARCH_TTL = 3600  # seconds — refit at most once per hour for the same dataset fingerprint
warnings.filterwarnings("ignore", message=".*covariance of the parameters.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*optimization.*", category=UserWarning)

# ── Ticker → filename mapping ──────────────────────────────────────────────────

_TICKER_ALIAS = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}


def ticker_to_fname(ticker: str) -> str:
    """Map any ticker symbol to its CSV filename prefix (no extension)."""
    if ticker in _TICKER_ALIAS:
        return _TICKER_ALIAS[ticker]
    return re.sub(r"[^a-z0-9]", "_", ticker.lower()).strip("_")


# ── GARCH(1,1) ────────────────────────────────────────────────────────────────

def fit_garch11(returns: np.ndarray) -> tuple:
    """
    Stima GARCH(1,1) via arch library.
    Ritorna: (omega, alpha, beta, h)
      h = array delle varianze condizionali (NOT volatilities)
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 50 or np.var(r) == 0:
        var_r = float(np.var(r)) if np.var(r) > 0 else 1e-6
        return var_r * 0.03, 0.05, 0.90, np.full(len(r), var_r)
    try:
        # arch expects returns in % scale — multiply by 100
        am = arch_model(r * 100, vol='Garch', p=1, q=1, dist='normal', rescale=False)
        res = am.fit(disp='off', show_warning=False)
        params = res.params
        omega = float(params.get('omega', 1e-6)) / 10_000   # back to decimal scale
        alpha = float(params.get('alpha[1]', 0.05))
        beta  = float(params.get('beta[1]', 0.90))
        # conditional_volatility is in % — convert to variance in decimal
        h = (res.conditional_volatility / 100) ** 2
        if not np.all(np.isfinite(h)) or len(h) != len(r):
            raise ValueError("bad h")
        return omega, alpha, beta, h.values if hasattr(h, 'values') else h
    except Exception:
        # fallback to rolling variance
        var_r = float(np.var(r)) if np.var(r) > 0 else 1e-6
        h = np.full(len(r), var_r)
        return var_r * 0.03, 0.05, 0.90, h


def compute_garch_regime(h: np.ndarray,
                         low_pct: float = 25,
                         high_pct: float = 75) -> np.ndarray:
    """
    Classifica ogni timestep in regime di volatilità:
      'LOW'  → h < low_pct percentile  (mercato silenzioso, pochi breakout)
      'MED'  → low_pct <= h <= high_pct (condizioni ottimali)
      'HIGH' → h > high_pct percentile  (volatilità estrema, ridurre size)
    """
    h_s = pd.Series(h)
    lo = h_s.expanding(min_periods=20).quantile(low_pct / 100)
    hi = h_s.expanding(min_periods=20).quantile(high_pct / 100)
    regime = np.full(len(h), "MED", dtype=object)
    valid = lo.notna() & hi.notna()
    regime[valid & (h_s.values < lo.values)] = "LOW"
    regime[valid & (h_s.values > hi.values)] = "HIGH"
    return regime


# ── Indicators ────────────────────────────────────────────────────────────────

def compute_indicators_v2(df: pd.DataFrame,
                           fit_garch: bool = True) -> pd.DataFrame:
    """
    Calcola indicatori tecnici + GARCH(1,1) regime sul dataframe orario.
    Aggiunge colonne:
      ATR14, RSI14, EMA50, EMA200, RollHigh6, RollLow6,
      ATR_pct, hour, dow, ret,
      garch_h (varianza condizionale), garch_regime (LOW/MED/HIGH),
      size_mult (1.0/MED, 0.5/HIGH, 0.0/LOW)
    """
    df = df.copy()

    # ATR
    df["HL"] = df["High"] - df["Low"]
    df["HC"] = (df["High"] - df["Close"].shift(1)).abs()
    df["LC"] = (df["Low"] - df["Close"].shift(1)).abs()
    df["TR"] = df[["HL", "HC", "LC"]].max(axis=1)
    df["ATR14"] = df["TR"].ewm(span=14, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["RSI14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    # EMA
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # Breakout levels
    df["RollHigh6"] = df["High"].rolling(6).max().shift(1)
    df["RollLow6"] = df["Low"].rolling(6).min().shift(1)

    # Misc
    df["ret"] = df["Close"].pct_change()
    df["ATR_pct"] = df["ATR14"] / df["Close"]
    df["hour"] = df.index.hour
    df["dow"] = df.index.dayofweek

    df = df.dropna()

    # GARCH regime
    if fit_garch and len(df) > 100:
        r_aligned = np.log(df["Close"] / df["Close"].shift(1)).fillna(0).values
        _cache_key = (len(r_aligned), round(float(r_aligned[0]), 6), round(float(r_aligned[-1]), 6))
        _cached = _GARCH_CACHE.get(_cache_key)
        _now = time.monotonic()
        try:
            if _cached and (_now - _cached[1]) < _GARCH_TTL:
                h_all = _cached[0]
            else:
                _, _, _, h_all = fit_garch11(r_aligned[1:])
                _GARCH_CACHE[_cache_key] = (h_all, _now)
            h_padded = np.concatenate([[h_all[0]], h_all])
            df["garch_h"] = h_padded[:len(df)]
        except Exception:
            df["garch_h"] = df["ret"].rolling(24).var().fillna(df["ret"].var())

        regime = compute_garch_regime(df["garch_h"].values)
        df["garch_regime"] = regime
        # size_mult: 0=skip LOW, 1=normal MED, 0.5=reduced HIGH
        df["size_mult"] = np.where(regime == "LOW", 0.0,
                          np.where(regime == "HIGH", 0.5, 1.0))
    else:
        df["garch_h"] = df["ret"].rolling(24).var().fillna(df["ret"].var())
        df["garch_regime"] = "MED"
        df["size_mult"] = 1.0

    return df


# ── Signal generation ─────────────────────────────────────────────────────────

def generate_signals_v2(df: pd.DataFrame,
                         atr_mult_sl: float = 1.0,
                         atr_mult_tp: float = 2.5,
                         active_hours: tuple = (6, 22),
                         use_garch_filter: bool = True,
                         rsi_ob: float = 70,
                         rsi_os: float = 30,
                         min_atr_pct: float = 0.003) -> pd.DataFrame:
    """
    Genera segnali long/short con filtro GARCH regime opzionale.
    """
    df = df.copy()
    h0, h1 = active_hours
    time_ok = (df["hour"] >= h0) & (df["hour"] <= h1)
    vol_ok = df["ATR_pct"] > min_atr_pct
    trend_long = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]
    bo_long = df["Close"] > df["RollHigh6"]
    bo_short = df["Close"] < df["RollLow6"]
    rsi_ok_l = df["RSI14"] < rsi_ob
    rsi_ok_s = df["RSI14"] > rsi_os

    # GARCH regime filter: salta segnali in regime LOW
    if use_garch_filter and "garch_regime" in df.columns:
        regime_ok = df["garch_regime"] != "LOW"
    else:
        regime_ok = pd.Series(True, index=df.index)

    df["signal"] = 0
    long_cond = bo_long & trend_long & rsi_ok_l & time_ok & vol_ok & regime_ok
    short_cond = bo_short & trend_short & rsi_ok_s & time_ok & vol_ok & regime_ok
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1

    df["SL_dist"] = df["ATR14"] * atr_mult_sl
    df["TP_dist"] = df["ATR14"] * atr_mult_tp

    return df


# ── Backtest v2: con costi di transazione ─────────────────────────────────────

def backtest_v2(df: pd.DataFrame,
                initial_capital: float = 10_000,
                risk_per_trade: float = 0.01,
                commission_pips: float = 1.0,   # commission in pips (absolute price units)
                slippage_pips: float = 0.5,     # slippage in pips (absolute price units)
                max_positions: int = 1,         # max concurrent open positions
                cooldown_bars: int = 0,         # bars to skip entry after a SL hit
                leverage: float = 1.0,          # position leverage multiplier
                ) -> dict:
    """
    Backtest event-driven con:
      - Stop Loss e Take Profit basati su ATR
      - Commissioni e slippage in pips (unità assolute di prezzo)
      - Position sizing: risk_per_trade % capitale / SL_dist, con leverage
      - Riduzione size in regime HIGH (size_mult)
      - max_positions: posizioni aperte contemporaneamente (default 1)
      - cooldown_bars: barre di pausa dopo un SL (default 0)
    """
    capital = initial_capital
    equity = [capital]
    trades = []

    open_positions: list = []  # list of active position dicts
    cooldown_remaining: int = 0

    prices = df["Close"].values
    signals = df["signal"].values
    sl_dists = df["SL_dist"].values
    tp_dists = df["TP_dist"].values
    highs = df["High"].values
    lows = df["Low"].values
    times = df.index
    size_mults = df["size_mult"].values if "size_mult" in df.columns else np.ones(len(df))

    # Convert pips → absolute price units.
    # Forex: price < 10  → pip = 0.0001 (EUR/USD, GBP/USD, AUD/USD, USD/CHF…)
    #        price >= 10 → pip = 0.01   (USD/JPY and high-price instruments)
    sample_price = float(prices[prices > 0][0]) if np.any(prices > 0) else 1.0
    pip_size = 0.01 if sample_price >= 10.0 else 0.0001
    cost_per_unit = (commission_pips + slippage_pips) * pip_size

    for i in range(len(df)):
        # ── 1. Process exits for all open positions ────────────────────────────
        closed_idxs = []
        for j, pos in enumerate(open_positions):
            exit_price = exit_reason = None
            check_sl_first = bool(i % 2)
            d = pos["dir"]

            if d == 1:
                sl_hit = lows[i] <= pos["sl"]
                tp_hit = highs[i] >= pos["tp"]
            else:
                sl_hit = highs[i] >= pos["sl"]
                tp_hit = lows[i] <= pos["tp"]

            if sl_hit and tp_hit:
                exit_price, exit_reason = (pos["sl"], "SL") if check_sl_first else (pos["tp"], "TP")
            elif sl_hit:
                exit_price, exit_reason = pos["sl"], "SL"
            elif tp_hit:
                exit_price, exit_reason = pos["tp"], "TP"

            if exit_price is not None:
                gross_pnl = d * pos["qty"] * (exit_price - pos["entry_price"])
                exit_cost = pos["qty"] * cost_per_unit
                pnl = gross_pnl - exit_cost
                capital += pnl
                notional = pos["entry_price"] * pos["qty"]
                log_ret = float(np.log1p(pnl / notional)) if notional > 0 else 0.0
                trades.append({
                    "entry_time":  pos["entry_time"],
                    "exit_time":   times[i],
                    "direction":   "LONG" if d == 1 else "SHORT",
                    "entry_price": pos["entry_price"],
                    "exit_price":  exit_price,
                    "qty":         pos["qty"],
                    "gross_pnl":   gross_pnl,
                    "costs":       pos["entry_cost"] + exit_cost,
                    "pnl":         pnl,
                    "pnl_pct":     log_ret * 100,
                    "exit_reason": exit_reason,
                })
                closed_idxs.append(j)
                if exit_reason == "SL":
                    cooldown_remaining = cooldown_bars

        for j in reversed(closed_idxs):
            open_positions.pop(j)

        # ── 2. Decrement cooldown ─────────────────────────────────────────────
        if cooldown_remaining > 0:
            cooldown_remaining -= 1

        # ── 3. Open new position if slot available and no cooldown ────────────
        if (len(open_positions) < max_positions and signals[i] != 0
                and cooldown_remaining == 0 and capital > 0):
            dir_new = int(signals[i])
            ep = prices[i]
            sl_d = sl_dists[i]
            tp_d = tp_dists[i]
            sm = float(size_mults[i])
            if sl_d > 0 and sm > 0:
                risk_amount = capital * risk_per_trade * sm
                qty = risk_amount / sl_d
                max_qty = (capital * leverage) / ep if ep > 0 else 0.0
                qty = min(qty, max_qty)

                entry_cost = qty * cost_per_unit
                capital -= entry_cost

                sl_price = ep - sl_d if dir_new == 1 else ep + sl_d
                tp_price = ep + tp_d if dir_new == 1 else ep - tp_d

                open_positions.append({
                    "dir":         dir_new,
                    "entry_price": ep,
                    "sl":          sl_price,
                    "tp":          tp_price,
                    "qty":         qty,
                    "entry_cost":  entry_cost,
                    "entry_time":  times[i],
                })

        equity.append(capital)

    equity_s = pd.Series(equity[1:], index=df.index)
    return {
        "trades": pd.DataFrame(trades) if trades else pd.DataFrame(),
        "equity": equity_s,
        "final_capital": capital,
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(result: dict, initial_capital: float) -> dict:
    trades = result["trades"]
    equity = result["equity"]

    if trades.empty or len(equity) < 2:
        return {"error": "Nessun trade", "sharpe_ratio": -999,
                "cagr_pct": -999, "total_return_pct": -999}

    total_return = (result["final_capital"] / initial_capital - 1) * 100
    n = len(trades)
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    win_rate = len(wins) / n * 100 if n > 0 else 0
    avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
    pf = wins["pnl"].sum() / abs(losses["pnl"].sum()) \
         if len(losses) > 0 and losses["pnl"].sum() != 0 else np.inf

    equity_safe = equity.clip(lower=1e-10)
    ret_s = np.log(equity_safe / equity_safe.shift(1)).dropna()
    ret_s = ret_s.replace([np.inf, -np.inf], np.nan).dropna()

    # ── annualisation factor: infer from equity timestamp spacing ─────────────
    _PERIODS = 24 * 365  # fallback: 1h
    if len(equity) >= 2:
        try:
            freq_secs = (equity.index[1] - equity.index[0]).total_seconds()
            if freq_secs > 0:
                _PERIODS = max(1, int(round(365 * 24 * 3600 / freq_secs)))
        except Exception:
            pass

    try:
        import quantstats as qs
        cagr = float(qs.stats.cagr(ret_s)) * 100
        cagr = max(min(cagr, 999.0), -999.0)
        sharpe  = float(qs.stats.sharpe(ret_s, periods=_PERIODS))
        sortino = float(qs.stats.sortino(ret_s, periods=_PERIODS))
        max_dd  = float(qs.stats.max_drawdown(ret_s)) * 100   # decimal → %
        omega   = float(qs.stats.omega(ret_s, periods=_PERIODS))
        ulcer   = float(qs.stats.ulcer_index(ret_s)) * 100
    except Exception:
        # fallback: pure numpy/pandas
        days = max((equity.index[-1] - equity.index[0]).days, 1)
        cagr = ((result["final_capital"] / initial_capital) ** (365 / days) - 1) * 100
        cagr = max(min(cagr, 999.0), -999.0)
        sharpe = float(ret_s.mean() / ret_s.std() * np.sqrt(_PERIODS)) if ret_s.std() > 0 else 0.0
        down = ret_s[ret_s < 0]
        dd_std = float(np.std(down)) * np.sqrt(_PERIODS) if len(down) > 0 else 0.0
        sortino = float(ret_s.mean()) * _PERIODS / dd_std if dd_std > 0 else 0.0
        roll_max_fb = equity.cummax()
        max_dd = float(((equity - roll_max_fb) / roll_max_fb * 100).min())
        pnl_arr_fb = trades["pnl"].values
        pos_s = float(np.sum(pnl_arr_fb[pnl_arr_fb > 0]))
        neg_s = float(abs(np.sum(pnl_arr_fb[pnl_arr_fb <= 0])))
        omega = round(pos_s / neg_s, 3) if neg_s > 0 else 99.0
        eq_arr = equity.values
        rm = np.maximum.accumulate(eq_arr)
        ulcer = float(np.sqrt(np.mean(((eq_arr - rm) / rm) ** 2))) * 100

    calmar = cagr / abs(max_dd) if max_dd != 0 else np.inf

    # ── trade-level metrics (kept custom — not in quantstats) ─────────────────
    total_costs = trades["costs"].sum() if "costs" in trades.columns else 0
    net_return = float(result["final_capital"] / initial_capital - 1) * 100
    recovery_factor = round(net_return / abs(max_dd), 2) if max_dd != 0 else 0.0

    skewness = float(ret_s.skew()) if len(ret_s) >= 3 else 0.0
    kurtosis = float(ret_s.kurt()) if len(ret_s) >= 4 else 0.0
    if not np.isfinite(skewness): skewness = 0.0
    if not np.isfinite(kurtosis): kurtosis = 0.0

    return {
        "total_return_pct": total_return,
        "cagr_pct":         round(cagr, 4),
        "sharpe_ratio":     round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "calmar_ratio":     round(calmar, 4) if np.isfinite(calmar) else 0.0,
        "n_trades":         n,
        "win_rate_pct":     win_rate,
        "profit_factor":    pf,
        "avg_win_usd":      avg_win,
        "avg_loss_usd":     avg_loss,
        "sl_hits":          len(trades[trades["exit_reason"] == "SL"]),
        "tp_hits":          len(trades[trades["exit_reason"] == "TP"]),
        "total_costs_usd":  total_costs,
        "omega":            round(omega, 3),
        "ulcer":            round(ulcer, 2),
        "recovery_factor":  recovery_factor,
        "sortino_ratio":    round(sortino, 4),
        "skewness":         round(skewness, 4),
        "kurtosis":         round(kurtosis, 4),
    }


def apply_garch_to_fold(
    is_df: pd.DataFrame, oos_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fit GARCH(1,1) on IS data only, then apply IS-fitted params to OOS.
    Returns (is_df_with_garch, oos_df_with_garch) — both with updated
    garch_h, garch_regime, size_mult columns.
    Lookahead-free: OOS never sees future IS returns during fitting.
    """
    is_df = is_df.copy()
    oos_df = oos_df.copy()

    # Fit GARCH on IS log-returns
    is_ret = np.log(is_df["Close"] / is_df["Close"].shift(1)).fillna(0).values
    try:
        omega, alpha, beta, h_is = fit_garch11(is_ret)
    except Exception:
        var_is = float(np.var(is_ret)) if np.var(is_ret) > 0 else 1e-6
        omega, alpha, beta = var_is * 0.03, 0.05, 0.90
        h_is = np.full(len(is_ret), var_is)

    # IS: regime uses expanding IS percentiles
    is_df["garch_h"] = h_is[: len(is_df)]
    is_regime = compute_garch_regime(is_df["garch_h"].values)
    is_df["garch_regime"] = is_regime
    is_df["size_mult"] = np.where(is_regime == "LOW", 0.0,
                          np.where(is_regime == "HIGH", 0.5, 1.0))

    # OOS: recursively forecast using IS-fitted params, seed from last IS h
    oos_ret = np.log(oos_df["Close"] / oos_df["Close"].shift(1)).fillna(0).values
    h_prev = h_is[-1] if len(h_is) > 0 else omega / max(1 - alpha - beta, 1e-6)
    h_oos = np.empty(len(oos_ret))
    for i, r in enumerate(oos_ret):
        h_oos[i] = omega + alpha * r ** 2 + beta * h_prev
        h_prev = h_oos[i]

    oos_df["garch_h"] = h_oos[: len(oos_df)]
    # Regime thresholds from IS distribution (no OOS data in thresholds)
    lo_thresh = float(np.percentile(h_is, 25)) if len(h_is) >= 4 else 0.0
    hi_thresh = float(np.percentile(h_is, 75)) if len(h_is) >= 4 else float("inf")
    oos_regime = np.where(
        oos_df["garch_h"].values < lo_thresh, "LOW",
        np.where(oos_df["garch_h"].values > hi_thresh, "HIGH", "MED")
    ).astype(object)
    oos_df["garch_regime"] = oos_regime
    oos_df["size_mult"] = np.where(oos_regime == "LOW", 0.0,
                           np.where(oos_regime == "HIGH", 0.5, 1.0))

    return is_df, oos_df
