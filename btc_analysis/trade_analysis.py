"""
trade_analysis.py
=================
Analisi trade-by-trade: LONG vs SHORT per fold IS/OOS, per ora UTC,
per regime GARCH, streak, SL/TP hit rate.

Usato dall'app Streamlit (tab Analisi Trade) e dal prompt di
miglioramento strategia.
"""

import os
import re
import json
import numpy as np
import pandas as pd

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_trades(asset: str = "BTC-USD") -> pd.DataFrame:
    alias = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}
    fname = alias.get(asset) or re.sub(r"[^a-z0-9]", "_", asset.lower()).strip("_")
    path = os.path.join(OUTPUT_DIR, "trades.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    if df.empty:
        return df
    df["entry_hour"] = pd.to_datetime(df["entry_time"]).dt.hour
    df["entry_month"] = pd.to_datetime(df["entry_time"]).dt.to_period("M").astype(str)
    df["win"] = df["pnl"] > 0
    df["rr"] = df["pnl_pct"].abs()  # proxy for R:R magnitude
    if "duration_h" not in df.columns:
        df["duration_h"] = (
            pd.to_datetime(df["exit_time"]) - pd.to_datetime(df["entry_time"])
        ).dt.total_seconds() / 3600
    # Enrich with GARCH regime from hourly data
    _enrich_regime(df, fname)
    return df


def _enrich_regime(df: pd.DataFrame, fname: str) -> None:
    """Add garch_regime column to trades_df by joining on entry_time."""
    try:
        hourly_path = os.path.join(OUTPUT_DIR, f"{fname}_hourly.csv")
        if not os.path.exists(hourly_path):
            return
        h = pd.read_csv(hourly_path, index_col=0, parse_dates=True)
        h.columns = [c if isinstance(c, str) else c[0] for c in h.columns]
        ret = h["Close"].pct_change()
        roll_vol = ret.rolling(24).std()
        q33 = roll_vol.quantile(0.33)
        q66 = roll_vol.quantile(0.66)
        regime = pd.cut(roll_vol, bins=[-np.inf, q33, q66, np.inf],
                        labels=["LOW", "MED", "HIGH"])
        regime_map = regime.to_dict()
        df["garch_regime"] = pd.to_datetime(df["entry_time"]).map(
            lambda t: regime_map.get(t, None)
        )
    except Exception:
        pass


def load_wfo(config: str = "IS8m_OOS2m") -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, f"wfo_{config}.csv")
    if not os.path.exists(path):
        path = os.path.join(OUTPUT_DIR, "walk_forward_results.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)


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
    rows = []
    for _, fold in wfo_df.iterrows():
        try:
            t_start = pd.to_datetime(fold.get("test_start", fold.get("train_end")))
            t_end   = pd.to_datetime(fold.get("test_end"))
        except Exception:
            continue
        oos = trades_df[
            (pd.to_datetime(trades_df["entry_time"]) >= t_start) &
            (pd.to_datetime(trades_df["entry_time"]) < t_end)
        ]
        fold_num = fold.get("fold", "?")
        period   = fold.get("period", "?")
        oos_sharpe = fold.get("oos_sharpe", None)
        for direction in ["LONG", "SHORT", "ALL"]:
            sub = oos if direction == "ALL" else oos[oos["direction"] == direction]
            n = len(sub)
            wins   = sub[sub["win"]]
            losses = sub[~sub["win"]]
            gp = wins["pnl"].sum()   if not wins.empty   else 0.0
            gl = abs(losses["pnl"].sum()) if not losses.empty else 1e-9
            rows.append({
                "Fold":         fold_num,
                "Periodo OOS":  period,
                "OOS Sharpe":   round(float(oos_sharpe), 3) if oos_sharpe is not None else None,
                "Direzione":    direction,
                "N trade":      n,
                "Win rate %":   round(sub["win"].mean() * 100, 1) if n > 0 else 0.0,
                "PF":           round(gp / gl, 3) if n > 0 else 0.0,
                "P&L totale":   round(sub["pnl"].sum(), 2),
                "SL hit %":     round((sub["exit_reason"] == "SL").mean() * 100, 1) if n > 0 else 0.0,
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
) -> list[str]:
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


# ── Improvement prompt ────────────────────────────────────────────────────────

def build_improvement_prompt(asset: str) -> str:
    """Build a comprehensive prompt for strategy improvement via vibe-trading/LLM."""
    trades_df = load_trades(asset)
    wfo_df    = load_wfo("IS8m_OOS2m")

    # Load comparison metrics
    comp_path = os.path.join(OUTPUT_DIR, "enhanced_strategy_comparison.csv")
    comp_text = ""
    if os.path.exists(comp_path):
        try:
            comp = pd.read_csv(comp_path)
            comp_text = comp.to_string(index=False)
        except Exception:
            pass

    # Load current config
    cfg_path = os.path.join(OUTPUT_DIR, "agent_strategy_config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path))
        except Exception:
            pass

    # Load MC percentiles
    mc_path = os.path.join(OUTPUT_DIR, "mc_bootstrap_results.csv")
    mc_text = ""
    if os.path.exists(mc_path):
        try:
            mc = pd.read_csv(mc_path)
            mc_text = mc.to_string(index=False)
        except Exception:
            pass

    # Load statistical analysis
    from agent_strategy import _build_context, _atr_stats
    stat_ctx  = _build_context(asset)
    atr_stats = _atr_stats(asset)

    # Trade analysis
    dir_text  = direction_stats(trades_df).to_string(index=False)   if not trades_df.empty else "N/A"
    hour_text = hourly_stats(trades_df).to_string(index=False)      if not trades_df.empty else "N/A"
    fold_text = fold_direction_stats(trades_df, wfo_df).to_string(index=False) if not trades_df.empty and not wfo_df.empty else "N/A"
    reg_text  = regime_stats(trades_df).to_string(index=False)      if not trades_df.empty else "N/A"
    streaks   = streak_stats(trades_df)
    issues    = identify_weaknesses(trades_df, wfo_df)

    current_strategy = (
        f"strategy_type={cfg.get('strategy_type','unknown')}  "
        f"sl_mult={cfg.get('sl_mult',2.0)}  tp_mult={cfg.get('tp_mult',5.0)}  "
        f"active_hours={cfg.get('active_hours',[6,22])}  source={cfg.get('source','?')}"
    )

    prompt = f"""You are a quantitative trading strategist. Your task: redesign the current trading strategy for {asset} to achieve POSITIVE real returns that are statistically significant (OOS Sharpe > 0.5, Profit Factor > 1.3, N_trades ≥ 20).

══ CURRENT STRATEGY ══
{current_strategy}
Rationale: {cfg.get('rationale', 'N/A')}

══ STATISTICAL PROPERTIES ({asset}) ══
{stat_ctx}

ATR: median {atr_stats.get('median_atr_pct', '?')}% of price

══ CURRENT PERFORMANCE ══
{comp_text}

══ TRADE ANALYSIS: LONG vs SHORT ══
{dir_text}

══ TRADE ANALYSIS: BY GARCH REGIME ══
{reg_text}

══ TRADE ANALYSIS: BY UTC HOUR (LONG/SHORT) ══
{hour_text}

══ WALK-FORWARD: OOS FOLD × DIRECTION ══
{fold_text}

══ STREAK ANALYSIS ══
Max winning streak : {streaks.get('max_win_streak', '?')}
Max losing streak  : {streaks.get('max_loss_streak', '?')}

══ MONTE CARLO BOOTSTRAP (5000 sims) ══
{mc_text}

══ IDENTIFIED WEAKNESSES ══
{chr(10).join(issues)}

══ YOUR TASK ══
Using ALL the data above, design an IMPROVED strategy that fixes the identified weaknesses.
Focus on:
1. Commission mathematics: ensure TP/SL ≥ 2.5 after 0.08% round-trip cost.
2. If LONG or SHORT is net-negative: disable or restrict that direction.
3. Remove losing UTC hours from active_hours.
4. If OOS Sharpe is consistently negative: simplify entry (fewer conditions = less overfit).
5. Adjust sl_mult if SL hit rate > 65% (SL too tight).

Return EXACTLY these three fenced blocks:

```json
{{
  "strategy_type": "<trend_following|mean_reversion|breakout|momentum>",
  "strategy_name": "<descriptive name v2>",
  "sl_mult": <float ≥ 1.5>,
  "tp_mult": <float, TP/SL ≥ 2.5>,
  "active_hours": [<start 0-23>, <end 0-23>],
  "commission": 0.0004,
  "slippage": 0.0001,
  "risk_per_trade": 0.01,
  "rationale": "<one sentence: what you changed and why>"
}}
```

```python
def generate_signals_agent(df):
    df = df.copy()
    # use only pd and np (already imported)
    # df["signal"]  = 1 / -1 / 0
    # df["SL_dist"] = ATR14 * sl_mult
    # df["TP_dist"] = ATR14 * tp_mult
    return df
```

```markdown
# Improvement Report
## What Changed
[bullet list of specific changes vs current strategy]
## Why These Changes Fix the Weaknesses
[reference the identified weaknesses above]
## Expected OOS Performance
[estimated Sharpe, PF, WR based on the data above]
```
"""
    return prompt
