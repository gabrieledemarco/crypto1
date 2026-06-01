"""Download M1 OHLCV for crypto from Binance Vision (public dataset).

URL pattern:
  https://data.binance.vision/data/spot/monthly/klines/{symbol}/{tf}/{symbol}-{tf}-{YYYY}-{MM}.zip

Each ZIP contains one CSV:  open_time, open, high, low, close, volume, ...
open_time is Unix ms.
"""
import gc
import io
import logging
import time
import zipfile

import pandas as pd
import requests

from engine.storage.parquet_store import already_downloaded, write_month

log = logging.getLogger(__name__)

_BASE = "https://data.binance.vision/data/spot/monthly/klines"

_SYMBOL_MAP = {
    "BTC-USD": "BTCUSDT",
    "ETH-USD": "ETHUSDT",
    "SOL-USD": "SOLUSDT",
    "BNB-USD": "BNBUSDT",
    "XRP-USD": "XRPUSDT",
    "ADA-USD": "ADAUSDT",
    "DOGE-USD": "DOGEUSDT",
    "AVAX-USD": "AVAXUSDT",
    "LINK-USD": "LINKUSDT",
    "DOT-USD": "DOTUSDT",
}

_CSV_COLS = [
    "open_time", "Open", "High", "Low", "Close", "Volume",
    "close_time", "quote_vol", "n_trades", "tb_base", "tb_quote", "_ignore",
]


def _to_binance_symbol(ticker: str) -> str:
    if ticker in _SYMBOL_MAP:
        return _SYMBOL_MAP[ticker]
    if ticker.endswith("-USD"):
        return ticker[:-4] + "USDT"
    return ticker.upper().replace("-", "").replace("/", "")


def _fetch_zip(symbol: str, tf: str, year: int, month: int,
               session: requests.Session) -> bytes | None:
    url = f"{_BASE}/{symbol}/{tf}/{symbol}-{tf}-{year}-{month:02d}.zip"
    try:
        r = session.get(url, timeout=120)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    except Exception as exc:
        log.warning("binance_vision download failed %s %d-%02d: %s", symbol, year, month, exc)
        return None


def _parse_zip(raw: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        csv_bytes = z.read(z.namelist()[0])
    df = pd.read_csv(
        io.BytesIO(csv_bytes), header=None, names=_CSV_COLS,
        dtype={"Open": float, "High": float, "Low": float, "Close": float, "Volume": float},
    )
    # Auto-detect timestamp unit by magnitude.
    # Binance Vision files are supposed to be ms, but some have µs (1000× too large).
    # Reasonable ms range for 2017-2030: 1.4e12 – 1.9e12
    # Reasonable µs range for 2017-2030: 1.4e15 – 1.9e15
    ts_sample = df["open_time"].iloc[0] if not df.empty else 0
    if ts_sample >= 1e15:
        unit = "us"
    elif ts_sample >= 1e12:
        unit = "ms"
    else:
        unit = "s"
    df.index = pd.to_datetime(df["open_time"], unit=unit, utc=False).dt.tz_localize(None)
    df.index.name = None
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def backfill(ticker: str,
             start_year: int = 2019, start_month: int = 1,
             end_year: int | None = None, end_month: int | None = None,
             tf: str = "1m",
             on_progress=None) -> int:
    """Download missing monthly files from Binance Vision. Returns total rows stored.

    on_progress(year, month, month_idx, total_months, rows_this_month, rows_total)
    is called after each month completes (downloaded or skipped).
    """
    import datetime
    now = datetime.datetime.utcnow()
    if end_year is None:
        end_year = now.year
    if end_month is None:
        end_month = now.month - 1
        if end_month == 0:
            end_month = 12
            end_year -= 1

    symbol = _to_binance_symbol(ticker)
    total = 0

    # Pre-compute total months for progress reporting
    total_months = (end_year - start_year) * 12 + (end_month - start_month + 1)
    month_idx = 0

    session = requests.Session()
    session.headers["User-Agent"] = "pareto-backfill/1.0"
    try:
        cur_y, cur_m = start_year, start_month
        while (cur_y, cur_m) <= (end_year, end_month):
            month_idx += 1
            month_rows = 0

            if already_downloaded("crypto", ticker, cur_y, cur_m):
                log.debug("skip %s %d-%02d", symbol, cur_y, cur_m)
            else:
                raw = _fetch_zip(symbol, tf, cur_y, cur_m, session)
                if raw is not None:
                    df = _parse_zip(raw)
                    del raw
                    if not df.empty:
                        write_month("crypto", ticker, cur_y, cur_m, df)
                        month_rows = len(df)
                        total += month_rows
                        log.info("stored %s %d-%02d rows=%d", symbol, cur_y, cur_m, month_rows)
                    del df
                    gc.collect()
                time.sleep(0.2)

            if on_progress:
                try:
                    on_progress(cur_y, cur_m, month_idx, total_months, month_rows, total)
                except Exception:
                    pass

            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1
    finally:
        session.close()

    return total
