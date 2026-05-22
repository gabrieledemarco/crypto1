"""engine/montecarlo.py — Bootstrap MC and stress tests. Pure computation."""
import numpy as np


def run_bootstrap(pnl: np.ndarray, n_sims: int = 1000, n_bars: int | None = None,
                  initial_capital: float = 10_000) -> dict:
    """Bootstrap Monte Carlo simulation.

    n_bars: trades per simulation path; defaults to len(pnl) when None/0.
    """
    K = len(pnl)
    path_len = n_bars if (n_bars and 0 < n_bars) else K
    idx = np.random.randint(0, K, size=(n_sims, path_len))
    sim = pnl[idx]
    eq  = initial_capital + np.cumsum(sim, axis=1)

    final       = eq[:, -1]
    cagr_arr    = ((final / initial_capital) ** (1 / max((K / (24 * 365)), 0.1)) - 1) * 100
    # Vectorized max-drawdown: eq shape (n_sims, path_len)
    running_max = np.maximum.accumulate(eq, axis=1)
    dd_matrix   = (eq - running_max) / running_max * 100   # negative values
    max_dd_arr  = dd_matrix.min(axis=1)                    # worst dd per sim
    sharpe_arr  = np.array([
        (np.diff(e) / initial_capital).mean() / (np.diff(e) / initial_capital).std() * np.sqrt(24 * 365)
        if (np.diff(e) / initial_capital).std() > 0 else 0
        for e in eq
    ])
    win_rates = (sim > 0).mean(axis=1) * 100  # per-simulation win-rate distribution

    sorted_finals = np.sort(final)
    var_idx = int(len(sorted_finals) * 0.05)
    var_95  = float(sorted_finals[var_idx])                              # 5th pct of final capital
    cvar_95 = float(sorted_finals[:max(1, var_idx)].mean())             # mean of worst 5%

    return {
        "final_capital": final,
        "cagr_pct":      cagr_arr,
        "sharpe":        sharpe_arr,
        "max_dd_pct":    max_dd_arr,
        "equity_matrix": eq,
        "win_rates":     win_rates,
        "var_95":        var_95,
        "cvar_95":       cvar_95,
    }


def run_stress(pnl: np.ndarray,
               initial_capital: float = 10_000) -> list:
    """Stress test scenarios."""
    scenarios = [
        ("Worst 10% trade risampling",  lambda x: x[x <= np.percentile(x, 10)]),
        ("Drawdown consecutivo ×3",     lambda x: np.concatenate([x[x < 0] * 1.5, x[x >= 0]])),
        ("Commissioni raddoppiate",     lambda x: x - abs(x) * 0.002),
        ("50% meno trade",             lambda x: x[::2]),
    ]
    rows = []
    for label, transform in scenarios:
        try:
            stressed  = transform(pnl.copy())
            if len(stressed) < 5:
                continue
            eq        = initial_capital + np.cumsum(stressed)
            final_cap = float(eq[-1])
            ret       = final_cap / initial_capital - 1
            dd        = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
            rows.append({
                "scenario":         label,
                "final_cap_usd":    round(final_cap, 2),
                "total_return_pct": round(ret * 100, 2),
                "max_drawdown_pct": round(float(dd), 2),
                "n_trades":         len(stressed),
            })
        except Exception:
            pass
    return rows
