"""engine/quant_stats.py — Standardised quantitative analysis tools."""
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore", message=".*Maximum Likelihood.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*covariance of the parameters.*", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*optimization.*", category=UserWarning)

HOURLY_PERIODS = 24 * 365  # annualisation factor for hourly bars


def compute_hurst(prices: np.ndarray) -> dict:
    """
    Hurst exponent via R/S analysis.
    H < 0.5 → mean-reverting, H ≈ 0.5 → random walk, H > 0.5 → trending.
    """
    try:
        from hurst import compute_Hc
        prices = np.asarray(prices, dtype=float)
        prices = prices[np.isfinite(prices)]
        if len(prices) < 100:
            return {"hurst": None, "error": "Need ≥100 prices"}
        H, c, _ = compute_Hc(prices, kind='price', simplified=True)
        regime = "trending" if H > 0.55 else ("mean-reverting" if H < 0.45 else "random-walk")
        return {"hurst": round(float(H), 4), "regime": regime}
    except Exception as e:
        return {"hurst": None, "error": str(e)}


def test_stationarity(prices: np.ndarray) -> dict:
    """
    ADF and KPSS stationarity tests on log-returns (statsmodels).
    ADF H0: unit root (non-stationary). Small p-value → stationary.
    KPSS H0: stationary. Small p-value → non-stationary.
    """
    try:
        from statsmodels.tsa.stattools import adfuller, kpss
        prices = np.asarray(prices, dtype=float)
        returns = np.diff(np.log(prices[prices > 0]))
        returns = returns[np.isfinite(returns)]
        if len(returns) < 20:
            return {"error": "Insufficient data"}

        adf_stat, adf_p, _, _, adf_crit, _ = adfuller(returns, autolag='AIC')
        try:
            kpss_stat, kpss_p, _, kpss_crit = kpss(returns, regression='c', nlags='auto')
        except Exception:
            kpss_stat, kpss_p, kpss_crit = None, None, {}

        stationary = bool(adf_p < 0.05)
        return {
            "adf_stat": round(float(adf_stat), 4),
            "adf_pvalue": round(float(adf_p), 4),
            "adf_stationary": stationary,
            "kpss_stat": round(float(kpss_stat), 4) if kpss_stat is not None else None,
            "kpss_pvalue": round(float(kpss_p), 4) if kpss_p is not None else None,
        }
    except Exception as e:
        return {"error": str(e)}


def compute_var_cvar(returns: np.ndarray, confidence: float = 0.95) -> dict:
    """
    Historical VaR and CVaR (Expected Shortfall) via quantstats.
    Returns values as positive percentages (loss convention).
    """
    try:
        import quantstats as qs
        r = pd.Series(np.asarray(returns, dtype=float)).dropna()
        if len(r) < 10:
            return {"var": None, "cvar": None, "error": "Insufficient data"}
        var = float(qs.stats.value_at_risk(r, confidence=confidence)) * -100
        cvar = float(qs.stats.conditional_value_at_risk(r, confidence=confidence)) * -100
        return {
            "var": round(var, 4),
            "cvar": round(cvar, 4),
            "confidence": confidence,
        }
    except Exception:
        # fallback: historical percentile method
        r = np.asarray(returns, dtype=float)
        r = r[np.isfinite(r)]
        if len(r) < 10:
            return {"var": None, "cvar": None, "error": "Insufficient data"}
        sorted_r = np.sort(r)
        idx = max(int(np.floor(len(sorted_r) * (1 - confidence))), 1)
        return {
            "var": round(float(-sorted_r[idx] * 100), 4),
            "cvar": round(float(-sorted_r[:idx].mean() * 100), 4),
            "confidence": confidence,
        }


def rolling_metrics(prices: np.ndarray, window: int = 30) -> dict:
    """Rolling volatility and Sharpe estimate via quantstats (hourly annualisation)."""
    try:
        import quantstats as qs
        prices = np.asarray(prices, dtype=float)
        rets = pd.Series(np.diff(np.log(prices[prices > 0]))).dropna()
        if len(rets) < window:
            return {"ann_vol": None, "sharpe": None}
        r = rets.iloc[-window:]
        ann_vol = float(r.std() * np.sqrt(HOURLY_PERIODS) * 100)
        sharpe = float(qs.stats.sharpe(r, periods=HOURLY_PERIODS))
        return {"ann_vol": round(ann_vol, 4), "sharpe": round(sharpe, 4)}
    except Exception:
        # fallback: raw numpy
        prices = np.asarray(prices, dtype=float)
        rets = np.diff(np.log(prices[prices > 0]))
        rets = rets[np.isfinite(rets)]
        if len(rets) < window:
            return {"ann_vol": None, "sharpe": None}
        r = rets[-window:]
        ann_factor = np.sqrt(HOURLY_PERIODS)
        ann_vol = float(np.std(r) * ann_factor * 100)
        sharpe = float(np.mean(r) / np.std(r) * ann_factor) if np.std(r) > 0 else 0.0
        return {"ann_vol": round(ann_vol, 4), "sharpe": round(sharpe, 4)}
