"""
Agent strategy: ATR Breakout + GARCH Filter (V5 Default)
Type: breakout  |  Source: default
"""
import numpy as np
import pandas as pd

def generate_signals_agent(df):
    """Default V5 strategy: ATR breakout + GARCH filter."""
    df = df.copy()
    time_ok     = (df["hour"] >= 6) & (df["hour"] <= 22)
    vol_ok      = df["ATR_pct"] > 0.003
    trend_long  = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]
    bo_long     = df["Close"] > df["RollHigh6"]
    bo_short    = df["Close"] < df["RollLow6"]
    rsi_ok_l    = df["RSI14"] < 70
    rsi_ok_s    = df["RSI14"] > 30
    if "garch_regime" in df.columns:
        regime_ok = df["garch_regime"] != "LOW"
    else:
        regime_ok = True
    df["signal"] = 0
    df.loc[bo_long  & trend_long  & rsi_ok_l & time_ok & vol_ok & regime_ok, "signal"] =  1
    df.loc[bo_short & trend_short & rsi_ok_s & time_ok & vol_ok & regime_ok, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * 2.0
    df["TP_dist"] = df["ATR14"] * 5.0
    return df

