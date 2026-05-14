"""
Agent strategy: Stat-Derived Trend Following — BTC-USD
Type: trend_following  |  Source: stats_derived
"""
import numpy as np
import pandas as pd

def generate_signals_agent(df):
    df = df.copy()
    # Two best trading windows: EU morning (6-10 UTC) + US open (13-17 UTC)
    # Avg hourly returns: 9h=4.9bps, 10h=3.0, 15h=2.4, 17h=2.2, 13h=1.9, 6h=1.8, 7h=1.7
    time_ok = ((df["hour"] >= 6) & (df["hour"] <= 10)) | ((df["hour"] >= 13) & (df["hour"] <= 17))
    # Trend filter: require clear EMA50/EMA200 gap (Hurst=0.592 → trend following)
    trend_long  = df["EMA50"] > df["EMA200"] * 1.001
    trend_short = df["EMA50"] < df["EMA200"] * 0.999
    # Entry: price breaks 6-bar rolling high/low
    bo_long  = df["Close"] > df["RollHigh6"]
    bo_short = df["Close"] < df["RollLow6"]
    # RSI: avoid overbought/oversold extremes
    rsi_long  = df["RSI14"] < 70
    rsi_short = df["RSI14"] > 30
    # Volatility filter: require active market
    atr_ok = df["ATR_pct"] > 0.002
    # GARCH regime filter (persistence=0.9595 → volatility clustering)
    if "garch_regime" in df.columns:
        garch_ok = df["garch_regime"] != "LOW"
    else:
        garch_ok = True
    df["signal"] = 0
    longs  = bo_long  & trend_long  & rsi_long  & atr_ok & garch_ok & time_ok
    shorts = bo_short & trend_short & rsi_short & atr_ok & garch_ok & time_ok
    df.loc[longs,  "signal"] =  1
    df.loc[shorts, "signal"] = -1
    # SL=2.5×ATR (kurtosis=8.95→fat tails), TP=7.0×ATR→R:R=2.8:1
    df["SL_dist"] = df["ATR14"] * 2.5
    df["TP_dist"] = df["ATR14"] * 7.0
    return df
