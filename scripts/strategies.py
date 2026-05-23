"""
scripts/strategies.py
=====================
Baseline strategy archetypes for the vibe optimization loop.
12 archetypes × 9 SL/TP combos = 108 unique baseline strategies.
"""

# Each tuple: (name, code_template)
# Placeholders: {sl}, {tp}  (floats, e.g. 2.0 and 4.5)
_ARCHETYPES: list[tuple[str, str]] = [

    ("ema_cross_fast", """\
def agent_fn(df, ind=None):
    df = df.copy()
    fast = ind("EMA", 8)  if ind else df["EMA50"]
    slow = ind("EMA", 21) if ind else df["EMA200"]
    xu = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    xd = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    df["signal"] = 0
    df.loc[xu, "signal"] =  1
    df.loc[xd, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("ema_cross_rsi", """\
def agent_fn(df, ind=None):
    df = df.copy()
    fast = ind("EMA", 20)  if ind else df["EMA50"]
    slow = ind("EMA", 100) if ind else df["EMA200"]
    rsi = df["RSI14"]
    xu = (fast > slow) & (fast.shift(1) <= slow.shift(1)) & (rsi < 65)
    xd = (fast < slow) & (fast.shift(1) >= slow.shift(1)) & (rsi > 35)
    df["signal"] = 0
    df.loc[xu, "signal"] =  1
    df.loc[xd, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("rsi_reversion", """\
def agent_fn(df, ind=None):
    df = df.copy()
    rsi = df["RSI14"]
    df["signal"] = 0
    df.loc[rsi < 30, "signal"] =  1
    df.loc[rsi > 70, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("rsi_trend", """\
def agent_fn(df, ind=None):
    df = df.copy()
    rsi  = df["RSI14"]
    bull = df["EMA50"] > df["EMA200"]
    df["signal"] = 0
    df.loc[bull  & (rsi < 35), "signal"] =  1
    df.loc[~bull & (rsi > 65), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("bb_reversion", """\
def agent_fn(df, ind=None):
    import numpy as np
    df = df.copy()
    mid   = df["Close"].rolling(20).mean()
    std   = df["Close"].rolling(20).std()
    upper = mid + 2.0 * std
    lower = mid - 2.0 * std
    df["signal"] = 0
    df.loc[df["Close"] < lower, "signal"] =  1
    df.loc[df["Close"] > upper, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("macd_cross", """\
def agent_fn(df, ind=None):
    df = df.copy()
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    xu = (macd > sig) & (macd.shift(1) <= sig.shift(1))
    xd = (macd < sig) & (macd.shift(1) >= sig.shift(1))
    df["signal"] = 0
    df.loc[xu, "signal"] =  1
    df.loc[xd, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("donchian_20", """\
def agent_fn(df, ind=None):
    df = df.copy()
    hi  = df["High"].rolling(20).max().shift(1)
    lo  = df["Low"].rolling(20).min().shift(1)
    rsi = df["RSI14"]
    df["signal"] = 0
    df.loc[(df["Close"] > hi) & (rsi <= 75), "signal"] =  1
    df.loc[(df["Close"] < lo) & (rsi >= 25), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("donchian_10_trend", """\
def agent_fn(df, ind=None):
    df = df.copy()
    hi10 = df["High"].rolling(10).max().shift(1)
    lo10 = df["Low"].rolling(10).min().shift(1)
    bull = df["EMA50"] > df["EMA200"]
    df["signal"] = 0
    df.loc[(df["Close"] > hi10) &  bull, "signal"] =  1
    df.loc[(df["Close"] < lo10) & ~bull, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("momentum_5bar", """\
def agent_fn(df, ind=None):
    df = df.copy()
    ret5 = df["Close"].pct_change(5)
    thr  = df["ATR14"] / df["Close"] * 0.5
    rsi  = df["RSI14"]
    df["signal"] = 0
    df.loc[(ret5 >  thr) & (rsi < 75), "signal"] =  1
    df.loc[(ret5 < -thr) & (rsi > 25), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("vwap_reversion", """\
def agent_fn(df, ind=None):
    df = df.copy()
    pv   = df["Close"] * df["Volume"]
    vwap = pv.rolling(24).sum() / (df["Volume"].rolling(24).sum() + 1e-10)
    dev  = (df["Close"] - vwap) / (df["ATR14"] + 1e-10)
    df["signal"] = 0
    df.loc[dev < -1.5, "signal"] =  1
    df.loc[dev >  1.5, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("bb_squeeze", """\
def agent_fn(df, ind=None):
    df = df.copy()
    mid = df["Close"].rolling(20).mean()
    std = df["Close"].rolling(20).std()
    bw  = 2.0 * std / (mid + 1e-10)
    sqz = bw < bw.rolling(50).quantile(0.2)
    mom = df["Close"] - df["Close"].shift(5)
    df["signal"] = 0
    df.loc[sqz & (mom > 0), "signal"] =  1
    df.loc[sqz & (mom < 0), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),

    ("adaptive_regime", """\
def agent_fn(df, ind=None):
    df = df.copy()
    rsi  = df["RSI14"]
    fast = ind("EMA", 50)  if ind else df["EMA50"]
    slow = ind("EMA", 200) if ind else df["EMA200"]
    hi20 = df["High"].rolling(20).max().shift(1)
    lo20 = df["Low"].rolling(20).min().shift(1)
    reg  = (fast - slow).abs() / (df["ATR14"] + 1e-10)
    trending = reg > 2.0
    df["signal"] = 0
    df.loc[ trending & (df["Close"] > hi20), "signal"] =  1
    df.loc[ trending & (df["Close"] < lo20), "signal"] = -1
    df.loc[~trending & (rsi < 30), "signal"] =  1
    df.loc[~trending & (rsi > 70), "signal"] = -1
    df["SL_dist"] = df["ATR14"] * {sl}
    df["TP_dist"] = df["ATR14"] * {tp}
    return df"""),
]

# SL/TP schedule: (sl_mult, tp_mult)
# Covers conservative → aggressive risk-reward profiles
_SL_TP: list[tuple[float, float]] = [
    (1.5, 3.0),  # RR 2.0 — conservative
    (2.0, 4.0),  # RR 2.0
    (2.5, 5.0),  # RR 2.0
    (3.0, 6.0),  # RR 2.0
    (2.0, 6.0),  # RR 3.0 — high RR
    (1.8, 5.4),  # RR 3.0
    (2.5, 7.5),  # RR 3.0
    (3.0, 9.0),  # RR 3.0
    (1.5, 4.5),  # RR 3.0 — tight SL
]


def get_archetype(iteration: int) -> tuple[str, str, float, float]:
    """
    Map 1-based iteration → (name, code, sl, tp).
    Cycles: all archetypes first (inner), then SL/TP combos (outer).
    """
    n_a      = len(_ARCHETYPES)
    n_s      = len(_SL_TP)
    arch_idx = (iteration - 1) % n_a
    sl_idx   = ((iteration - 1) // n_a) % n_s
    name, code_tpl = _ARCHETYPES[arch_idx]
    sl, tp = _SL_TP[sl_idx]
    return name, code_tpl.format(sl=sl, tp=tp), sl, tp
