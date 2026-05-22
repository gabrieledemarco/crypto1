"""
engine/parity_check.py
======================
Verify engine/ output matches btc_analysis/strategy_core.py on same input.
Run: python engine/parity_check.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "btc_analysis", "output", "btc_hourly.csv")

def main():
    if not os.path.exists(DATA_PATH):
        print(f"[parity] Data not found at {DATA_PATH}")
        print("[parity] SKIP — no local data available")
        return

    df_raw = pd.read_csv(DATA_PATH, index_col="Date", parse_dates=True)
    df_raw.columns = [c[0] if isinstance(c, tuple) else c for c in df_raw.columns]
    df_raw = df_raw[["Open","High","Low","Close","Volume"]].dropna()
    df_raw = df_raw.iloc[-2000:]  # last 2000 bars for speed

    print(f"[parity] Loaded {len(df_raw)} bars")

    # Engine pipeline
    from engine.strategy_core import (
        compute_indicators_v2 as eng_ind,
        generate_signals_v2 as eng_sig,
        backtest_v2 as eng_bt,
        compute_metrics as eng_m,
    )
    df_ind_e = eng_ind(df_raw.copy(), fit_garch=False)
    df_sig_e = eng_sig(df_ind_e, atr_mult_sl=2.0, atr_mult_tp=5.0,
                       active_hours=(6, 22), use_garch_filter=False)
    res_e = eng_bt(df_sig_e)
    m_e   = eng_m(res_e, 10_000)

    # Legacy pipeline
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "btc_analysis"))
    from strategy_core import (
        compute_indicators_v2 as leg_ind,
        generate_signals_v2 as leg_sig,
        backtest_v2 as leg_bt,
        compute_metrics as leg_m,
    )
    df_ind_l = leg_ind(df_raw.copy(), fit_garch=False)
    df_sig_l = leg_sig(df_ind_l, atr_mult_sl=2.0, atr_mult_tp=5.0,
                       active_hours=(6, 22), use_garch_filter=False)
    res_l = leg_bt(df_sig_l)
    m_l   = leg_m(res_l, 10_000)

    print(f"\n{'Metric':<22} {'Engine':>10} {'Legacy':>10} {'Match':>8}")
    print("-" * 52)
    keys = ["sharpe_ratio", "cagr_pct", "max_drawdown_pct", "n_trades", "win_rate_pct", "profit_factor"]
    all_ok = True
    for k in keys:
        ev = m_e.get(k, 0) or 0
        lv = m_l.get(k, 0) or 0
        diff = abs(ev - lv)
        ok = diff < 0.01
        if not ok:
            all_ok = False
        print(f"  {k:<20} {ev:>10.4f} {lv:>10.4f} {'OK' if ok else 'MISMATCH':>8}")

    print()
    if all_ok:
        print("[parity] All metrics match — engine is equivalent to legacy")
    else:
        print("[parity] Mismatch detected — review differences above")
        sys.exit(1)

if __name__ == "__main__":
    main()
