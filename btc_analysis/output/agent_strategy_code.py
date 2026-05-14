"""
Agent strategy: Stat-Derived Trend Following — BTC-USD
Type: trend_following  |  Source: stats_derived
"""
import numpy as np
import pandas as pd

def generate_signals_agent(df):
    df = df.copy()
    # Active window: UTC 5-11 (best hours [6, 7, 9, 10])
    time_ok = (df["hour"] >= 5) & (df["hour"] <= 11)
    # Trend filter: EMA50/EMA200 (Hurst=0.592 → trend following)
    trend_long  = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]
    # Entry: price breaks 6-bar rolling high/low
    bo_long  = df["Close"] > df["RollHigh6"]
    bo_short = df["Close"] < df["RollLow6"]
    # Momentum confirmation: short EMA slope
    ema20 = df["Close"].ewm(span=20, adjust=False).mean()
    mom_long  = ema20 > ema20.shift(3)
    mom_short = ema20 < ema20.shift(3)
    # RSI: avoid overbought/oversold extremes
    rsi_long  = df["RSI14"] < 68
    rsi_short = df["RSI14"] > 32
    # Volatility filter: require active market
    atr_ok = df["ATR_pct"] > 0.0025
    # GARCH regime filter (persistence=0.9595 → clusters)
    if "garch_regime" in df.columns:
        garch_ok = df["garch_regime"] != "LOW"
    else:
        garch_ok = True
    df["signal"] = 0
    longs  = bo_long  & trend_long  & mom_long  & rsi_long  & atr_ok & garch_ok & time_ok
    shorts = bo_short & trend_short & mom_short & rsi_short & atr_ok & garch_ok & time_ok
    df.loc[longs,  "signal"] =  1
    df.loc[shorts, "signal"] = -1
    # SL=2.5×ATR (kurtosis=8.95→fat tails), TP=6.5×ATR→R:R=2.6:1
    df["SL_dist"] = df["ATR14"] * 2.5
    df["TP_dist"] = df["ATR14"] * 6.5
    return df

