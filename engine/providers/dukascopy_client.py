"""Download M1 OHLCV for forex pairs from Dukascopy (public tick feed).

URL: https://datafeed.dukascopy.com/datafeed/{symbol}/{year}/{month_0idx:02d}/{day:02d}/{hour:02d}h_ticks.bi5
Month index is 0-based: January=00 … December=11.

.bi5 format: LZMA-compressed binary records of 20 bytes each.
  struct ">3i2f": time_ms_in_hour, ask_pips, bid_pips, ask_vol, bid_vol
"""
import gc
import logging
import lzma
import struct
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from engine.storage.parquet_store import already_downloaded, write_month

log = logging.getLogger(__name__)

_BASE = "https://datafeed.dukascopy.com/datafeed"
_RECORD_FMT = ">3i2f"
_RECORD_SIZE = struct.calcsize(_RECORD_FMT)  # 20 bytes

_POINT_VALUES: dict[str, int] = {
    "EURUSD": 100000, "GBPUSD": 100000, "AUDUSD": 100000, "NZDUSD": 100000,
    "USDCHF": 100000, "USDCAD": 100000, "EURGBP": 100000, "EURCHF": 100000,
    "EURAUD": 100000, "GBPAUD": 100000, "AUDCAD": 100000, "AUDCHF": 100000,
    "USDJPY": 1000,   "EURJPY": 1000,   "GBPJPY": 1000,   "AUDJPY": 1000,
    "CADJPY": 1000,   "CHFJPY": 1000,   "NZDJPY": 1000,
}
_DEFAULT_POINT = 100000


def _normalise(ticker: str) -> str:
    """Convert any ticker form to a plain 6-char Dukascopy symbol."""
    return (ticker.upper()
            .replace("-", "").replace("/", "")
            .replace("=X", "").replace("USD$", "USD"))


def is_forex_ticker(ticker: str) -> bool:
    norm = _normalise(ticker)
    return norm in _POINT_VALUES or (len(norm) == 6 and norm.isalpha())


def _fetch_hour(symbol: str, year: int, month_0idx: int, day: int, hour: int,
                session: requests.Session) -> bytes | None:
    url = (f"{_BASE}/{symbol}/{year}/{month_0idx:02d}"
           f"/{day:02d}/{hour:02d}h_ticks.bi5")
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content
    except Exception as exc:
        log.debug("dukascopy %s %d-%02d-%02d %02dh: %s",
                  symbol, year, month_0idx + 1, day, hour, exc)
        return None


def _parse_bi5(raw: bytes, base_ts: datetime, point_value: int) -> pd.DataFrame:
    """Decompress .bi5 ticks → 1-minute OHLCV DataFrame."""
    try:
        data = lzma.decompress(raw)
    except lzma.LZMAError:
        return pd.DataFrame()

    n = len(data) // _RECORD_SIZE
    if n == 0:
        return pd.DataFrame()

    timestamps = []
    prices = []
    volumes = []
    for i in range(n):
        ms, ask_p, bid_p, ask_v, bid_v = struct.unpack_from(_RECORD_FMT, data, i * _RECORD_SIZE)
        mid = (ask_p + bid_p) / 2.0 / point_value
        timestamps.append(base_ts + timedelta(milliseconds=ms))
        prices.append(mid)
        volumes.append(ask_v + bid_v)

    idx = pd.DatetimeIndex(timestamps)
    price_ser = pd.Series(prices, index=idx)
    vol_ser = pd.Series(volumes, index=idx)

    ohlcv = price_ser.resample("1min").ohlc()
    ohlcv.columns = ["Open", "High", "Low", "Close"]
    ohlcv["Volume"] = vol_ser.resample("1min").sum()
    return ohlcv.dropna(subset=["Open"])


def _days_in_month(year: int, month: int) -> int:
    first_next = datetime(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
    return (first_next - timedelta(days=1)).day


def backfill(ticker: str,
             start_year: int = 2010, start_month: int = 1,
             end_year: int | None = None, end_month: int | None = None) -> int:
    """Download missing monthly M1 files from Dukascopy. Returns total rows stored."""
    now = datetime.utcnow()
    if end_year is None:
        end_year = now.year
    if end_month is None:
        end_month = now.month - 1
        if end_month == 0:
            end_month = 12
            end_year -= 1

    symbol = _normalise(ticker)
    point_value = _POINT_VALUES.get(symbol, _DEFAULT_POINT)
    total = 0

    session = requests.Session()
    session.headers["User-Agent"] = "pareto-backfill/1.0"
    try:
        cur_y, cur_m = start_year, start_month
        while (cur_y, cur_m) <= (end_year, end_month):
            if already_downloaded("forex", ticker, cur_y, cur_m):
                log.debug("skip %s %d-%02d", symbol, cur_y, cur_m)
                cur_m += 1
                if cur_m > 12:
                    cur_m, cur_y = 1, cur_y + 1
                continue

            month_frames: list[pd.DataFrame] = []
            month_0idx = cur_m - 1

            for day in range(1, _days_in_month(cur_y, cur_m) + 1):
                for hour in range(24):
                    raw = _fetch_hour(symbol, cur_y, month_0idx, day, hour, session)
                    if raw:
                        try:
                            base_ts = datetime(cur_y, cur_m, day, hour)
                            df_h = _parse_bi5(raw, base_ts, point_value)
                            if not df_h.empty:
                                month_frames.append(df_h)
                        except Exception as exc:
                            log.debug("parse %s %d-%02d-%02d %02dh: %s",
                                      symbol, cur_y, cur_m, day, hour, exc)
                    time.sleep(0.05)

            if month_frames:
                df_month = pd.concat(month_frames).sort_index()
                df_month = df_month[~df_month.index.duplicated(keep="last")]
                write_month("forex", ticker, cur_y, cur_m, df_month)
                total += len(df_month)
                log.info("stored %s %d-%02d rows=%d", symbol, cur_y, cur_m, len(df_month))
                del df_month, month_frames
                gc.collect()

            cur_m += 1
            if cur_m > 12:
                cur_m, cur_y = 1, cur_y + 1
    finally:
        session.close()

    return total
