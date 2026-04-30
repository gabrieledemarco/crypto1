"""
download_real_data_local.py
===========================
ESEGUI QUESTO SCRIPT SUL TUO PC (non in questo ambiente).

Scarica dati OHLCV reali da Yahoo Finance via yfinance e li salva
nella cartella output/ nel formato atteso dalla pipeline.

Setup:
  pip install yfinance pandas

Esecuzione:
  python3 download_real_data_local.py

Output (copia questi file in btc_analysis/output/ sul server):
  btc_daily.csv     BTC-USD giornaliero  2015-01-01 → oggi
  btc_hourly.csv    BTC-USD orario       2023-01-01 → oggi
  eth_hourly.csv    ETH-USD orario       2023-01-01 → oggi
  sol_hourly.csv    SOL-USD orario       2023-01-01 → oggi
"""

import os
import sys
import warnings
import pandas as pd

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    print("Installa yfinance: pip install yfinance")
    sys.exit(1)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DAILY_START  = "2015-01-01"
HOURLY_START = "2023-01-01"

ASSETS = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
}


def fetch(ticker: str, interval: str, start: str) -> pd.DataFrame:
    print(f"  Downloading {ticker} ({interval}) from {start}...")
    df = yf.download(ticker, start=start, interval=interval,
                     auto_adjust=True, progress=True)
    if df.empty:
        raise ValueError(f"Nessun dato per {ticker} ({interval})")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "Date"
    df.dropna(inplace=True)
    return df


def main():
    print("=" * 60)
    print("  Download dati reali BTC/ETH/SOL")
    print("=" * 60)

    # BTC daily (10 anni)
    df = fetch("BTC-USD", "1d", DAILY_START)
    path = os.path.join(OUTPUT_DIR, "btc_daily.csv")
    df.to_csv(path)
    print(f"  Salvato: {path}  ({len(df)} righe, "
          f"${df['Close'].iloc[-1]:,.0f} ultimo close)\n")

    # Orari BTC / ETH / SOL
    for name, ticker in ASSETS.items():
        df = fetch(ticker, "1h", HOURLY_START)
        path = os.path.join(OUTPUT_DIR, f"{name}_hourly.csv")
        df.to_csv(path)
        print(f"  Salvato: {path}  ({len(df)} righe)\n")

    print("=" * 60)
    print("  FATTO — ora copia i file output/*.csv")
    print("  nella cartella btc_analysis/output/ del progetto")
    print("  e riesegui: python3 run_all.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
