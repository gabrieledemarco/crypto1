"""
BTC/USD Synthetic Historical Data Generator
============================================
Genera dati sintetici realistici con le stesse proprietà statistiche di BTC/USD storico:
- Daily OHLCV: 10 anni (2015-2025) con GARCH volatility + fat tails + regime switching
- Hourly OHLCV: 2 anni (2023-2025) con intraday seasonality + sessioni Asia/EU/USA

I dati rispettano i prezzi di riferimento storici reali, la struttura di correlazione
e le principali anomalie di mercato (halving bull run, bear market, volatility clustering).
"""

import numpy as np
import pandas as pd
import os

np.random.seed(42)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Price anchors storici reali ──────────────────────────────────────────────
ANCHORS = [
    ("2015-01-01",    310),
    ("2015-11-01",    390),
    ("2016-01-01",    430),
    ("2016-07-09",    650),    # halving 2
    ("2017-01-01",    1000),
    ("2017-12-17",   19800),   # ATH 2017
    ("2018-06-01",    7000),
    ("2018-12-15",    3200),
    ("2019-06-26",   13000),
    ("2019-12-31",    7200),
    ("2020-03-13",    5000),   # COVID crash
    ("2020-05-11",    8700),   # halving 3
    ("2020-12-31",   29000),
    ("2021-04-14",   64000),   # ATH 2021
    ("2021-07-20",   32000),
    ("2021-11-10",   69000),   # ATH 2021 (vero)
    ("2022-01-01",   47000),
    ("2022-06-18",   17800),
    ("2022-11-09",   16000),   # FTX crash
    ("2023-01-01",   16600),
    ("2023-04-01",   28500),
    ("2023-10-01",   27000),
    ("2023-12-31",   42500),
    ("2024-01-01",   44000),
    ("2024-04-19",   65000),   # halving 4
    ("2024-07-01",   63000),
    ("2024-11-13",   93000),
    ("2025-01-01",   94000),
    ("2025-04-29",   95000),
]

# Volatilità annualizzata per regime (approssimata su storia reale)
VOL_REGIMES = {
    "2015": 0.70,
    "2016": 0.60,
    "2017": 0.95,
    "2018": 1.10,
    "2019": 0.75,
    "2020": 0.85,
    "2021": 0.90,
    "2022": 0.85,
    "2023": 0.50,
    "2024": 0.55,
    "2025": 0.50,
}


def garch_variance(T: int, omega: float, alpha: float, beta: float,
                   innov: np.ndarray) -> np.ndarray:
    """GARCH(1,1) variance sequence."""
    h = np.zeros(T)
    h[0] = omega / (1 - alpha - beta)
    for t in range(1, T):
        h[t] = omega + alpha * innov[t-1]**2 + beta * h[t-1]
    return h


def generate_daily(start="2015-01-01", end="2025-04-30") -> pd.DataFrame:
    """
    Genera serie giornaliera OHLCV con:
    - Drift calcolato dagli anchor points
    - GARCH(1,1) volatility clustering
    - Innovazioni t-Student (fat tails, df=4)
    - Price forcing soft verso gli anchor points
    """
    print("Generazione dati giornalieri sintetici (2015-2025)...")
    dates = pd.date_range(start, end, freq="D")
    T = len(dates)

    # Build per-day target drift from anchors (log-space interpolation)
    anchor_dates = [pd.Timestamp(d) for d, _ in ANCHORS]
    anchor_prices = np.array([p for _, p in ANCHORS], dtype=float)
    anchor_log = np.log(anchor_prices)

    # Interpolate log-price target at each date
    date_num = np.array([(d - dates[0]).days for d in dates], dtype=float)
    anchor_num = np.array([(d - dates[0]).days for d in anchor_dates], dtype=float)
    log_target = np.interp(date_num, anchor_num, anchor_log)

    # Per-year volatility lookup
    def get_vol(d: pd.Timestamp) -> float:
        y = str(d.year)
        return VOL_REGIMES.get(y, 0.70)

    daily_vol = np.array([get_vol(d) / np.sqrt(252) for d in dates])

    # GARCH(1,1) innovations (t-student df=4 for fat tails)
    nu = 4.0
    raw_innov = np.random.standard_t(df=nu, size=T)
    raw_innov /= np.sqrt(nu / (nu - 2))   # normalize to unit variance

    omega = 0.02
    alpha = 0.08
    beta = 0.88
    h = garch_variance(T, omega, alpha, beta, raw_innov)
    garch_scale = np.sqrt(h / h.mean())    # normalize so mean h ≈ 1

    returns = daily_vol * garch_scale * raw_innov

    # Soft anchor forcing: pull toward target log price
    log_price = np.zeros(T)
    log_price[0] = log_target[0]
    pull_strength = 0.04   # soft reversion toward target path

    for t in range(1, T):
        gap = log_target[t] - log_price[t-1]
        drift = gap * pull_strength
        log_price[t] = log_price[t-1] + drift + returns[t]

    close = np.exp(log_price)

    # OHLCV from close
    intra_vol = daily_vol * garch_scale * 0.6  # intra-day range
    high = close * np.exp(np.abs(np.random.normal(0, intra_vol)))
    low  = close * np.exp(-np.abs(np.random.normal(0, intra_vol)))
    open_ = np.roll(close, 1)
    open_[0] = close[0] * np.exp(np.random.normal(0, daily_vol[0]))

    # Ensure OHLC consistency
    high = np.maximum(high, np.maximum(open_, close))
    low  = np.minimum(low, np.minimum(open_, close))

    volume_base = 1e9
    volume = volume_base * (1 + 2 * np.abs(returns / daily_vol)) * np.random.lognormal(0, 0.3, T)

    df = pd.DataFrame({
        "Open":   open_,
        "High":   high,
        "Low":    low,
        "Close":  close,
        "Volume": volume,
    }, index=dates)
    df.index.name = "Date"
    df.to_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"))
    print(f"  Daily rows: {T} | {dates[0].date()} → {dates[-1].date()}")
    print(f"  Price range: ${close.min():,.0f} → ${close.max():,.0f}")
    return df


# ── Hourly data generator ─────────────────────────────────────────────────────

# Intraday return profile (UTC) based on empirical BTC patterns:
# Higher activity at EU open (08:00), US open (14:00-15:00)
HOURLY_DRIFT = np.array([
    -0.00008, -0.00006, -0.00004, -0.00002,  # 00-03 Asia quiet
     0.00001,  0.00002,  0.00003,  0.00005,  # 04-07 Asia late
     0.00020,  0.00025,  0.00015,  0.00010,  # 08-11 EU open
     0.00008,  0.00010,  0.00025,  0.00030,  # 12-15 US open
     0.00020,  0.00015,  0.00010,  0.00005,  # 16-19 US session
     0.00003,  0.00001, -0.00003, -0.00005,  # 20-23 US close
])

HOURLY_VOL = np.array([
    0.0025, 0.0022, 0.0020, 0.0019,  # 00-03
    0.0020, 0.0021, 0.0022, 0.0025,  # 04-07
    0.0040, 0.0045, 0.0042, 0.0038,  # 08-11
    0.0035, 0.0040, 0.0055, 0.0060,  # 12-15
    0.0055, 0.0050, 0.0045, 0.0038,  # 16-19
    0.0032, 0.0028, 0.0026, 0.0025,  # 20-23
])

DOW_MULT = np.array([1.0, 1.05, 1.10, 1.08, 1.02, 0.90, 0.85])  # Mon-Sun


def generate_hourly(start="2023-01-01", end="2025-04-30") -> pd.DataFrame:
    """Genera dati orari con intraday seasonality."""
    print("Generazione dati orari sintetici (2023-2025)...")
    dates = pd.date_range(start, end, freq="h")
    T = len(dates)

    # Anchor from daily
    daily = pd.read_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"),
                        index_col="Date", parse_dates=True)
    daily.columns = [c[0] if isinstance(c, tuple) else c for c in daily.columns]

    # Start price from daily
    start_ts = pd.Timestamp(start)
    start_price = daily.loc[daily.index >= start_ts, "Close"].iloc[0]

    # GARCH hourly
    nu = 5.0
    raw_innov = np.random.standard_t(df=nu, size=T) / np.sqrt(nu / (nu - 2))
    omega_h = 0.0000005
    alpha_h = 0.06
    beta_h  = 0.92
    h = garch_variance(T, omega_h, alpha_h, beta_h, raw_innov)
    garch_scale = np.sqrt(h / h.mean())

    hours = dates.hour.values
    dows  = dates.dayofweek.values
    base_drift = HOURLY_DRIFT[hours]
    base_vol   = HOURLY_VOL[hours] * DOW_MULT[dows]

    returns = base_drift + base_vol * garch_scale * raw_innov

    # Soft anchor to daily closes
    log_price = np.zeros(T)
    log_price[0] = np.log(start_price)

    daily_closes = {}
    for d, row in daily.loc[start_ts:].iterrows():
        daily_closes[d.date()] = np.log(row["Close"])

    pull = 0.02
    for t in range(1, T):
        d = dates[t].date()
        target = daily_closes.get(d, log_price[t-1])
        gap = target - log_price[t-1]
        log_price[t] = log_price[t-1] + pull * gap + returns[t]

    close = np.exp(log_price)
    h_vol = base_vol * garch_scale * 0.5
    high  = close * np.exp(np.abs(np.random.normal(0, h_vol)))
    low   = close * np.exp(-np.abs(np.random.normal(0, h_vol)))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(high, np.maximum(open_, close))
    low  = np.minimum(low, np.minimum(open_, close))

    vol_base = 1e8
    volume = vol_base * HOURLY_VOL[hours] / HOURLY_VOL.mean() * np.random.lognormal(0, 0.4, T)

    df = pd.DataFrame({
        "Open":   open_,
        "High":   high,
        "Low":    low,
        "Close":  close,
        "Volume": volume,
    }, index=dates)
    df.index.name = "Date"
    df.to_csv(os.path.join(OUTPUT_DIR, "btc_hourly.csv"))
    print(f"  Hourly rows: {T} | {dates[0]} → {dates[-1]}")
    return df


if __name__ == "__main__":
    daily = generate_daily()
    hourly = generate_hourly()
    print("\nDati sintetici generati in output/")
