"""
01_data_download.py
===================
Scarica dati OHLCV reali da Yahoo Finance via yfinance.
Se yfinance non è disponibile, tenta Alpaca Markets (ALPACA_API_KEY / ALPACA_SECRET_KEY).
Se entrambe le fonti falliscono, il processo termina con errore — nessun dato sintetico.

Asset scaricati:
  BTC-USD  daily  2015-01-01 → oggi          → output/btc_daily.csv
  BTC-USD  hourly ultimi 730 giorni          → output/btc_hourly.csv
  ETH-USD  hourly ultimi 730 giorni          → output/eth_hourly.csv
  SOL-USD  hourly ultimi 730 giorni          → output/sol_hourly.csv

Dipendenze:
  pip install yfinance pandas requests
"""

import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Ticker map ────────────────────────────────────────────────────────────────
TICKERS = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
}

DAILY_START  = "2015-01-01"
HOURLY_DAYS  = 730   # yfinance limita hourly a ~730 giorni
HOURLY_START = "2023-01-01"


# ══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD via yfinance
# ══════════════════════════════════════════════════════════════════════════════

def _download(ticker: str, interval: str, start: str,
              end: str = None) -> pd.DataFrame:
    """
    Scarica dati da Yahoo Finance.
    Ritorna DataFrame OHLCV con DatetimeIndex; lancia eccezione se vuoto.
    """
    import yfinance as yf
    kw = dict(start=start, interval=interval, auto_adjust=True, progress=False)
    if end:
        kw["end"] = end
    df = yf.download(ticker, **kw)
    if df.empty:
        raise ValueError(f"Nessun dato ricevuto per {ticker} ({interval})")

    # yfinance a volte restituisce MultiIndex colonne → appiattisci
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "Date"
    df.dropna(inplace=True)
    return df


def download_real() -> bool:
    """
    Tenta di scaricare tutti i dati reali.
    Ritorna True se tutto è riuscito, False in caso di errore.
    """
    try:
        import yfinance as yf  # noqa: F401
    except ImportError:
        print("  yfinance non installato — usa: pip install yfinance")
        return False

    try:
        print(f"Download BTC-USD daily ({DAILY_START} → oggi)...")
        btc_d = _download("BTC-USD", "1d", start=DAILY_START)
        btc_d.to_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"))
        print(f"  OK: {len(btc_d)} righe  "
              f"{btc_d.index[0].date()} → {btc_d.index[-1].date()}  "
              f"${btc_d['Close'].iloc[-1]:,.0f}")

        print(f"Download BTC-USD hourly ({HOURLY_START} → oggi)...")
        btc_h = _download("BTC-USD", "1h", start=HOURLY_START)
        btc_h.to_csv(os.path.join(OUTPUT_DIR, "btc_hourly.csv"))
        print(f"  OK: {len(btc_h)} righe  "
              f"{btc_h.index[0]} → {btc_h.index[-1]}")

        print(f"Download ETH-USD hourly ({HOURLY_START} → oggi)...")
        eth_h = _download("ETH-USD", "1h", start=HOURLY_START)
        eth_h.to_csv(os.path.join(OUTPUT_DIR, "eth_hourly.csv"))
        print(f"  OK: {len(eth_h)} righe")

        print(f"Download SOL-USD hourly ({HOURLY_START} → oggi)...")
        sol_h = _download("SOL-USD", "1h", start=HOURLY_START)
        sol_h.to_csv(os.path.join(OUTPUT_DIR, "sol_hourly.csv"))
        print(f"  OK: {len(sol_h)} righe")

        return True

    except Exception as e:
        print(f"  Errore download: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD via Alpaca Markets (fallback a yfinance)
# ══════════════════════════════════════════════════════════════════════════════

ALPACA_BASE = "https://data.alpaca.markets"
_ALPACA_SYMBOLS = {"btc": "BTC/USD", "eth": "ETH/USD", "sol": "SOL/USD"}


def _alpaca_bars(api_key: str, secret_key: str,
                 symbol: str, timeframe: str, start: str) -> pd.DataFrame:
    """Download paginated bars from Alpaca crypto data API v1beta3."""
    import requests
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
    }
    params: dict = {"symbols": symbol, "timeframe": timeframe,
                    "start": start, "limit": 10000}
    rows: list = []
    url = f"{ALPACA_BASE}/v1beta3/crypto/bars"
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("bars", {}).get(symbol, [])
        rows.extend(batch)
        npt = data.get("next_page_token")
        if not npt:
            break
        params["page_token"] = npt
    if not rows:
        raise ValueError(f"Nessun dato Alpaca per {symbol} ({timeframe})")
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["t"]).dt.tz_localize(None)
    df.index.name = "Date"
    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                             "c": "Close", "v": "Volume"})
    return df[["Open", "High", "Low", "Close", "Volume"]].copy()


def download_alpaca(api_key: str, secret_key: str) -> bool:
    """Scarica OHLCV da Alpaca Markets. Ritorna True se tutto è riuscito."""
    try:
        import requests  # noqa: F401
    except ImportError:
        print("  requests non installato — usa: pip install requests")
        return False
    try:
        print(f"Download BTC/USD daily da Alpaca ({DAILY_START} → oggi)...")
        btc_d = _alpaca_bars(api_key, secret_key, "BTC/USD", "1Day", DAILY_START)
        btc_d.to_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"))
        print(f"  OK: {len(btc_d)} righe  "
              f"${btc_d['Close'].iloc[-1]:,.0f}")

        print(f"Download BTC/USD hourly da Alpaca ({HOURLY_START} → oggi)...")
        btc_h = _alpaca_bars(api_key, secret_key, "BTC/USD", "1Hour", HOURLY_START)
        btc_h.to_csv(os.path.join(OUTPUT_DIR, "btc_hourly.csv"))
        print(f"  OK: {len(btc_h)} righe")

        print("Download ETH/USD hourly da Alpaca...")
        eth_h = _alpaca_bars(api_key, secret_key, "ETH/USD", "1Hour", HOURLY_START)
        eth_h.to_csv(os.path.join(OUTPUT_DIR, "eth_hourly.csv"))
        print(f"  OK: {len(eth_h)} righe")

        print("Download SOL/USD hourly da Alpaca...")
        sol_h = _alpaca_bars(api_key, secret_key, "SOL/USD", "1Hour", HOURLY_START)
        sol_h.to_csv(os.path.join(OUTPUT_DIR, "sol_hourly.csv"))
        print(f"  OK: {len(sol_h)} righe")

        return True
    except Exception as exc:
        print(f"  Errore Alpaca: {exc}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  DATI SINTETICI (solo per sviluppo/test — non usare in produzione)
# ══════════════════════════════════════════════════════════════════════════════

np.random.seed(42)

ANCHORS = [
    ("2015-01-01",    310),
    ("2015-11-01",    390),
    ("2016-01-01",    430),
    ("2016-07-09",    650),
    ("2017-01-01",   1000),
    ("2017-12-17",  19800),
    ("2018-06-01",   7000),
    ("2018-12-15",   3200),
    ("2019-06-26",  13000),
    ("2019-12-31",   7200),
    ("2020-03-13",   5000),
    ("2020-05-11",   8700),
    ("2020-12-31",  29000),
    ("2021-04-14",  64000),
    ("2021-07-20",  32000),
    ("2021-11-10",  69000),
    ("2022-01-01",  47000),
    ("2022-06-18",  17800),
    ("2022-11-09",  16000),
    ("2023-01-01",  16600),
    ("2023-04-01",  28500),
    ("2023-10-01",  27000),
    ("2023-12-31",  42500),
    ("2024-01-01",  44000),
    ("2024-04-19",  65000),
    ("2024-07-01",  63000),
    ("2024-11-13",  93000),
    ("2025-01-01",  94000),
    ("2025-04-29",  95000),
]

VOL_REGIMES = {
    "2015": 0.70, "2016": 0.60, "2017": 0.95, "2018": 1.10,
    "2019": 0.75, "2020": 0.85, "2021": 0.90, "2022": 0.85,
    "2023": 0.50, "2024": 0.55, "2025": 0.50,
}

HOURLY_DRIFT = np.array([
    -0.00008, -0.00006, -0.00004, -0.00002,
     0.00001,  0.00002,  0.00003,  0.00005,
     0.00020,  0.00025,  0.00015,  0.00010,
     0.00008,  0.00010,  0.00025,  0.00030,
     0.00020,  0.00015,  0.00010,  0.00005,
     0.00003,  0.00001, -0.00003, -0.00005,
])
HOURLY_VOL = np.array([
    0.0025, 0.0022, 0.0020, 0.0019,
    0.0020, 0.0021, 0.0022, 0.0025,
    0.0040, 0.0045, 0.0042, 0.0038,
    0.0035, 0.0040, 0.0055, 0.0060,
    0.0055, 0.0050, 0.0045, 0.0038,
    0.0032, 0.0028, 0.0026, 0.0025,
])
DOW_MULT = np.array([1.0, 1.05, 1.10, 1.08, 1.02, 0.90, 0.85])


def _garch_var(T: int, omega: float, alpha: float, beta: float,
               innov: np.ndarray) -> np.ndarray:
    h = np.zeros(T)
    h[0] = omega / (1 - alpha - beta)
    for t in range(1, T):
        h[t] = omega + alpha * innov[t-1]**2 + beta * h[t-1]
    return h


def _synth_daily(start: str = "2015-01-01",
                 end:   str = "2025-04-30") -> pd.DataFrame:
    print("  Generazione dati giornalieri sintetici BTC (2015-2025)...")
    dates    = pd.date_range(start, end, freq="D")
    T        = len(dates)
    a_dates  = [pd.Timestamp(d) for d, _ in ANCHORS]
    a_log    = np.log([p for _, p in ANCHORS])
    d_num    = np.array([(d - dates[0]).days for d in dates], dtype=float)
    a_num    = np.array([(d - dates[0]).days for d in a_dates], dtype=float)
    log_tgt  = np.interp(d_num, a_num, a_log)

    daily_vol = np.array([VOL_REGIMES.get(str(d.year), 0.70) / np.sqrt(252)
                          for d in dates])
    raw = np.random.standard_t(df=4, size=T) / np.sqrt(4 / 2)
    h   = _garch_var(T, 0.02, 0.08, 0.88, raw)
    sc  = np.sqrt(h / h.mean())
    ret = daily_vol * sc * raw

    lp    = np.zeros(T)
    lp[0] = log_tgt[0]
    for t in range(1, T):
        lp[t] = lp[t-1] + (log_tgt[t] - lp[t-1]) * 0.04 + ret[t]
    close = np.exp(lp)

    iv   = daily_vol * sc * 0.6
    high = close * np.exp(np.abs(np.random.normal(0, iv)))
    low  = close * np.exp(-np.abs(np.random.normal(0, iv)))
    op   = np.roll(close, 1); op[0] = close[0]
    high = np.maximum(high, np.maximum(op, close))
    low  = np.minimum(low,  np.minimum(op, close))
    vol  = 1e9 * (1 + 2 * np.abs(ret / daily_vol)) * np.random.lognormal(0, 0.3, T)

    df = pd.DataFrame({"Open": op, "High": high, "Low": low,
                       "Close": close, "Volume": vol}, index=dates)
    df.index.name = "Date"
    return df


def _synth_hourly(daily: pd.DataFrame, asset: str = "btc",
                  start: str = "2023-01-01",
                  end:   str = "2025-04-30",
                  vol_mult: float = 1.0) -> pd.DataFrame:
    print(f"  Generazione dati orari sintetici {asset.upper()} ({start}-{end})...")
    dates  = pd.date_range(start, end, freq="h")
    T      = len(dates)
    start_ts = pd.Timestamp(start)
    sp = daily.loc[daily.index >= start_ts, "Close"].iloc[0]

    raw = np.random.standard_t(df=5, size=T) / np.sqrt(5 / 3)
    h   = _garch_var(T, 5e-7, 0.06, 0.92, raw)
    sc  = np.sqrt(h / h.mean())
    hrs = dates.hour.values
    dws = dates.dayofweek.values
    bdrift = HOURLY_DRIFT[hrs]
    bvol   = HOURLY_VOL[hrs] * DOW_MULT[dws] * vol_mult
    ret    = bdrift + bvol * sc * raw

    dc = {}
    for d, row in daily.loc[start_ts:].iterrows():
        dc[d.date()] = np.log(row["Close"])

    lp    = np.zeros(T)
    lp[0] = np.log(sp)
    for t in range(1, T):
        tgt  = dc.get(dates[t].date(), lp[t-1])
        lp[t] = lp[t-1] + 0.02 * (tgt - lp[t-1]) + ret[t]

    close = np.exp(lp)
    hv    = bvol * sc * 0.5
    high  = close * np.exp(np.abs(np.random.normal(0, hv)))
    low   = close * np.exp(-np.abs(np.random.normal(0, hv)))
    op    = np.roll(close, 1); op[0] = close[0]
    high  = np.maximum(high, np.maximum(op, close))
    low   = np.minimum(low,  np.minimum(op, close))
    vol   = 1e8 * HOURLY_VOL[hrs] / HOURLY_VOL.mean() * np.random.lognormal(0, 0.4, T)

    df = pd.DataFrame({"Open": op, "High": high, "Low": low,
                       "Close": close, "Volume": vol}, index=dates)
    df.index.name = "Date"
    return df


def generate_synthetic():
    """Genera tutti i file CSV sintetici come fallback."""
    print("Generazione dati sintetici (fallback)...")
    daily = _synth_daily()
    daily.to_csv(os.path.join(OUTPUT_DIR, "btc_daily.csv"))
    print(f"  btc_daily.csv: {len(daily)} righe  "
          f"${daily['Close'].min():,.0f} → ${daily['Close'].max():,.0f}")

    for asset, vm in [("btc", 1.0), ("eth", 0.9), ("sol", 1.27)]:
        h = _synth_hourly(daily, asset=asset, vol_mult=vm)
        h.to_csv(os.path.join(OUTPUT_DIR, f"{asset}_hourly.csv"))
        print(f"  {asset}_hourly.csv: {len(h)} righe")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("  01_data_download.py — BTC/ETH/SOL OHLCV")
    print("=" * 60)

    ok = download_real()   # prova yfinance

    if not ok:
        alp_key = os.environ.get("ALPACA_API_KEY", "").strip()
        alp_sec = os.environ.get("ALPACA_SECRET_KEY", "").strip()
        if alp_key and alp_sec:
            print("\nYahoo Finance non disponibile — tentativo via Alpaca Markets...")
            ok = download_alpaca(alp_key, alp_sec)
        else:
            print("\n  Nessuna chiave Alpaca configurata"
                  " (ALPACA_API_KEY / ALPACA_SECRET_KEY).")

    if not ok:
        print("\nERRORE: impossibile scaricare dati reali.")
        print("  • Verifica la connessione a Yahoo Finance, oppure")
        print("  • Configura ALPACA_API_KEY e ALPACA_SECRET_KEY nel dashboard.")
        sys.exit(1)

    print("\nFile generati:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith(".csv"):
            size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f"  {f:<35} {size/1024:>7.1f} KB")
