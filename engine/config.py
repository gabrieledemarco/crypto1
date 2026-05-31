"""engine/config.py — single source of truth for engine constants and enums."""
from enum import Enum


# ── Capital & sizing ──────────────────────────────────────────────────────────
INITIAL_CAPITAL: float = 10_000.0
HOURS_MONTH: int = 24 * 30

# ── Annualization factors (bars per year per timeframe) ───────────────────────
ANN_FACTORS: dict[str, int] = {
    "1m":  365 * 24 * 60,
    "5m":  365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2,
    "1h":  365 * 24,
    "4h":  365 * 6,
    "1d":  365,
    "1wk": 52,
    "1mo": 12,
}

# ── Backtest / pipeline limits ────────────────────────────────────────────────
BACKTEST_TIMEOUT: int = 300
SSE_STREAM_TIMEOUT: int = 660
BOOTSTRAP_N_RESAMPLES: int = 500
MAX_SWEEP_COMBOS: int = 10_000

# ── Parameter sweep ranges ────────────────────────────────────────────────────
SWEEP_SL_RANGE: list[float] = [1.0, 1.5, 2.0, 2.5, 3.0]
SWEEP_TP_RANGE: list[float] = [2.0, 3.0, 4.0, 5.0, 7.0]
SWEEP_HOUR_WINDOWS: list[tuple[int, int]] = [(6, 22), (8, 20), (0, 23)]

# ── WFO grid (kept small for per-fold IS optimisation speed) ─────────────────
WFO_SL_GRID: list[float] = [1.5, 2.0, 2.5, 3.0]
WFO_TP_GRID: list[float] = [2.0, 3.0, 4.0, 5.0, 6.0]


# ── Strategy version names (avoid magic strings) ─────────────────────────────
class StrategyVersion(str, Enum):
    V1_BASE    = "V1 Base"
    V2_COSTS   = "V2 +Costi"
    V4_GARCH   = "V4 +GARCH+Costi"
    V_AGENT    = "V_Agent"

    @classmethod
    def preference_order(cls) -> list["StrategyVersion"]:
        """Ordered list: pick best available version for metrics export."""
        return [cls.V_AGENT, cls.V4_GARCH, cls.V2_COSTS, cls.V1_BASE]
