"""
engine/trade_analysis.py
========================
Pure computation functions for trade analysis.
No file IO, no Streamlit, no matplotlib.
"""

import numpy as np
import pandas as pd


# ── Direction stats ───────────────────────────────────────────────────────────

def direction_stats(df: pd.DataFrame) -> pd.DataFrame:
    """LONG vs SHORT performance breakdown."""
    if df.empty:
        return pd.DataFrame()
    rows = []
    for direction in ["LONG", "SHORT", "ALL"]:
        sub = df if direction == "ALL" else df[df["direction"] == direction]
        if sub.empty:
            continue
        wins = sub[sub["win"]]
        losses = sub[~sub["win"]]
        gross_profit = wins["pnl"].sum() if not wins.empty else 0.0
        gross_loss   = abs(losses["pnl"].sum()) if not losses.empty else 1e-9
        try:
            dur_mean = round(sub["duration_h"].mean(), 1)
        except (KeyError, TypeError):
            try:
                dur_mean = round(
                    (pd.to_datetime(sub["exit_time"]) - pd.to_datetime(sub["entry_time"]))
                    .dt.total_seconds().mean() / 3600, 1
                )
            except Exception:
                dur_mean = None
        rows.append({
            "Direzione":       direction,
            "N trade":         len(sub),
            "Win rate %":      round(sub["win"].mean() * 100, 1),
            "Avg win %":       round(wins["pnl_pct"].mean() * 100, 3) if not wins.empty else 0.0,
            "Avg loss %":      round(losses["pnl_pct"].mean() * 100, 3) if not losses.empty else 0.0,
            "Profit Factor":   round(gross_profit / gross_loss, 3),
            "P&L totale":      round(sub["pnl"].sum(), 2),
            "SL hit %":        round((sub["exit_reason"] == "SL").mean() * 100, 1),
            "TP hit %":        round((sub["exit_reason"] == "TP").mean() * 100, 1),
            "Durata media h":  dur_mean,
        })
    return pd.DataFrame(rows)


# ── Per-fold IS/OOS trade breakdown ──────────────────────────────────────────

def fold_direction_stats(trades_df: pd.DataFrame, wfo_df: pd.DataFrame) -> pd.DataFrame:
    """For each WFO fold: LONG vs SHORT stats in the OOS period."""
    if trades_df.empty or wfo_df.empty:
        return pd.DataFrame()

    # Normalize entry_time to timezone-naive to avoid comparison errors
    try:
        entry_ts = pd.to_datetime(trades_df["entry_time"], utc=True, errors="coerce")
        # Remove timezone info so comparison with naive WFO timestamps works
        if entry_ts.dt.tz is not None:
            entry_ts = entry_ts.dt.tz_convert(None)
    except Exception:
        entry_ts = pd.to_datetime(trades_df["entry_time"], errors="coerce")

    rows = []
    for _, fold in wfo_df.iterrows():
        try:
            raw_start = fold.get("test_start") or fold.get("train_end")
            raw_end   = fold.get("test_end")
            if pd.isna(raw_start) or pd.isna(raw_end):
                continue
            t_start = pd.to_datetime(raw_start, utc=False)
            t_end   = pd.to_datetime(raw_end,   utc=False)
            if pd.isna(t_start) or pd.isna(t_end):
                continue
        except Exception:
            continue

        # Use <= t_end so trades entered on the last bar of the window are included
        mask = (entry_ts >= t_start) & (entry_ts <= t_end)
        oos  = trades_df[mask]

        fold_num   = fold.get("fold", "?")
        period     = fold.get("period", "?")
        oos_sharpe = fold.get("oos_sharpe", None)

        for direction in ["LONG", "SHORT", "ALL"]:
            sub = oos if direction == "ALL" else oos[oos["direction"] == direction]
            n = len(sub)
            # Skip direction rows with no trades so the table stays readable
            if n == 0:
                continue
            wins   = sub[sub["win"]]
            losses = sub[~sub["win"]]
            gp = wins["pnl"].sum()        if not wins.empty   else 0.0
            gl = abs(losses["pnl"].sum()) if not losses.empty else 1e-9
            rows.append({
                "Fold":        fold_num,
                "Periodo OOS": period,
                "OOS Sharpe":  round(float(oos_sharpe), 3) if oos_sharpe is not None else None,
                "Direzione":   direction,
                "N trade":     n,
                "Win rate %":  round(sub["win"].mean() * 100, 1),
                "PF":          round(gp / gl, 3),
                "P&L totale":  round(sub["pnl"].sum(), 2),
                "SL hit %":    round((sub["exit_reason"] == "SL").mean() * 100, 1),
            })
    return pd.DataFrame(rows)


# ── Hour breakdown ────────────────────────────────────────────────────────────

def hourly_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Performance by UTC entry hour × direction."""
    if df.empty or "entry_hour" not in df.columns:
        return pd.DataFrame()
    rows = []
    for hour in range(24):
        sub_h = df[df["entry_hour"] == hour]
        if sub_h.empty:
            continue
        for direction in ["LONG", "SHORT"]:
            sub = sub_h[sub_h["direction"] == direction]
            if sub.empty:
                continue
            wins = sub[sub["win"]]
            rows.append({
                "Ora UTC": hour,
                "Direzione": direction,
                "N": len(sub),
                "Win%": round(sub["win"].mean() * 100, 1),
                "P&L medio": round(sub["pnl"].mean(), 2),
            })
    return pd.DataFrame(rows)


# ── Regime breakdown ──────────────────────────────────────────────────────────

def regime_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Performance by GARCH regime."""
    if df.empty or "garch_regime" not in df.columns:
        return pd.DataFrame()
    rows = []
    for regime in ["LOW", "MED", "HIGH"]:
        sub = df[df["garch_regime"] == regime]
        if sub.empty:
            continue
        wins   = sub[sub["win"]]
        losses = sub[~sub["win"]]
        gp = wins["pnl"].sum()   if not wins.empty   else 0.0
        gl = abs(losses["pnl"].sum()) if not losses.empty else 1e-9
        rows.append({
            "Regime GARCH": regime,
            "N trade":      len(sub),
            "Win rate %":   round(sub["win"].mean() * 100, 1),
            "PF":           round(gp / gl, 3),
            "P&L totale":   round(sub["pnl"].sum(), 2),
        })
    return pd.DataFrame(rows)


# ── Streak analysis ───────────────────────────────────────────────────────────

def streak_stats(df: pd.DataFrame) -> dict:
    """Compute winning/losing streaks."""
    if df.empty:
        return {}
    wins = df["win"].astype(int).values
    max_win_streak = max_loss_streak = cur = 0
    prev = -1
    for w in wins:
        if w == prev:
            cur += 1
        else:
            cur = 1
        if w == 1:
            max_win_streak  = max(max_win_streak, cur)
        else:
            max_loss_streak = max(max_loss_streak, cur)
        prev = w
    return {
        "max_win_streak":  max_win_streak,
        "max_loss_streak": max_loss_streak,
        "n_win_streaks":   int((df["win"] & ~df["win"].shift(1).fillna(False)).sum()),
        "n_loss_streaks":  int((~df["win"] & df["win"].shift(1).fillna(True)).sum()),
    }


# ── Weakness identification ───────────────────────────────────────────────────

def identify_weaknesses(
    trades_df: pd.DataFrame,
    wfo_df: pd.DataFrame,
) -> list:
    """Return a list of human-readable weakness strings for the improvement prompt."""
    issues = []

    if trades_df.empty:
        return ["No trade data available."]

    dir_df = direction_stats(trades_df)
    if not dir_df.empty:
        for _, row in dir_df.iterrows():
            d = row["Direzione"]
            if d == "ALL":
                continue
            if row["Win rate %"] < 35:
                issues.append(
                    f"  - {d} trades: win rate={row['Win rate %']:.1f}% (<35%) — "
                    f"entry signal for {d} is too noisy."
                )
            if row["Profit Factor"] < 1.0 and row["N trade"] >= 5:
                issues.append(
                    f"  - {d} trades: Profit Factor={row['Profit Factor']:.2f} (<1.0) — "
                    f"{d} side is net-negative, consider disabling or reversing."
                )
            if row["SL hit %"] > 70:
                issues.append(
                    f"  - {d} trades: SL hit {row['SL hit %']:.0f}% — "
                    f"SL too tight; increase sl_mult or add confirmation filter."
                )

    if not wfo_df.empty:
        oos_neg = (wfo_df["oos_sharpe"] < 0).sum()
        total = len(wfo_df)
        if oos_neg > total * 0.5:
            issues.append(
                f"  - Walk-forward: {oos_neg}/{total} OOS folds have negative Sharpe — "
                "strategy does not generalise; simplify entry conditions."
            )
        if "oos_winrate" in wfo_df.columns:
            avg_oos_wr = wfo_df["oos_winrate"].mean()
            if avg_oos_wr < 35:
                issues.append(
                    f"  - OOS average win rate={avg_oos_wr:.1f}% (<35%) — "
                    "overfit: IS conditions don't hold OOS."
                )

    h_df = hourly_stats(trades_df)
    if not h_df.empty:
        worst = h_df[h_df["P&L medio"] < -50].sort_values("P&L medio")
        for _, row in worst.head(3).iterrows():
            issues.append(
                f"  - Hour {int(row['Ora UTC']):02d}:00 UTC, {row['Direzione']}: "
                f"avg P&L={row['P&L medio']:.0f} over {int(row['N'])} trades — remove from active window."
            )

    reg_df = regime_stats(trades_df)
    if not reg_df.empty:
        low_reg = reg_df[reg_df["Regime GARCH"] == "LOW"]
        if not low_reg.empty and low_reg.iloc[0]["PF"] < 0.8:
            issues.append(
                "  - GARCH LOW regime: PF<0.8 — ensure garch_regime filter is active "
                "or expand it to skip MED regime too."
            )

    if not issues:
        issues.append("  - No critical weaknesses detected — strategy appears robust.")
    return issues
