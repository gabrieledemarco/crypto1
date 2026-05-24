"""
/assets/download — bulk OHLCV downloader for multiple tickers × timeframes.

POST /assets/download
    body: {"tickers": ["BTC-USD","ETH-USD"], "timeframes": ["1m","15m","1h","4h","1d"]}
    returns: {"job_id": "...", "stream_url": "/assets/download/{job_id}/stream"}

GET  /assets/download/{job_id}/stream
    SSE: start | downloading | download_done | download_error | complete | error

Usage (curl):
    JOB=$(curl -s -X POST https://<api>/assets/download \
        -H 'Content-Type: application/json' \
        -d '{"tickers":["BTC-USD","ETH-USD","SOL-USD"],"timeframes":["15m","1h","4h","1d"]}' \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
    curl -N https://<api>/assets/download/$JOB/stream
"""
import asyncio
import concurrent.futures
import json
import os
import sys
import uuid
from typing import Optional

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.db import get_conn

router = APIRouter()
_queues: dict[str, asyncio.Queue] = {}

# ── Timeframe metadata ─────────────────────────────────────────────────────────
_TF_NORM = {
    "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}
_YF_PERIOD = {
    "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
    "1h": "730d", "4h": "730d", "1d": "max",
}
_YF_INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "1h",  # yfinance has no 4h; we resample from 1h
    "1d": "1d",
}
_RESAMPLE_4H = {"4h"}


# ── Request model ──────────────────────────────────────────────────────────────

class DownloadRequest(BaseModel):
    tickers: list[str] = ["BTC-USD", "ETH-USD", "SOL-USD"]
    timeframes: list[str] = ["1m", "15m", "1h", "4h", "1d"]
    period: Optional[str] = None   # override max-lookback for all TFs


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("")
async def start_download(body: DownloadRequest):
    job_id = uuid.uuid4().hex[:12]
    _queues[job_id] = asyncio.Queue()
    asyncio.create_task(_run_download(job_id, body))
    return {
        "job_id": job_id,
        "stream_url": f"/assets/download/{job_id}/stream",
        "tickers": body.tickers,
        "timeframes": body.timeframes,
    }


@router.get("/{job_id}/stream")
async def stream_download(job_id: str):
    queue = _queues.setdefault(job_id, asyncio.Queue())

    async def gen():
        try:
            while True:
                evt = await queue.get()
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") in ("complete", "error"):
                    break
        finally:
            _queues.pop(job_id, None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Async coordinator ──────────────────────────────────────────────────────────

async def _run_download(job_id: str, body: DownloadRequest):
    queue = _queues[job_id]

    def push(evt: dict):
        queue.put_nowait(evt)

    loop = asyncio.get_running_loop()
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, _sync_download, body, push)
    except Exception as exc:
        push({"type": "error", "msg": str(exc)})


# ── Sync worker ────────────────────────────────────────────────────────────────

def _sync_download(body: DownloadRequest, push):
    tickers = body.tickers
    # Normalize TF aliases
    tfs = [_TF_NORM.get(t.strip(), t.strip()) for t in body.timeframes]

    push({"type": "start", "tickers": tickers, "timeframes": tfs,
          "total": len(tickers) * len(tfs)})

    conn = get_conn()
    summary = []

    for ticker in tickers:
        for tf in tfs:
            period = body.period or _YF_PERIOD.get(tf, "max")
            push({"type": "downloading", "ticker": ticker, "tf": tf, "period": period})

            try:
                df = _fetch(ticker, tf, period)
                if df is None or df.empty:
                    raise ValueError("empty response")

                # Resample 1h→4h if needed
                if tf in _RESAMPLE_4H:
                    df = _resample_4h(df)

                count = _store(conn, ticker, tf, df)
                evt = {
                    "type": "download_done",
                    "ticker": ticker, "tf": tf,
                    "bars": len(df), "stored": count,
                    "period": period,
                    "start": str(df.index[0].date()),
                    "end":   str(df.index[-1].date()),
                }
                push(evt)
                summary.append({**evt, "ok": True})

            except Exception as exc:
                evt = {"type": "download_error", "ticker": ticker, "tf": tf, "msg": str(exc)}
                push(evt)
                summary.append({**evt, "ok": False})

    ok = [s for s in summary if s.get("ok")]
    fail = [s for s in summary if not s.get("ok")]
    push({
        "type": "complete",
        "total": len(summary),
        "ok": len(ok),
        "failed": len(fail),
        "summary": summary,
    })


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch(ticker: str, tf: str, period: str) -> pd.DataFrame:
    yf_interval = _YF_INTERVAL.get(tf, tf)

    try:
        from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
        if is_crypto_ticker(ticker):
            try:
                return ccxt_fetch(ticker, period=period, interval=tf)
            except Exception:
                pass
    except ImportError:
        pass

    from engine.providers.yfinance_client import fetch as yf_fetch
    return yf_fetch(ticker, period=period, interval=yf_interval)


def _resample_4h(df: pd.DataFrame) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample("4h").agg(agg).dropna()


def _store(conn, ticker: str, tf: str, df: pd.DataFrame) -> int:
    src = f"download:{tf}"
    count = 0
    for ts, row in df.iterrows():
        try:
            conn.execute(
                "INSERT OR IGNORE INTO assets "
                "(ticker,source,ts,open,high,low,close,volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                [ticker, src, ts,
                 float(row["Open"]), float(row["High"]),
                 float(row["Low"]),  float(row["Close"]),
                 float(row["Volume"])],
            )
            count += 1
        except Exception:
            pass
    return count
