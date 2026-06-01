from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Literal, Optional


class RunParams(BaseModel):
    ticker: str = Field(
        "BTC-USD",
        min_length=1, max_length=20,
        pattern=r"^[A-Z0-9][A-Z0-9\.\-]{0,19}$",
    )
    timeframe: str = Field("1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d|1wk|1mo)$")
    sl_mult: float = Field(2.0, ge=0.5, le=10.0)
    tp_mult: float = Field(5.0, ge=1.0, le=20.0)
    active_hours: list[int] = Field([6, 22], min_length=2, max_length=2)
    # Frontend sends percentage (1.0 = 1%); engine expects decimal (0.01 = 1%).
    # Accept both forms — normalize_risk converts anything > 0.1 from % to decimal.
    risk_per_trade: float = Field(0.01, ge=0.0001, le=100.0)
    commission: float = Field(0.0004, ge=0.0, le=0.01)
    slippage: float = Field(0.0001, ge=0.0, le=0.01)
    direction: Literal["ALL", "LONG", "SHORT"] = "ALL"
    run_wfo: bool = True
    run_sweep: bool = True
    run_mc: bool = True
    mc_sims: int = Field(1000, ge=100, le=10_000)
    mc_bars: Optional[int] = Field(None, ge=0, le=100_000)
    wfo_is_window: int = Field(500, ge=50, le=10_000)
    wfo_oos_window: int = Field(100, ge=10, le=5_000)
    max_positions: int = Field(1, ge=1, le=10)
    cooldown_bars: int = Field(0, ge=0, le=100)
    initial_capital: float = Field(10_000, ge=100, le=10_000_000)
    leverage: float = Field(1.0, ge=1.0, le=100.0)
    trailing_stop: bool = False
    trailing_stop_method: Literal["atr", "pct", "pips"] = "atr"
    trailing_stop_value: float = Field(1.5, ge=0.1, le=500.0)
    position_size_method: Literal["risk_pct", "fixed_pct"] = "risk_pct"

    @field_validator("active_hours")
    @classmethod
    def validate_hours(cls, v):
        if len(v) != 2 or not all(0 <= h <= 23 for h in v):
            raise ValueError("active_hours must be [start, end] with 0 <= h <= 23")
        # Allow midnight-crossing ranges (e.g. [22, 6]) by wrapping end hour
        if v[0] == v[1]:
            raise ValueError("active_hours start and end must differ")
        return v

    @model_validator(mode="after")
    def validate_tp_gt_sl(self) -> "RunParams":
        if self.tp_mult <= self.sl_mult:
            raise ValueError(
                f"tp_mult ({self.tp_mult}) must be greater than sl_mult ({self.sl_mult})"
            )
        return self

    @field_validator("risk_per_trade")
    @classmethod
    def normalize_risk(cls, v: float) -> float:
        # Convert % form (e.g. 1.0) → decimal (0.01); leave decimal form unchanged.
        return v / 100 if v >= 0.1 else v

    @field_validator("mc_bars", mode="before")
    @classmethod
    def normalize_mc_bars(cls, v):
        # Frontend sends 0 when "auto"; treat 0/None as None (engine picks automatically).
        if v is None or v == 0:
            return None
        return v


class RunCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    params: RunParams = RunParams()
    strategy_id: Optional[str] = Field(
        None,
        pattern=r"^[0-9a-f]{8,64}$",
        description="Hex strategy ID (8-64 chars)",
    )


class AssetFetch(BaseModel):
    ticker: str
    source: str = "yfinance"
    period: str = "2y"
    interval: str = "1d"


class StrategyCreate(BaseModel):
    name: str
    strategy_type: str = "other"
    config: dict = {}
    code: str = ""
    status: str = "research"


class BackfillRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    interval: str = Field("1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d)$")


class VibeGenerateRequest(BaseModel):
    prompt: str = ""
    asset: str = "BTC-USD"
    timeframe: str = "1h"
    n_candidates: int = 1
    asset_stats: Optional[dict] = None
    quant_analysis: Optional[dict] = None
    garch_forecast: Optional[dict] = None
