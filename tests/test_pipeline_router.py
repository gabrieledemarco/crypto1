"""
Tests for api/routers/pipeline.py — no external network required.
"""
import json
import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.routers.pipeline import (
    PipelineRequest,
    _resample,
    _TF_NORM,
    _YF_PERIOD,
    _ANN_FACTORS,
    _ACTIVE_HOURS,
)


# ── PipelineRequest validation ───────────────────────────────────────────────────────────────────

def test_pipeline_request_defaults():
    req = PipelineRequest()
    assert req.tickers == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert req.timeframes == ["1m", "5m", "15m", "1h"]
    assert req.max_iter == 40
    assert req.stop_sharpe == 1.5
    assert req.max_dd == 20.0
    assert req.period is None
