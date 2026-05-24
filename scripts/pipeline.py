#!/usr/bin/env python3
"""
scripts/pipeline.py
===================
Autonomous end-to-end pipeline:
  1. Seed DuckDB from local CSV archives (no external API required)
  2. Run vibe_loop for each ticker × timeframes
  3. Promote ROBUST/best strategies to library (starred=True)
  4. Print final leaderboard of all starred strategies

Usage:
    cd /home/user/crypto1
    python scripts/pipeline.py [--tickers BTC-USD,ETH-USD,SOL-USD] \
                                [--timeframes 1h,4h,1d] \
                                [--max-iter 30] \
                                [--stop-sharpe 1.5] \
                                [--max-dd 20]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.db import get_conn

# ── Available archive tickers ──────────────────────────────────────────────────
_ARCHIVE_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD"]

_CSV_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "archive", "btc_analysis", "output")
_CSV_MAP  = {
    "BTC-USD": "btc_hourly.csv",
    "ETH-USD": "eth_hourly.csv",
    "SOL-USD": "sol_hourly.csv",
}


def seed_ticker(ticker: str) -> int:
    """Load CSV into DuckDB if not already present. Returns row count."""
    import pandas as pd
    conn = get_conn()
    existing = conn.execute(
        "SELECT COUNT(*) FROM assets WHERE ticker=? AND source='csv_archive'", [ticker]
    ).fetchone()[0]
    if existing > 0:
        print(f"  {ticker}: {existing:,} bars already in DB — skip seed")
        return existing

    fname = _CSV_MAP.get(ticker)
    if not fname:
        print(f"  {ticker}: no archive CSV — skip")
        return 0
    fpath = os.path.join(_CSV_DIR, fname)
    if not os.path.exists(fpath):
        print(f"  {ticker}: CSV not found at {fpath} — skip")
        return 0

    df = pd.read_csv(fpath, parse_dates=["Date"])
    df = df.rename(columns={"Date": "ts", "Open": "open", "High": "high",
                             "Low": "low", "Close": "close", "Volume": "volume"})

    from engine.storage.bulk_writer import bulk_store
    n = bulk_store(conn, ticker, "csv_archive", df)
    print(f"  {ticker}: seeded {n:,} bars from {fname}")
    return n


def run_ticker(ticker: str, timeframes: list, max_iter: int,
               stop_sharpe: float, max_dd: float) -> dict:
    """Run vibe_loop for one ticker and return result dict."""
    # Patch sys.argv so vibe_loop.main() uses our params
    orig_argv = sys.argv[:]
    sys.argv = [
        "vibe_loop.py",
        "--ticker",      ticker,
        "--timeframes",  ",".join(timeframes),
        "--max-iter",    str(max_iter),
        "--stop-sharpe", str(stop_sharpe),
        "--max-dd",      str(max_dd),
    ]
    try:
        import scripts.vibe_loop as vl
        # Reload to reset any module-level state between tickers
        import importlib
        importlib.reload(vl)
        result = vl.main() or {}
    except SystemExit:
        result = {}
    except Exception as e:
        print(f"  [pipeline] {ticker} loop error: {e}")
        result = {}
    finally:
        sys.argv = orig_argv

    result["ticker"] = ticker
    return result


def library_summary() -> list:
    """Return all starred strategies from DuckDB."""
    import json
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, strategy_type, config, status, created_at "
        "FROM strategies WHERE starred=TRUE ORDER BY created_at DESC"
    ).fetchall()
    out = []
    for r in rows:
        cfg = {}
        try:
            cfg = json.loads(r[3]) if r[3] else {}
        except Exception:
            pass
        out.append({
            "id": r[0], "name": r[1], "type": r[2],
            "ticker": cfg.get("ticker", "?"),
            "timeframe": cfg.get("timeframe", "?"),
            "status": r[4],
            "created_at": str(r[5]),
        })
    return out


def print_leaderboard(results: list) -> None:
    print(f"\n{'='*70}")
    print("  PIPELINE COMPLETE — LEADERBOARD")
    print(f"{'='*70}")
    print(f"  {'Ticker':<10} {'TF':<5} {'Sharpe':>7} {'DD%':>6} {'Verdict':<10} {'SID'}")
    print("  " + "─" * 65)
    for r in results:
        sid = r.get("sid") or "—"
        print(
            f"  {r['ticker']:<10} {str(r.get('tf','?')):<5} "
            f"{r.get('sharpe', 0):>+7.3f} {r.get('dd', 0) or 0:>6.1f} "
            f"{r.get('verdict','?'):<10} {sid}"
        )

    print(f"\n  {'='*68}")
    print("  STARRED STRATEGIES IN LIBRARY")
    print(f"  {'='*68}")
    lib = library_summary()
    if not lib:
        print("  (none)")
    else:
        for s in lib:
            print(f"  [{s['status']:>8}] {s['id']}  {s['ticker']}/{s['timeframe']}  {s['name']}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description="Autonomous pipeline: seed → optimize → library")
    p.add_argument("--tickers",     default=",".join(_ARCHIVE_TICKERS))
    p.add_argument("--timeframes",  default="1h,4h,1d")
    p.add_argument("--max-iter",    type=int,   default=30)
    p.add_argument("--stop-sharpe", type=float, default=1.5)
    p.add_argument("--max-dd",      type=float, default=20.0)
    args = p.parse_args()

    tickers   = [t.strip() for t in args.tickers.split(",") if t.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    print(f"\n{'='*70}")
    print(f"  AUTONOMOUS PIPELINE")
    print(f"  Tickers    : {tickers}")
    print(f"  Timeframes : {timeframes}")
    print(f"  Max iters  : {args.max_iter}  per ticker")
    print(f"  Target     : Sharpe ≥ {args.stop_sharpe}  MaxDD ≤ {args.max_dd}%")
    print(f"{'='*70}\n")

    # ── Step 1: Seed ────────────────────────────────────────────────────────────
    print("[STEP 1] Seeding DuckDB from archive CSVs...")
    valid_tickers = []
    for ticker in tickers:
        n = seed_ticker(ticker)
        if n > 0:
            valid_tickers.append(ticker)

    if not valid_tickers:
        print("ERROR: no data available for any ticker. Aborting.")
        sys.exit(1)

    print(f"\n  Ready: {valid_tickers}\n")

    # ── Step 2: Optimize ────────────────────────────────────────────────────────
    print("[STEP 2] Running optimization loop per ticker...")
    results = []
    for i, ticker in enumerate(valid_tickers, 1):
        print(f"\n[{i}/{len(valid_tickers)}] {ticker}")
        t0 = time.time()
        result = run_ticker(ticker, timeframes, args.max_iter, args.stop_sharpe, args.max_dd)
        elapsed = time.time() - t0
        print(f"  [{ticker}] done in {elapsed:.1f}s  verdict={result.get('verdict','?')}")
        results.append(result)

    # ── Step 3: Report ──────────────────────────────────────────────────────────
    print_leaderboard(results)


if __name__ == "__main__":
    main()
