"""
03_features.py
==============
Step 3 della pipeline: costruzione esplicita delle feature necessarie
alla strategia progettata dall'agent (Step 2).

Carica i dati orari grezzi, applica compute_indicators_v2() (incluso
GARCH(1,1)), e salva il dataframe arricchito in:
  output/{asset}_features.parquet   (preferito, più veloce da caricare)
  output/{asset}_features.csv       (fallback se pyarrow non disponibile)

I passi successivi (04_backtest.py, 05_montecarlo.py) caricano queste
feature pre-calcolate invece di ricalcolare GARCH ogni volta.

Input:  STRATEGY_ASSET env var (default: BTC-USD)
        output/{asset}_hourly.csv

Output: output/{asset}_features.parquet  (o .csv)
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
from strategy_core import (
    load_hourly, compute_indicators_v2,
    ticker_to_fname, OUTPUT_DIR,
)

STRATEGY_ASSET = os.environ.get("STRATEGY_ASSET", "BTC-USD")


def build_features(asset: str) -> pd.DataFrame:
    fname = ticker_to_fname(asset)

    print(f"  Caricamento dati orari {asset}...")
    df_raw = load_hourly(asset)
    n_bars = len(df_raw)
    date_range = f"{df_raw.index[0].date()} → {df_raw.index[-1].date()}"
    print(f"  Barre: {n_bars:,}  |  Periodo: {date_range}")

    print("  Calcolo indicatori tecnici + GARCH(1,1)  (può richiedere ~30s)...")
    t0 = time.time()
    df_feat = compute_indicators_v2(df_raw, fit_garch=True)
    elapsed = time.time() - t0
    print(f"  Indicatori calcolati in {elapsed:.1f}s  |  "
          f"Colonne: {list(df_feat.columns)}")

    # ── Regime summary ──────────────────────────────────────────────────────
    if "garch_regime" in df_feat.columns:
        vc = df_feat["garch_regime"].value_counts()
        total = len(df_feat)
        parts = [f"{r}: {c/total*100:.0f}%" for r, c in vc.items()]
        print(f"  Regime GARCH → {' | '.join(parts)}")

    # ── Persist ─────────────────────────────────────────────────────────────
    try:
        out_path = os.path.join(OUTPUT_DIR, f"{fname}_features.parquet")
        df_feat.to_parquet(out_path)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"  Salvato: {os.path.basename(out_path)}  ({size_kb:.0f} KB)")
    except Exception as parquet_err:
        # pyarrow not available — fall back to CSV
        out_path = os.path.join(OUTPUT_DIR, f"{fname}_features.csv")
        df_feat.to_csv(out_path)
        size_kb = os.path.getsize(out_path) / 1024
        print(f"  [pyarrow non disponibile] Salvato CSV: "
              f"{os.path.basename(out_path)}  ({size_kb:.0f} KB)")

    return df_feat


if __name__ == "__main__":
    print("=" * 60)
    print(f"  FEATURE CONSTRUCTION — {STRATEGY_ASSET}")
    print("=" * 60)

    build_features(STRATEGY_ASSET)

    print("\nFeature construction completata.")
