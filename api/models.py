from pydantic import BaseModel
from typing import Any, Optional


class RunParams(BaseModel):
    ticker: str = "BTC-USD"
    timeframe: str = "1h"
    sl_mult: float = 2.0
    tp_mult: float = 5.0
    active_hours: list[int] = [6, 22]
    risk_per_trade: float = 0.01
    commission: float = 0.0004
    slippage: float = 0.0001
    direction: str = "ALL"
    run_wfo: bool = True
    run_sweep: bool = True
    run_mc: bool = True
    mc_sims: int = 1000
    mc_bars: Optional[int] = None


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
    prompt: str
    asset: str = "BTC-USD"
    n_candidates: int = 1
