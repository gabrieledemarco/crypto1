from pydantic import BaseModel, Field, field_validator
from typing import Any, Literal, Optional


class RunParams(BaseModel):
    ticker: str = Field("BTC-USD", min_length=1, max_length=20)
    timeframe: str = Field("1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d|1wk|1mo)$")
    sl_mult: float = Field(2.0, ge=0.5, le=10.0)
    tp_mult: float = Field(5.0, ge=1.0, le=20.0)
    active_hours: list[int] = Field([6, 22], min_length=2, max_length=2)
    risk_per_trade: float = Field(0.01, ge=0.001, le=0.1)
    commission: float = Field(0.0004, ge=0.0, le=0.01)
    slippage: float = Field(0.0001, ge=0.0, le=0.01)
    direction: Literal["ALL", "LONG", "SHORT"] = "ALL"
    run_wfo: bool = True
    run_sweep: bool = True
    run_mc: bool = True
    mc_sims: int = Field(1000, ge=100, le=10_000)
    mc_bars: Optional[int] = Field(None, ge=1, le=100_000)

    @field_validator("active_hours")
    @classmethod
    def validate_hours(cls, v):
        if len(v) != 2 or not all(0 <= h <= 23 for h in v) or v[0] >= v[1]:
            raise ValueError("active_hours must be [start, end] with 0 <= start < end <= 23")
        return v


class RunCreate(BaseModel):
    name: Optional[str] = None
    params: RunParams = RunParams()
    strategy_id: Optional[str] = None


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


class VibeGenerateRequest(BaseModel):
    prompt: str = ""
    asset: str = "BTC-USD"
    timeframe: str = "1h"
    n_candidates: int = 1
    asset_stats: Optional[dict] = None
