"""
06_validation.py
================
Statistical validation: Sharpe CI, permutation test, min track record, multiple comparison.
Input: output/trades.csv, output/enhanced_strategy_comparison.csv
Output: output/validation_results.json
"""

import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def sharpe_ci_bootstrap(equity_series, n_bootstrap=5000, confidence=0.95):
    """
    Bootstrap confidence interval for annualised Sharpe ratio.

    Parameters
    ----------
    equity_series : pd.Series
        Equity curve values (hourly).
    n_bootstrap : int
        Number of bootstrap resamples.
    confidence : float
        Confidence level (e.g. 0.95).

    Returns
    -------
    dict with keys: sharpe_point, ci_lower, ci_upper, ci_pct, n_bootstrap
    """
    equity = pd.Series(equity_series).dropna()
    ret = equity.pct_change().dropna().values

    if len(ret) < 5:
        return {
            "error": "Not enough data points (< 5 returns)",
            "sharpe_point": None,
            "ci_lower": None,
            "ci_upper": None,
            "ci_pct": int(confidence * 100),
            "n_bootstrap": n_bootstrap,
        }

    annualisation = np.sqrt(24 * 365)
    n = len(ret)

    # Point estimate
    std_ret = ret.std()
    sharpe_point = float((ret.mean() / std_ret * annualisation) if std_ret != 0 else 0.0)

    # Bootstrap resamples — vectorised: shape (n_bootstrap, n)
    rng = np.random.default_rng(42)
    samples = rng.choice(ret, size=(n_bootstrap, n), replace=True)
    sample_means = samples.mean(axis=1)
    sample_stds = samples.std(axis=1)

    # Avoid division by zero
    valid = sample_stds != 0
    bootstrap_sharpes = np.where(valid, sample_means / sample_stds * annualisation, 0.0)

    alpha = 1.0 - confidence
    ci_lower = float(np.percentile(bootstrap_sharpes, alpha / 2 * 100))
    ci_upper = float(np.percentile(bootstrap_sharpes, (1 - alpha / 2) * 100))

    return {
        "sharpe_point": sharpe_point,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "ci_pct": int(confidence * 100),
        "n_bootstrap": n_bootstrap,
    }


def permutation_test(trades_df, n_permutations=1000):
    """
    Permutation test: is the observed Sharpe statistically significant?

    Parameters
    ----------
    trades_df : pd.DataFrame
        DataFrame with at least a 'pnl' column.
    n_permutations : int
        Number of random permutations.

    Returns
    -------
    dict with keys: observed_sharpe, p_value, n_permutations, pct_rank
    """
    if not isinstance(trades_df, pd.DataFrame) or "pnl" not in trades_df.columns:
        return {
            "error": "trades_df must be a DataFrame with a 'pnl' column",
            "observed_sharpe": None,
            "p_value": None,
            "n_permutations": n_permutations,
            "pct_rank": None,
        }

    pnl = trades_df["pnl"].values
    n = len(pnl)

    if n < 5:
        return {
            "error": "Not enough trades (< 5)",
            "observed_sharpe": None,
            "p_value": None,
            "n_permutations": n_permutations,
            "pct_rank": None,
        }

    def _sharpe_from_pnl(arr):
        equity = np.cumsum(arr)
        ret = np.diff(equity)
        if len(ret) == 0 or ret.std() == 0:
            return 0.0
        return float(ret.mean() / ret.std() * np.sqrt(24 * 365))

    observed_sharpe = _sharpe_from_pnl(pnl)

    # Vectorise: each row is one permutation of pnl indices
    rng = np.random.default_rng(42)
    permuted_indices = np.argsort(
        rng.random((n_permutations, n)), axis=1
    )
    permuted_pnl = pnl[permuted_indices]  # shape (n_permutations, n)

    permuted_equity = np.cumsum(permuted_pnl, axis=1)
    # returns along each path: diff on axis=1
    permuted_ret = np.diff(permuted_equity, axis=1)

    perm_means = permuted_ret.mean(axis=1)
    perm_stds = permuted_ret.std(axis=1)
    valid = perm_stds != 0
    perm_sharpes = np.where(valid, perm_means / perm_stds * np.sqrt(24 * 365), 0.0)

    p_value = float(np.mean(perm_sharpes >= observed_sharpe))
    pct_rank = float(np.mean(perm_sharpes < observed_sharpe) * 100)

    return {
        "observed_sharpe": float(observed_sharpe),
        "p_value": p_value,
        "n_permutations": n_permutations,
        "pct_rank": pct_rank,
    }


def min_track_record(n_trades, sharpe):
    """
    Minimum track record check.

    Rule: strategy needs >= 20 OOS trades AND Sharpe > 0.5.

    Parameters
    ----------
    n_trades : int
    sharpe : float

    Returns
    -------
    dict with keys: ok, n_trades, sharpe, min_trades, min_sharpe, message
    """
    MIN_TRADES = 20
    MIN_SHARPE = 0.5

    ok = bool(n_trades >= MIN_TRADES and sharpe > MIN_SHARPE)

    if n_trades < MIN_TRADES and sharpe <= MIN_SHARPE:
        message = (
            f"FAIL: only {n_trades} trades (need {MIN_TRADES}) "
            f"and Sharpe {sharpe:.3f} (need > {MIN_SHARPE})"
        )
    elif n_trades < MIN_TRADES:
        message = f"FAIL: only {n_trades} trades (need >= {MIN_TRADES})"
    elif sharpe <= MIN_SHARPE:
        message = f"FAIL: Sharpe {sharpe:.3f} (need > {MIN_SHARPE})"
    else:
        message = (
            f"PASS: {n_trades} trades >= {MIN_TRADES} and Sharpe {sharpe:.3f} > {MIN_SHARPE}"
        )

    return {
        "ok": ok,
        "n_trades": int(n_trades),
        "sharpe": float(sharpe),
        "min_trades": MIN_TRADES,
        "min_sharpe": MIN_SHARPE,
        "message": message,
    }


def bonferroni_correction(n_combinations, alpha=0.05):
    """
    Bonferroni correction for multiple comparisons.

    Parameters
    ----------
    n_combinations : int
        Number of parameter combinations tested in grid search.
    alpha : float
        Raw significance level.

    Returns
    -------
    dict with keys: raw_alpha, corrected_alpha, n_combinations
    """
    n_combinations = max(1, int(n_combinations))
    corrected_alpha = float(alpha / n_combinations)

    return {
        "raw_alpha": float(alpha),
        "corrected_alpha": corrected_alpha,
        "n_combinations": n_combinations,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json as _json

    results = {}

    # ── Load trades ──────────────────────────────────────────────────────────
    trades_path = os.path.join(OUTPUT_DIR, "trades.csv")
    trades_df = None
    if os.path.exists(trades_path):
        try:
            trades_df = pd.read_csv(trades_path)
            print(f"Loaded trades.csv  ({len(trades_df)} rows)")
        except Exception as exc:
            print(f"Warning: could not load trades.csv — {exc}")
    else:
        print(f"Warning: {trades_path} not found")

    # ── Load mc_bootstrap_results (equity proxy) ──────────────────────────────
    mc_path = os.path.join(OUTPUT_DIR, "mc_bootstrap_results.csv")
    equity_series = None
    if os.path.exists(mc_path):
        try:
            mc_df = pd.read_csv(mc_path)
            # Use median equity path from final capitals as a scalar proxy;
            # build a synthetic equity series from trades if available, otherwise
            # use the p50 final capital linearly interpolated.
            if trades_df is not None and "pnl" in trades_df.columns:
                equity_series = pd.Series(
                    10_000 + trades_df["pnl"].cumsum().values,
                    name="equity",
                )
            else:
                p50 = mc_df.loc[mc_df["percentile"] == 50, "final_cap_bs"]
                if not p50.empty:
                    final_cap = float(p50.iloc[0])
                    equity_series = pd.Series(
                        np.linspace(10_000, final_cap, 500), name="equity"
                    )
            print(f"Loaded mc_bootstrap_results.csv")
        except Exception as exc:
            print(f"Warning: could not load mc_bootstrap_results.csv — {exc}")
    else:
        print(f"Warning: {mc_path} not found")

    # Fallback: build equity from trades if mc not available
    if equity_series is None and trades_df is not None and "pnl" in trades_df.columns:
        equity_series = pd.Series(
            10_000 + trades_df["pnl"].cumsum().values, name="equity"
        )

    # ── 1. Sharpe CI ─────────────────────────────────────────────────────────
    if equity_series is not None and len(equity_series) >= 5:
        print("Running Sharpe bootstrap CI...")
        sharpe_ci = sharpe_ci_bootstrap(equity_series)
        results["sharpe_ci"] = sharpe_ci
        print(f"  Sharpe point: {sharpe_ci.get('sharpe_point', 'N/A'):.3f}  "
              f"95% CI [{sharpe_ci.get('ci_lower', 'N/A'):.3f}, "
              f"{sharpe_ci.get('ci_upper', 'N/A'):.3f}]")
    else:
        results["sharpe_ci"] = {"error": "No equity series available"}
        print("Skipping Sharpe CI — no equity data")

    # ── 2. Permutation test ───────────────────────────────────────────────────
    if trades_df is not None and "pnl" in trades_df.columns:
        print("Running permutation test...")
        perm = permutation_test(trades_df)
        results["permutation_test"] = perm
        print(f"  Observed Sharpe: {perm.get('observed_sharpe', 'N/A'):.3f}  "
              f"p-value: {perm.get('p_value', 'N/A'):.4f}  "
              f"pct_rank: {perm.get('pct_rank', 'N/A'):.1f}%")
    else:
        results["permutation_test"] = {"error": "No trades data available"}
        print("Skipping permutation test — no trades data")

    # ── 3. Min track record ───────────────────────────────────────────────────
    n_tr = len(trades_df) if trades_df is not None else 0
    sharpe_pt = results.get("sharpe_ci", {}).get("sharpe_point") or 0.0
    print("Checking min track record...")
    mtr = min_track_record(n_tr, sharpe_pt)
    results["min_track_record"] = mtr
    print(f"  {mtr['message']}")

    # ── 4. Bonferroni correction ──────────────────────────────────────────────
    # Estimate n_combinations from optimization_results.csv if available
    opt_path = os.path.join(OUTPUT_DIR, "optimization_results.csv")
    n_combos = 1
    if os.path.exists(opt_path):
        try:
            opt_df = pd.read_csv(opt_path)
            n_combos = max(1, len(opt_df))
        except Exception:
            pass
    print(f"Running Bonferroni correction (n_combinations={n_combos})...")
    bonf = bonferroni_correction(n_combos)
    results["bonferroni"] = bonf
    print(f"  raw alpha={bonf['raw_alpha']}  corrected alpha={bonf['corrected_alpha']:.6f}")

    # ── Save results ──────────────────────────────────────────────────────────
    out_path = os.path.join(OUTPUT_DIR, "validation_results.json")
    with open(out_path, "w") as _f:
        _json.dump(results, _f, indent=2)
    print(f"\nSaved: {out_path}")
    print("Validation completata.")
