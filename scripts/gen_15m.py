#!/usr/bin/env python3
"""Generate synthetic 15min BTC bars from hourly archive and seed DuckDB."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

CSV_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', 'archive', 'btc_analysis', 'output', 'btc_hourly.csv')

def generate_15m(df_1h: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng     = np.random.default_rng(seed)
    records = []
    for ts, row in df_1h.iterrows():
        o, h, l, c, v = float(row.Open), float(row.High), float(row.Low), float(row.Close), float(row.Volume)
        span   = h - l
        t      = np.array([1, 2, 3, 4]) / 4.0
        closes = o + (c - o) * t + rng.normal(0, span * 0.03, 4)
        closes = np.clip(closes, l, h)
        closes[-1] = c
        opens  = np.concatenate([[o], closes[:-1]])
        for i in range(4):
            so, sc = float(opens[i]), float(closes[i])
            sh = float(min(max(so, sc) + rng.uniform(0, (h - max(so, sc)) * 0.6), h))
            sl = float(max(min(so, sc) - rng.uniform(0, (min(so, sc) - l) * 0.6), l))
            records.append({
                'Date':   ts + pd.Timedelta(minutes=15 * i),
                'Open':   round(so, 4),  'High':   round(sh, 4),
                'Low':    round(sl, 4),  'Close':  round(sc, 4),
                'Volume': round(v / 4, 2),
            })
    return pd.DataFrame(records)

def main():
    from api.db import get_conn
    df_1h = pd.read_csv(CSV_PATH, parse_dates=['Date'])
    df_1h = df_1h.set_index('Date').sort_index()
    print(f"Input : {len(df_1h):,} hourly bars  "
          f"({df_1h.index[0].date()} → {df_1h.index[-1].date()})")

    df15 = generate_15m(df_1h)
    print(f"Output: {len(df15):,} 15-min bars")

    conn = get_conn()
    rows = [
        ('BTC-USD', 'synthetic_15m',
         r.Date, r.Open, r.High, r.Low, r.Close, r.Volume)
        for r in df15.itertuples(index=False)
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO assets "
        "(ticker,source,ts,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    n = conn.execute(
        "SELECT COUNT(*) FROM assets WHERE ticker='BTC-USD'"
    ).fetchone()[0]
    print(f"DuckDB : {n:,} BTC-USD rows  ({os.environ.get('DUCKDB_PATH','?')})")

if __name__ == '__main__':
    main()
