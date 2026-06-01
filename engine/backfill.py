"""Unified M1 backfill orchestrator.

Routes backfill requests to the right provider based on asset class:
  - crypto  → engine.providers.binance_vision
  - forex   → engine.providers.dukascopy_client
  - stock   → engine.providers.alpaca_client

Usage (CLI):
  python -m engine.backfill BTC-USD --start-year 2020
  python -m engine.backfill EURUSD  --start-year 2018
  python -m engine.backfill AAPL    --start-year 2015
"""
import logging
from typing import Literal

from engine.providers.ccxt_client import is_crypto_ticker
from engine.providers.dukascopy_client import is_forex_ticker

log = logging.getLogger(__name__)

AssetClass = Literal["crypto", "forex", "stock"]


def classify_ticker(ticker: str) -> AssetClass:
    if is_crypto_ticker(ticker):
        return "crypto"
    if is_forex_ticker(ticker):
        return "forex"
    return "stock"


def backfill_ticker(
    ticker: str,
    start_year: int = 2018,
    start_month: int = 1,
    end_year: int | None = None,
    end_month: int | None = None,
) -> dict:
    """Download missing M1 history for one ticker. Returns a summary dict."""
    asset_class = classify_ticker(ticker)
    log.info("backfill %s  asset_class=%s  from=%d-%02d", ticker, asset_class, start_year, start_month)

    kwargs = dict(
        ticker=ticker,
        start_year=start_year,
        start_month=start_month,
        end_year=end_year,
        end_month=end_month,
    )

    if asset_class == "crypto":
        from engine.providers.binance_vision import backfill
    elif asset_class == "forex":
        from engine.providers.dukascopy_client import backfill
    else:
        from engine.providers.alpaca_client import backfill

    try:
        rows = backfill(**kwargs)
        return {"ticker": ticker, "asset_class": asset_class, "rows": rows, "ok": True}
    except Exception as exc:
        log.error("backfill failed %s: %s", ticker, exc)
        return {"ticker": ticker, "asset_class": asset_class, "rows": 0, "ok": False, "error": str(exc)}


def backfill_many(
    tickers: list[str],
    start_year: int = 2018,
    start_month: int = 1,
    end_year: int | None = None,
    end_month: int | None = None,
) -> list[dict]:
    return [
        backfill_ticker(t, start_year, start_month, end_year, end_month)
        for t in tickers
    ]


if __name__ == "__main__":
    import argparse, sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Backfill M1 history")
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--start-year", type=int, default=2018)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--end-month", type=int, default=None)
    args = parser.parse_args()

    results = backfill_many(
        args.tickers,
        start_year=args.start_year,
        start_month=args.start_month,
        end_year=args.end_year,
        end_month=args.end_month,
    )
    for r in results:
        status = "OK" if r["ok"] else f"FAIL: {r.get('error','')}"
        print(f"{r['ticker']} ({r['asset_class']})  rows={r['rows']}  {status}")
    sys.exit(0 if all(r["ok"] for r in results) else 1)
