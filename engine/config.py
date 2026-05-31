"""
engine/config.py — single source of truth for shared constants.

Import from here instead of redefining in each router/engine file.
"""

# ── Capital ───────────────────────────────────────────────────────────────────

INITIAL_CAPITAL: float = 10_000.0

# ── Time ──────────────────────────────────────────────────────────────────────

HOURS_MONTH: int = 24 * 30

# Annualisation factors: bars per year for each timeframe
ANN_FACTORS: dict[str, int] = {
    "1m":  365 * 24 * 60,
    "5m":  365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2,
    "1h":  365 * 24,
    "4h":  365 * 6,
    "1d":  365,
    "1wk": 52,
}

ANN_FACTORS_ALT: dict[str, int] = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040,
    "30m": 17_520, "1h": 8_760,   "4h": 2_190,
    "1d": 365,     "1wk": 52,
}

# ── Backtest ──────────────────────────────────────────────────────────────────

BACKTEST_TIMEOUT: int = 300          # seconds before a run is force-killed
BOOTSTRAP_N_RESAMPLES: int = 500     # scipy.stats.bootstrap n_resamples
MAX_SWEEP_COMBOS: int = 10_000       # hard cap on parameter grid size
SSE_STREAM_TIMEOUT: int = 660        # seconds before orphaned SSE queue self-terminates

# Default sweep grids (used by run_optimization in backtest.py)
SWEEP_SL_RANGE: list[float] = [1.0, 1.5, 2.0, 2.5, 3.0]
SWEEP_TP_RANGE: list[float] = [2.0, 3.0, 4.0, 5.0, 7.0]
SWEEP_HOUR_WINDOWS: list[tuple[int, int]] = [(6, 22), (8, 20), (0, 23)]

# WFO grid (used by _best_params_on_is)
WFO_SL_GRID: list[float] = [1.5, 2.0, 2.5, 3.0]
WFO_TP_GRID: list[float] = [2.0, 3.0, 4.0, 5.0, 6.0]
