"""
agent_strategy.py
=================
AI agent that analyses BTC/USD statistical results and designs a trading
strategy FROM SCRATCH — choosing the best strategy type (trend following,
mean reversion, breakout, range trading) based on the time-series properties.

Outputs:
  output/agent_strategy_config.json  — strategy metadata + parameters
  output/agent_strategy_code.py      — Python function generate_signals_agent(df)
  output/agent_strategy_report.md    — markdown explanation of the choice

Provider priority (first key found wins):
  1. ANTHROPIC_API_KEY  → claude-opus-4-7, adaptive thinking + prompt caching
  2. OPENROUTER_API_KEY → OpenRouter HTTP (model via OPENROUTER_MODEL env var)
  3. Neither            → V5 ATR-breakout defaults, no API call
"""

import os
import json
import re
import warnings

warnings.filterwarnings("ignore")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OPENROUTER_API_URL     = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "anthropic/claude-opus-4"

# ── V5 default config (used as fallback) ──────────────────────────────────────

V5_DEFAULT_CONFIG = {
    "asset": "BTC-USD",
    "strategy_type": "breakout",
    "strategy_name": "ATR Breakout + GARCH Filter (V5 Default)",
    "sl_mult": 2.0,
    "tp_mult": 5.0,
    "active_hours": [6, 22],
    "commission": 0.0004,
    "slippage":   0.0001,
    "risk_per_trade": 0.01,
    "rationale": (
        "Default V5: ATR breakout + GARCH filter, SL=2×ATR, TP=5×ATR, "
        "maker fee 0.01%/side, active hours 06-22 UTC."
    ),
    "source": "default",
}

# ── Fallback strategy code (mirrors V5 generate_signals_v2) ──────────────────

DEFAULT_CODE = """\
def generate_signals_agent(df):
    \"\"\"Default V5 strategy: ATR breakout + GARCH filter.\"\"\"
    df = df.copy()
    time_ok     = (df["hour"] >= 6) & (df["hour"] <= 22)
    vol_ok      = df["ATR_pct"] > 0.003
    trend_long  = df["EMA50"] > df["EMA200"]
    trend_short = df["EMA50"] < df["EMA200"]
    bo_long     = df["Close"] > df["RollHigh6"]
    bo_short    = df["Close"] < df["RollLow6"]
    rsi_ok_l    = df["RSI14"] < 70
    rsi_ok_s    = df["RSI14"] > 30
    if "garch_regime" in df.columns:
        regime_ok = df["garch_regime"] != "LOW"
    else:
        regime_ok = True
    df["signal"] = 0
    df.loc[bo_long  & trend_long  & rsi_ok_l & time_ok & vol_ok & regime_ok, "signal"] =  1
    df.loc[bo_short & trend_short & rsi_ok_s & time_ok & vol_ok & regime_ok, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * 2.0
    df["TP_dist"] = df["ATR14"] * 5.0
    return df
"""

DEFAULT_REPORT = """\
# Strategy Report: ATR Breakout + GARCH Filter (V5 Default)

## Note
This is the default V5 strategy used when no API key is configured.
Set `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY` to let the AI agent design
a custom strategy from the statistical analysis results.

## Strategy Summary
- **Type**: Breakout
- **Entry**: price breaks 6-bar rolling high/low with EMA trend alignment
- **SL**: 2×ATR14  |  **TP**: 5×ATR14
- **Filter**: GARCH regime (skip LOW-vol periods), RSI, active hours 06-22 UTC
"""

# ── File helpers ──────────────────────────────────────────────────────────────

def _read_safe(path: str, max_chars: int = 6000) -> str:
    if not os.path.exists(path):
        return f"[not found: {os.path.basename(path)}]"
    try:
        txt = open(path, encoding="utf-8").read(max_chars)
        return txt + ("\n[truncated]" if len(txt) == max_chars else "")
    except Exception as exc:
        return f"[error: {exc}]"


def _atr_stats(asset: str) -> dict:
    """Compute median ATR14 and ATR% from hourly CSV for SL/TP calibration."""
    try:
        import re as _re, pandas as _pd, numpy as _np
        alias = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}
        fname = alias.get(asset) or _re.sub(r"[^a-z0-9]", "_", asset.lower()).strip("_")
        df = _pd.read_csv(os.path.join(OUTPUT_DIR, f"{fname}_hourly.csv"),
                          index_col=0, parse_dates=True)
        df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
        close = df["Close"].values
        h, lo = df["High"].values, df["Low"].values
        tr = _np.maximum(h - lo,
             _np.maximum(abs(h - _np.roll(close, 1)),
                         abs(lo - _np.roll(close, 1))))
        atr14 = _pd.Series(tr[1:]).rolling(14).mean().dropna().values
        med_atr = float(_np.median(atr14))
        med_prc = float(_np.median(close[-len(atr14):]))
        med_pct = med_atr / med_prc * 100
        return {
            "median_atr":     round(med_atr, 2),
            "median_atr_pct": round(med_pct, 3),
            "sl2x_pct":       round(2.0 * med_pct, 3),
        }
    except Exception:
        return {}


def _parse_wfo_insight() -> str:
    """Extract actionable insights from walk_forward_results.csv."""
    try:
        import pandas as _pd, numpy as _np
        df = _pd.read_csv(os.path.join(OUTPUT_DIR, "walk_forward_results.csv"))
        n_pos = (df["oos_sharpe"] > 0).sum()
        n_tot = len(df)
        best_is_sl = df["best_sl"].mode().iloc[0] if not df["best_sl"].empty else "?"
        best_is_tp = df["best_tp"].mode().iloc[0] if not df["best_tp"].empty else "?"
        oos_mean   = df["oos_sharpe"].mean()
        is_mean    = df["is_sharpe"].mean()
        overfit    = is_mean > 1.0 and oos_mean < 0
        lines = [
            f"Walk-Forward ({n_tot} folds): "
            f"OOS Sharpe avg={oos_mean:.2f}  IS Sharpe avg={is_mean:.2f}  "
            f"OOS profitable folds: {n_pos}/{n_tot}",
            f"Most common IS-optimal params: SL={best_is_sl}×ATR, TP={best_is_tp}×ATR",
        ]
        if overfit:
            lines.append(
                "⚠️ IS→OOS degradation detected: grid-search IS params overfit badly. "
                "Do NOT copy IS-optimal SL/TP. Use conservative SL ≥ 2×ATR, TP ≥ 4×ATR "
                "for better OOS robustness."
            )
        elif oos_mean > 0.3:
            lines.append(f"✅ OOS Sharpe is positive on average — IS params generalise reasonably.")
        return "\n".join(lines)
    except Exception:
        return ""


def _parse_optim_insight() -> str:
    """Extract top-3 SL/TP combinations from optimization_results.csv."""
    try:
        import pandas as _pd
        df = _pd.read_csv(os.path.join(OUTPUT_DIR, "optimization_results.csv"))
        df = df.sort_values("sharpe", ascending=False).head(5)
        lines = ["Top IS parameter combinations (grid search, use as rough reference only):"]
        for _, r in df.iterrows():
            lines.append(
                f"  SL={r['sl_mult']:.1f}×ATR / TP={r['tp_mult']:.1f}×ATR  "
                f"hours={r['h_from']:.0f}-{r['h_to']:.0f}  "
                f"Sharpe={r['sharpe']:.2f}  CAGR={r['cagr']:.1f}%  WR={r['win_rate']:.1f}%"
            )
        return "\n".join(lines)
    except Exception:
        return ""


def _best_active_hours(best_hours: list) -> list:
    """Convert a list of best UTC hours to a [start, end] active window."""
    if not best_hours or not isinstance(best_hours, list):
        return [6, 22]
    try:
        hrs = sorted(int(h) for h in best_hours)
        # Find the longest contiguous run
        best_start, best_end, cur_start = hrs[0], hrs[0], hrs[0]
        best_len = 1
        for i in range(1, len(hrs)):
            if hrs[i] - hrs[i-1] <= 2:
                cur_len = hrs[i] - cur_start + 1
                if cur_len > best_len:
                    best_len, best_start, best_end = cur_len, cur_start, hrs[i]
            else:
                cur_start = hrs[i]
        # Expand window by ±1 hour for coverage
        return [max(0, best_start - 1), min(23, best_end + 1)]
    except Exception:
        return [6, 22]


def _build_context(asset: str = "BTC-USD") -> str:
    _fname = re.sub(r"[^a-z0-9]", "_", asset.lower()).strip("_")
    asset_json   = os.path.join(OUTPUT_DIR, f"analysis_report_{_fname}.json")
    generic_json = os.path.join(OUTPUT_DIR, "analysis_report.json")
    report_json  = asset_json if os.path.exists(asset_json) else generic_json
    if os.path.exists(report_json):
        try:
            with open(report_json) as f:
                rpt = json.load(f)
            s   = rpt.get("statistics", {})
            g   = rpt.get("garch", {})
            v4  = rpt.get("v4_baseline", {})
            atr = _atr_stats(asset)

            v4_sharpe = float(v4.get("sharpe_ratio", -999) or -999)
            v4_cagr   = float(v4.get("cagr_pct",     -999) or -999)
            target_sharpe = max(0.5, v4_sharpe + 0.5)
            target_cagr   = max(5.0, v4_cagr   + 5.0)

            med_pct = atr.get("median_atr_pct", 0.3)
            comm_rt = 0.08
            be_lines = []
            for sl_m, tp_m in [(1.5, 3.0), (2.0, 4.5), (2.0, 5.0), (2.5, 5.0)]:
                sl_pct = sl_m * med_pct
                tp_pct = tp_m * med_pct
                be = (sl_pct + comm_rt) / (sl_pct + tp_pct) * 100
                be_lines.append(
                    f"  SL={sl_m}×ATR ({sl_pct:.2f}%) / TP={tp_m}×ATR "
                    f"({tp_pct:.2f}%) → break-even WR = {be:.1f}%"
                )

            v4_note = ""
            if v4_cagr < 0:
                v4_note = (
                    "\n  ⚠️ V4 CAGR is NEGATIVE — do NOT replicate its logic. "
                    "It fails due to commission drag."
                )

            kurt_val = float(s.get("excess_kurtosis", 0) or 0)
            acf_val  = float(s.get("acf_lag1", 0) or 0)
            ctx = (
                f"### Asset: {rpt.get('asset', asset)}\n"
                f"Period: {rpt.get('period_start','?')} → {rpt.get('period_end','?')}  "
                f"({rpt.get('n_bars_hourly','?')} hourly bars)\n\n"
                f"### Time-Series Properties\n"
                f"- Hurst exponent: {s.get('hurst_exponent','?')}  →  "
                f"**{str(s.get('regime','?')).upper()}**\n"
                f"  {s.get('regime_description','')}\n"
                f"- ACF lag-1: {s.get('acf_lag1','?')}  "
                f"({'momentum' if acf_val > 0 else 'mean-reversion'})\n"
                f"- Excess kurtosis: {s.get('excess_kurtosis','?')}  "
                f"({'FAT TAILS — use SL ≥ 2.5×ATR' if kurt_val > 5 else 'normal tails — SL 1.5-2×ATR fine'})\n"
                f"- Annualised vol: {s.get('ann_vol_pct','?')}%\n"
                f"- Best UTC hours (avg return +): {s.get('best_hours_utc','?')}\n"
                f"- Worst UTC hours (avg return -): {s.get('worst_hours_utc','?')}\n\n"
                f"### GARCH(1,1)\n"
                f"- alpha={g.get('alpha','?')}  beta={g.get('beta','?')}  "
                f"persistence={g.get('persistence','?')}  (< 1 = stationary)\n"
                f"- Regime distribution: {g.get('regime_pct','?')}\n\n"
                f"### ATR Calibration (critical for SL/TP sizing)\n"
                f"- Median ATR14: ${atr.get('median_atr','?')} = "
                f"{atr.get('median_atr_pct','?')}% of price\n"
                f"- Break-even win rates at commission=0.08% round-trip:\n"
                + "\n".join(be_lines) + "\n\n"
                f"### Baseline V4 (ATR breakout + GARCH filter, taker 0.04%){v4_note}\n"
                f"- CAGR: {v4.get('cagr_pct','?')}%\n"
                f"- Sharpe Ratio: {v4.get('sharpe_ratio','?')}\n"
                f"- Max Drawdown: {v4.get('max_drawdown_pct','?')}%\n"
                f"- Win Rate: {v4.get('win_rate_pct','?')}%\n"
                f"- N trades: {v4.get('n_trades','?')}\n\n"
                f"### Minimum Targets (non-negotiable)\n"
                f"- Target Sharpe  ≥ {target_sharpe:.2f}\n"
                f"- Target CAGR    ≥ {target_cagr:.1f}%\n"
                f"- Profit Factor  ≥ 1.3\n"
                f"- N trades       ≥ 20\n\n"
            )
            # Suggested active_hours derived from best_hours_utc
            _suggested_hours = _best_active_hours(s.get("best_hours_utc", []))
            ctx += (
                f"### Suggested Active Window\n"
                f"Derived from best UTC hours {s.get('best_hours_utc','?')}: "
                f"use active_hours = {_suggested_hours} as starting point.\n\n"
            )

            # Walk-forward insight (interpreted, not raw CSV)
            _wfo = _parse_wfo_insight()
            if _wfo:
                ctx += f"### Walk-Forward Analysis\n{_wfo}\n\n"

            # Top optimization results (interpreted)
            _opt = _parse_optim_insight()
            if _opt:
                ctx += f"### Grid-Search Reference (IS only — treat with caution)\n{_opt}\n\n"

            ctx += f"### Target Asset\nDesign the strategy for **{asset}**.\n"
            return ctx
        except Exception as exc:
            print(f"  [agent] Warning: could not parse analysis_report.json: {exc}")

    # Fallback: raw file dump
    files = [
        ("Statistical Report (BTC reference)", "REPORT.txt"),
        ("Enhanced Strategy Comparison",        "enhanced_strategy_comparison.csv"),
        ("Walk-Forward Results",                "walk_forward_results.csv"),
        ("Monte Carlo Bootstrap",               "mc_bootstrap_results.csv"),
        ("Grid-Search Optimization",            "optimization_results.csv"),
    ]
    ctx = "\n\n".join(
        f"### {title}\n```\n{_read_safe(os.path.join(OUTPUT_DIR, fname))}\n```"
        for title, fname in files
    )
    ctx += f"\n\n{_compute_quick_stats(asset)}"
    ctx += f"\n\n### Target Asset\nDesign the strategy for **{asset}**.\n"
    return ctx


def _extract_block(text: str, lang: str) -> str:
    """Return the content of the first fenced block tagged with *lang*."""
    m = re.search(rf"```{lang}\s*([\s\S]+?)\s*```", text)
    return m.group(1).strip() if m else ""

# ── Validation ────────────────────────────────────────────────────────────────

def _compute_quick_stats(ticker: str) -> str:
    """Compute Hurst, ACF, kurtosis, volatility for any downloaded asset."""
    try:
        import re as _re
        _alias = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}
        fname = _alias.get(ticker) or _re.sub(r"[^a-z0-9]", "_", ticker.lower()).strip("_")
        path = os.path.join(OUTPUT_DIR, f"{fname}_hourly.csv")
        if not os.path.exists(path):
            return f"[dati non disponibili per {ticker}]"
        import pandas as _pd, numpy as _np
        df = _pd.read_csv(path, index_col=0, parse_dates=True)
        df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
        ret = df["Close"].pct_change().dropna()
        lp  = _np.log(df["Close"].values)
        lags = [2, 4, 8, 16, 32, 64, 128]
        rs   = [_np.std(_np.diff(lp, lag)) for lag in lags]
        H    = float(_np.polyfit(_np.log(lags), _np.log(rs), 1)[0])
        acf1 = float(ret.autocorr(1))
        kurt = float(ret.kurtosis())
        vol  = float(ret.std() * _np.sqrt(24 * 365) * 100)
        idx  = _pd.to_datetime(df.index)
        best_hrs = sorted(ret.groupby(idx.hour).mean().nlargest(8).index.tolist())
        regime = ("trend following" if H > 0.55
                  else "mean reversion" if H < 0.45
                  else "breakout/range trading")
        return (
            f"### Proprietà statistiche {ticker}\n"
            f"- Periodo: {df.index[0]} → {df.index[-1]}\n"
            f"- Prezzo attuale: {df['Close'].iloc[-1]:.4f}\n"
            f"- Hurst exponent: {H:.3f} → **{regime}**\n"
            f"- ACF lag-1: {acf1:.3f} ({'momentum' if acf1 > 0 else 'mean reversion'})\n"
            f"- Kurtosis: {kurt:.2f} ({'fat tails' if kurt > 5 else 'normal tails'})\n"
            f"- Volatilità annualizzata: {vol:.1f}%\n"
            f"- Ore UTC più attive: {best_hrs}\n"
        )
    except Exception as exc:
        return f"[errore stats {ticker}: {exc}]"


def _validate_config(raw: dict, source: str = "agent") -> dict:
    d  = V5_DEFAULT_CONFIG
    sl = max(0.5, min(5.0,  float(raw.get("sl_mult",       d["sl_mult"]))))
    tp = max(sl + 0.5, min(10.0, float(raw.get("tp_mult",  d["tp_mult"]))))
    ah = raw.get("active_hours", d["active_hours"])
    if isinstance(ah, (list, tuple)) and len(ah) == 2:
        h0 = max(0, min(23, int(ah[0])))
        h1 = max(h0 + 1, min(23, int(ah[1])))
    else:
        h0, h1 = d["active_hours"]
    return {
        "asset":          str(raw.get("asset",          d.get("asset", "BTC-USD"))),
        "strategy_type":  str(raw.get("strategy_type", d["strategy_type"])),
        "strategy_name":  str(raw.get("strategy_name", d["strategy_name"])),
        "sl_mult":        sl,
        "tp_mult":        tp,
        "active_hours":   [h0, h1],
        "commission":     max(0.0, min(0.005, float(raw.get("commission",    d["commission"])))),
        "slippage":       max(0.0, min(0.005, float(raw.get("slippage",      d["slippage"])))),
        "risk_per_trade": max(0.005, min(0.05, float(raw.get("risk_per_trade", d["risk_per_trade"])))),
        "rationale":      str(raw.get("rationale", d["rationale"])),
        "source":         source,
    }


def _validate_code(code: str) -> str:
    """Compile-check and smoke-test the generated strategy function."""
    import numpy as np
    import pandas as pd

    # 1. syntax check
    compile(code, "<agent_code>", "exec")

    # 2. execute in isolated namespace
    ns: dict = {"np": np, "pd": pd}
    exec(code, ns)                                          # noqa: S102
    if "generate_signals_agent" not in ns:
        raise ValueError("generate_signals_agent not defined in generated code")

    # 3. smoke-test with a tiny synthetic DataFrame
    n   = 60
    idx = pd.date_range("2023-01-01", periods=n, freq="h")
    rng = np.random.default_rng(0)
    base = 30_000 + rng.standard_normal(n).cumsum() * 200
    df = pd.DataFrame({
        "Open":   base,  "High": base + 50,
        "Low":    base - 50, "Close": base,
        "Volume": rng.uniform(1, 10, n),
        "ATR14":  rng.uniform(100, 400, n),
        "RSI14":  rng.uniform(20, 80, n),
        "EMA50":  base * 0.99, "EMA200": base * 0.98,
        "RollHigh6": base + 100, "RollLow6": base - 100,
        "ATR_pct": rng.uniform(0.002, 0.01, n),
        "hour":    np.tile(np.arange(24), 3)[:n],
        "dow":     rng.integers(0, 7, n),
        "ret":     rng.standard_normal(n) * 0.01,
        "garch_h": rng.uniform(1e-6, 1e-4, n),
        "garch_regime": np.random.choice(["LOW", "MED", "HIGH"], n),
        "size_mult": np.random.choice([0.0, 0.5, 1.0], n),
    }, index=idx)

    result = ns["generate_signals_agent"](df)
    missing = [c for c in ("signal", "SL_dist", "TP_dist") if c not in result.columns]
    if missing:
        raise ValueError(f"Missing output columns: {missing}")
    return code

# ── System prompt ─────────────────────────────────────────────────────────────

def _make_system_prompt(asset: str = "BTC-USD") -> str:
    return f"""\
You are an expert quantitative trading strategist and Python developer for crypto markets.

## CORE OBJECTIVE
Design a strategy for **{asset}** that generates POSITIVE real returns after 0.04% taker fees (0.08% round-trip).
Your code will be backtested automatically — design it to achieve the gates below.

## PROFITABILITY GATES (design targets)
- Profit Factor  > 1.3   (gross_profit / |gross_loss|)
- Sharpe Ratio   > 0.5   (annualised, after commission)
- CAGR           > 5%    (after commission)
- N trades       ≥ 20    (enough for statistical significance)

## STEP-BY-STEP DESIGN PROCESS
Follow these steps in order:

**Step 1 — Read the statistical regime** from the context:
- Hurst > 0.55 → trend following (momentum)
- Hurst < 0.45 → mean reversion
- Hurst 0.45-0.55 → breakout / range
- ACF lag-1 positive → strengthens trend case
- Kurtosis > 5 → fat tails, use SL ≥ 2.5×ATR

**Step 2 — Fix SL and TP** using the ATR Calibration table in the context.
Commission eats ~0.08% round-trip. Rule: use TP/SL ≥ 2.5 always.

**Step 3 — Fix active_hours** using the suggested window in the context.
Trading in bad hours destroys edge. Restrict to the best 8-14 UTC hours.

**Step 4 — Choose entry signal** matching the regime (see patterns below).
Verify mentally: will this signal fire ≥ 20 times over the data period?

**Step 5 — Add one quality filter** (GARCH regime, RSI boundary, ATR_pct threshold).
One filter is enough — over-filtering reduces trade count below significance threshold.

## COMMISSION MATHEMATICS
Taker fee: 0.04%/side = 0.08% round-trip.
Break-even win rate by R:R ratio:

| R:R  | Break-even WR |
|------|--------------|
| 1:1  | ~50.1%       |
| 1:2  | ~33.5%       |
| 1:2.5| ~28.8%       |
| 1:3  | ~25.1%       |
| 1:4  | ~20.2%       |

## PATTERNS BY REGIME

### Pattern A — ATR Momentum Breakout (Hurst > 0.55)
Entry long:  Close > RollHigh6 AND EMA50 > EMA200 AND RSI14 < 70
Entry short: Close < RollLow6  AND EMA50 < EMA200 AND RSI14 > 30
SL=2×ATR14, TP=5×ATR14 | Filter: garch_regime != "LOW"
Typical WR 35-45%, PF 1.3-1.8

### Pattern B — RSI Mean Reversion (Hurst < 0.45)
Entry long:  RSI14 < 32 AND Close < EMA200 * 0.99
Entry short: RSI14 > 68 AND Close > EMA200 * 1.01
SL=1.5×ATR14, TP=4×ATR14 | Filter: ATR_pct > 0.002 (avoid dead markets)
Typical WR 45-55%, PF 1.2-1.6

### Pattern C — EMA Trend Filter + Breakout (any regime)
Entry long:  EMA50 > EMA200 AND Close > RollHigh6 AND hour in active window
Entry short: EMA50 < EMA200 AND Close < RollLow6  AND hour in active window
SL=2×ATR14, TP=4.5×ATR14 | (uses EMA50/EMA200 which are pre-computed)
Typical WR 38-48%, PF 1.2-1.5

### Pattern D — Volatility Breakout (Hurst 0.45-0.55)
Compute inline: `ema20 = df["Close"].ewm(span=20).mean()`
Entry long:  ATR_pct > ATR_pct.rolling(24).mean()*1.3 AND Close > RollHigh6 AND EMA50 > ema20
Entry short: ATR_pct > ATR_pct.rolling(24).mean()*1.3 AND Close < RollLow6  AND EMA50 < ema20
SL=2.5×ATR14, TP=6×ATR14
Typical WR 30-40%, PF 1.4-2.0

## INLINE INDICATORS (allowed and encouraged)
You MAY compute additional indicators inside `generate_signals_agent(df)`:
```python
ema20    = df["Close"].ewm(span=20, adjust=False).mean()
bb_mid   = df["Close"].rolling(20).mean()
bb_std   = df["Close"].rolling(20).std()
bb_upper = bb_mid + 2 * bb_std
bb_lower = bb_mid - 2 * bb_std
vol_regime = df["ATR_pct"] > df["ATR_pct"].rolling(48).mean()
```
These are all valid — use them freely.

## `size_mult` USAGE
`size_mult` encodes GARCH-derived position size: 0.5 in LOW-vol, 1.0 in MED/HIGH.
You do NOT need to use it directly in signals. Your signal=1/-1/0 logic is enough.
Optionally: add `df.loc[df["size_mult"] == 0, "signal"] = 0` to skip dead-vol periods.

## ANTI-PATTERNS
1. ❌ SL < 1.5×ATR — stops out on noise before TP fires
2. ❌ TP/SL ratio < 2.5 — commission makes edge negative
3. ❌ Trading all 24 hours — restrict to best UTC window from context
4. ❌ Zero/too few signals — test that your conditions overlap; relax one if signal count < 20
5. ❌ Copying grid-search IS params blindly — they overfit; prefer SL ≥ 2.0×ATR

## FUNCTION CONTRACT
Pre-computed columns available: Open, High, Low, Close, Volume, ATR14, RSI14,
EMA50, EMA200, RollHigh6, RollLow6, ATR_pct, hour, dow, ret, garch_h,
garch_regime ("LOW"/"MED"/"HIGH"), size_mult.

The function **must**:
- Start with `df = df.copy()`
- Set `df["signal"]` to 1 (long), -1 (short), or 0 (flat)
- Set `df["SL_dist"]` = ATR14 × sl_mult (absolute price units)
- Set `df["TP_dist"]` = ATR14 × tp_mult (TP_dist / SL_dist ≥ 2.5)
- Return `df`
- Use only `numpy` (as `np`) and `pandas` (as `pd`) — both are pre-imported

## RESPONSE FORMAT
Return **exactly** these three fenced blocks — nothing else:

```json
{{
  "strategy_type": "<trend_following|mean_reversion|breakout|range_trading|momentum>",
  "strategy_name": "<descriptive name>",
  "sl_mult": <float, ≥ 1.5>,
  "tp_mult": <float, ≥ sl_mult × 2.5>,
  "active_hours": [<start 0-23>, <end 0-23>],
  "commission": 0.0004,
  "slippage":   0.0001,
  "risk_per_trade": 0.01,
  "rationale": "<one sentence: regime → pattern → why R:R beats commission>"
}}
```

```python
def generate_signals_agent(df):
    df = df.copy()
    # ... your implementation ...
    return df
```

```markdown
# Strategy Report: <strategy_name>

## Statistical Regime
[Hurst, ACF, kurtosis → regime conclusion]

## Parameter Calibration
[ATR% → SL/TP in % terms → break-even WR → expected actual WR → edge]

## Entry Logic
[Which pattern, what conditions, expected signal frequency]

## Active Hours
[Why this window from best_hours_utc data]

## Expected Performance
[Estimated WR, PF, Sharpe — and why these gates should be met]
```
"""

SYSTEM_PROMPT = _make_system_prompt()  # default (BTC-USD) for backward compat

# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_response(text: str, source: str) -> tuple:
    """Return (config_dict, code_str, report_str) from Claude's response."""
    json_raw = _extract_block(text, "json")
    if not json_raw:
        raise ValueError("No ```json block found in response")
    config = _validate_config(json.loads(json_raw), source=source)

    code = _extract_block(text, "python")
    if not code:
        raise ValueError("No ```python block found in response")
    _validate_code(code)

    report = _extract_block(text, "markdown")
    return config, code, report


# ── Anthropic backend ─────────────────────────────────────────────────────────

def _call_anthropic(api_key: str, context: str, asset: str = "BTC-USD") -> tuple:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Run: pip install anthropic")

    user_msg = (
        f"Analyse the {asset} results and design the optimal strategy.\n\n"
        + context
        + "\n\nReturn exactly the three fenced blocks specified."
    )
    client = anthropic.Anthropic(api_key=api_key)
    print("  [agent] Calling claude-opus-4-7 (adaptive thinking + cache)...")
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": _make_system_prompt(asset),
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": [
            {"type": "text", "text": user_msg,
             "cache_control": {"type": "ephemeral"}}
        ]}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    if not text:
        raise ValueError("Empty Anthropic response")
    u = resp.usage
    cr = getattr(u, "cache_read_input_tokens", 0)
    print(f"  [agent] tokens in={u.input_tokens} out={u.output_tokens}"
          + (f" cache_read={cr}" if cr else ""))
    return _parse_response(text, source="anthropic")


# ── OpenRouter backend ────────────────────────────────────────────────────────

def _call_openrouter(api_key: str, context: str, model: str = "",
                     asset: str = "BTC-USD") -> tuple:
    import requests as _req
    model = model or os.environ.get("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL)
    print(f"  [agent] Calling OpenRouter model={model}...")
    user_msg = (
        f"Analyse the {asset} results and design the optimal strategy.\n\n"
        + context
        + "\n\nReturn exactly the three fenced blocks specified."
    )
    resp = _req.post(
        OPENROUTER_API_URL,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/gabrieledemarco/crypto1",
                 "X-Title": "Crypto Strategy Agent"},
        json={"model": model, "max_tokens": 8192,
              "messages": [{"role": "system", "content": _make_system_prompt(asset)},
                           {"role": "user",   "content": user_msg}]},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    u = data.get("usage", {})
    print(f"  [agent] tokens in={u.get('prompt_tokens','?')} "
          f"out={u.get('completion_tokens','?')}")
    return _parse_response(text, source=f"openrouter/{model}")


# ── Quick backtest ─────────────────────────────────────────────────────────────

def _quick_backtest(code_str: str, asset: str) -> dict:
    """Run a vectorised backtest of the generated strategy; returns metrics dict."""
    try:
        import re as _re, pandas as _pd, numpy as _np
        alias = {"BTC-USD": "btc", "ETH-USD": "eth", "SOL-USD": "sol"}
        fname = alias.get(asset) or _re.sub(r"[^a-z0-9]", "_", asset.lower()).strip("_")
        path = os.path.join(OUTPUT_DIR, f"{fname}_hourly.csv")
        if not os.path.exists(path):
            return {}
        df = _pd.read_csv(path, index_col=0, parse_dates=True)
        df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]

        # Build indicators
        c, h, lo = df["Close"].values, df["High"].values, df["Low"].values
        tr = _np.maximum(h - lo,
             _np.maximum(abs(h - _np.roll(c, 1)), abs(lo - _np.roll(c, 1))))
        df["ATR14"]    = _pd.Series(tr, index=df.index).rolling(14).mean()
        df["ATR_pct"]  = df["ATR14"] / df["Close"]
        df["EMA50"]    = df["Close"].ewm(span=50,  adjust=False).mean()
        df["EMA200"]   = df["Close"].ewm(span=200, adjust=False).mean()
        delta = df["Close"].diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        df["RSI14"]    = 100 - 100 / (1 + gain / loss.replace(0, _np.nan))
        df["RollHigh6"] = df["High"].rolling(6).max().shift(1)
        df["RollLow6"]  = df["Low"].rolling(6).min().shift(1)
        idx = _pd.to_datetime(df.index)
        df["hour"] = idx.hour
        df["dow"]  = idx.dayofweek
        df["ret"]  = df["Close"].pct_change()
        roll_vol   = df["ret"].rolling(24).std()
        q33, q66   = roll_vol.quantile(0.33), roll_vol.quantile(0.66)
        df["garch_h"] = roll_vol ** 2
        df["garch_regime"] = _pd.cut(roll_vol,
                                      bins=[-_np.inf, q33, q66, _np.inf],
                                      labels=["LOW", "MED", "HIGH"])
        df["size_mult"] = (df["garch_regime"].map({"LOW": 0.5, "MED": 1.0, "HIGH": 1.0})
                           .fillna(1.0))
        df = df.dropna()

        ns = {"np": _np, "pd": _pd}
        exec(code_str, ns)
        df = ns["generate_signals_agent"](df)

        commission = 0.0004
        signals = df["signal"].values
        close   = df["Close"].values
        sl_arr  = df["SL_dist"].values
        tp_arr  = df["TP_dist"].values

        pnl_list: list = []
        in_trade = 0
        entry_price = entry_sl = entry_tp = 0.0

        for i in range(1, len(df)):
            if in_trade != 0:
                if in_trade == 1:
                    if close[i] <= entry_price - entry_sl:
                        pnl_list.append(-entry_sl / entry_price - commission)
                        in_trade = 0
                    elif close[i] >= entry_price + entry_tp:
                        pnl_list.append(entry_tp / entry_price - commission)
                        in_trade = 0
                else:
                    if close[i] >= entry_price + entry_sl:
                        pnl_list.append(-entry_sl / entry_price - commission)
                        in_trade = 0
                    elif close[i] <= entry_price - entry_tp:
                        pnl_list.append(entry_tp / entry_price - commission)
                        in_trade = 0
            if in_trade == 0 and signals[i] != 0:
                in_trade    = int(signals[i])
                entry_price = close[i]
                entry_sl    = sl_arr[i]
                entry_tp    = tp_arr[i]

        if not pnl_list:
            return {"n_trades": 0, "sharpe": -999.0, "cagr": -999.0, "profit_factor": 0.0,
                    "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0}

        pnl    = _np.array(pnl_list)
        wins   = pnl[pnl > 0]
        losses = pnl[pnl < 0]
        gross_profit = float(wins.sum())   if len(wins)   > 0 else 0.0
        gross_loss   = abs(float(losses.sum())) if len(losses) > 0 else 1e-9
        pf     = gross_profit / gross_loss
        equity = _np.cumprod(1 + pnl)
        n_years = len(df) / (24 * 365)
        cagr   = float((equity[-1] ** (1 / max(n_years, 0.1)) - 1) * 100)
        ann_f  = 24 * 365 / max(len(df) / len(pnl), 1)
        sharpe = float(_np.mean(pnl) / (_np.std(pnl) + 1e-9) * _np.sqrt(ann_f))
        return {
            "n_trades":     len(pnl),
            "win_rate":     round(len(wins) / len(pnl) * 100, 1),
            "sharpe":       round(sharpe, 3),
            "cagr":         round(cagr, 2),
            "profit_factor": round(pf, 3),
            "avg_win":      round(float(_np.mean(wins))   * 100 if len(wins)   > 0 else 0.0, 3),
            "avg_loss":     round(float(_np.mean(losses)) * 100 if len(losses) > 0 else 0.0, 3),
        }
    except Exception as exc:
        print(f"  [agent] Backtest error: {exc}")
        return {}


# ── Stats-based strategy generator (no LLM required) ─────────────────────────

def _generate_strategy_from_stats(asset: str = "BTC-USD",
                                  strategy_hint: str = "") -> tuple:
    """Translate statistical properties into a trading strategy without an LLM.

    Rules applied:
      Hurst > 0.55 → trend following (EMA cross + breakout entry)
      Hurst < 0.45 → mean reversion  (RSI + Bollinger Band entry)
      Hurst 0.45-0.55 → breakout     (ATR channel breakout)
      Kurtosis > 7 → SL = 2.5×ATR   (fat tails)
      Kurtosis > 4 → SL = 2.0×ATR
      else         → SL = 1.5×ATR
      GARCH persistence > 0.85 → apply regime filter
      Best UTC hours → derive active window
    """
    _fname = re.sub(r"[^a-z0-9]", "_", asset.lower()).strip("_")
    report_path = os.path.join(OUTPUT_DIR, f"analysis_report_{_fname}.json")
    if not os.path.exists(report_path):
        report_path = os.path.join(OUTPUT_DIR, "analysis_report.json")

    with open(report_path) as _f:
        rpt = json.load(_f)

    s = rpt.get("statistics", {})
    g = rpt.get("garch", {})

    hurst      = float(s.get("hurst_exponent", 0.5))
    acf1       = float(s.get("acf_lag1", 0))
    kurt       = float(s.get("excess_kurtosis", 3))
    best_hours = s.get("best_hours_utc", [6, 7, 9, 10, 13, 15, 16, 17])
    garch_pers = float(g.get("persistence", 0.95))
    regime     = str(s.get("regime", "breakout"))

    atr_data     = _atr_stats(asset)
    active_hours = _best_active_hours(best_hours)
    h_start, h_end = active_hours

    # SL calibration based on kurtosis (fat-tail risk)
    if kurt > 7:
        sl_mult = 2.5
    elif kurt > 4:
        sl_mult = 2.0
    else:
        sl_mult = 1.5

    # TP: maintain ≥ 2.8:1 R:R after 0.08% round-trip commission
    tp_mult = round(sl_mult * 2.8, 1)

    use_garch = garch_pers > 0.85

    garch_block = (
        '    if "garch_regime" in df.columns:\n'
        '        garch_ok = df["garch_regime"] != "LOW"\n'
        "    else:\n"
        "        garch_ok = True"
        if use_garch else
        "    garch_ok = True"
    )

    # Build two-window time filter from best hours
    # Split best_hours into morning (0-12) and afternoon (12-23) clusters
    _bh = sorted(int(h) for h in best_hours) if best_hours else list(range(6, 18))
    _morning = [h for h in _bh if h < 13]
    _afternoon = [h for h in _bh if h >= 13]
    if _morning and _afternoon:
        m_start, m_end = _morning[0], _morning[-1]
        a_start, a_end = _afternoon[0], _afternoon[-1]
        time_filter = (
            f"    time_ok = ((df[\"hour\"] >= {m_start}) & (df[\"hour\"] <= {m_end})) "
            f"| ((df[\"hour\"] >= {a_start}) & (df[\"hour\"] <= {a_end}))"
        )
        active_hours = [m_start, a_end]
    elif _morning:
        m_start, m_end = max(0, _morning[0] - 1), min(23, _morning[-1] + 1)
        time_filter = f"    time_ok = (df[\"hour\"] >= {m_start}) & (df[\"hour\"] <= {m_end})"
        active_hours = [m_start, m_end]
    else:
        time_filter = f"    time_ok = (df[\"hour\"] >= {h_start}) & (df[\"hour\"] <= {h_end})"

    # User hint takes priority over the Hurst-based decision.
    _hint = strategy_hint.lower()
    _hint_type = None
    if any(k in _hint for k in ("mean reversion", "mean_reversion", "zscore",
                                 "z-score", "z score", "reversion", "mean rev")):
        _hint_type = "mean_reversion"
    elif any(k in _hint for k in ("trend following", "trend_following",
                                   "momentum", "trending", "ema cross")):
        _hint_type = "trend_following"
    elif any(k in _hint for k in ("breakout", "break out", "channel break",
                                   "range", "volatility break")):
        _hint_type = "breakout"

    if hurst > 0.55:
        strategy_type = _hint_type or "trend_following"
        strategy_name = f"Stat-Derived Trend Following — {asset}"
        rationale = (
            f"Hurst={hurst:.4f}>0.55 → momentum/trending regime; "
            f"ACF(1)={acf1:.4f} ({'momentum' if acf1>0 else 'mean-reversion'}); "
            f"kurtosis={kurt:.2f}→SL={sl_mult}×ATR; TP={tp_mult}×ATR→R:R={tp_mult/sl_mult:.1f}:1; "
            f"two windows: morning {_morning[:3]} + afternoon {_afternoon[:3]} UTC."
        )
        code = (
            "def generate_signals_agent(df):\n"
            "    df = df.copy()\n"
            f"    # Two trading windows (best UTC hours: {best_hours[:6]})\n"
            f"{time_filter}\n"
            f"    # Trend filter: require clear EMA gap (Hurst={hurst:.3f} → trend following)\n"
            "    trend_long  = df[\"EMA50\"] > df[\"EMA200\"] * 1.001\n"
            "    trend_short = df[\"EMA50\"] < df[\"EMA200\"] * 0.999\n"
            "    # Entry: price breaks 6-bar rolling high/low\n"
            "    bo_long  = df[\"Close\"] > df[\"RollHigh6\"]\n"
            "    bo_short = df[\"Close\"] < df[\"RollLow6\"]\n"
            "    # RSI: avoid overbought/oversold extremes\n"
            "    rsi_long  = df[\"RSI14\"] < 70\n"
            "    rsi_short = df[\"RSI14\"] > 30\n"
            "    # Volatility filter: require active market\n"
            "    atr_ok = df[\"ATR_pct\"] > 0.002\n"
            f"    # GARCH regime filter (persistence={garch_pers:.4f} → clusters)\n"
            f"{garch_block}\n"
            "    df[\"signal\"] = 0\n"
            "    longs  = bo_long  & trend_long  & rsi_long  & atr_ok & garch_ok & time_ok\n"
            "    shorts = bo_short & trend_short & rsi_short & atr_ok & garch_ok & time_ok\n"
            "    df.loc[longs,  \"signal\"] =  1\n"
            "    df.loc[shorts, \"signal\"] = -1\n"
            f"    # SL={sl_mult}×ATR (kurtosis={kurt:.2f}→fat tails), TP={tp_mult}×ATR→R:R={tp_mult/sl_mult:.1f}:1\n"
            f"    df[\"SL_dist\"] = df[\"ATR14\"] * {sl_mult}\n"
            f"    df[\"TP_dist\"] = df[\"ATR14\"] * {tp_mult}\n"
            "    return df\n"
        )

    elif hurst < 0.45:
        strategy_type = _hint_type or "mean_reversion"
        strategy_name = f"Stat-Derived Mean Reversion — {asset}"
        rationale = (
            f"Hurst={hurst:.4f}<0.45 → mean-reverting regime; "
            f"kurtosis={kurt:.2f}→SL={sl_mult}×ATR; "
            f"active_hours={active_hours}."
        )
        code = (
            "def generate_signals_agent(df):\n"
            "    df = df.copy()\n"
            f"    time_ok = (df[\"hour\"] >= {h_start}) & (df[\"hour\"] <= {h_end})\n"
            f"    # Mean reversion: Hurst={hurst:.3f}<0.45\n"
            "    # Bollinger Bands (20-period, 2σ)\n"
            "    mid = df[\"Close\"].rolling(20).mean()\n"
            "    std = df[\"Close\"].rolling(20).std()\n"
            "    bb_upper = mid + 2.0 * std\n"
            "    bb_lower = mid - 2.0 * std\n"
            "    # RSI extremes for entry confirmation\n"
            "    rsi_oversold   = df[\"RSI14\"] < 30\n"
            "    rsi_overbought = df[\"RSI14\"] > 70\n"
            "    bb_long  = df[\"Close\"] < bb_lower\n"
            "    bb_short = df[\"Close\"] > bb_upper\n"
            "    atr_ok = df[\"ATR_pct\"] > 0.002\n"
            f"{garch_block}\n"
            "    df[\"signal\"] = 0\n"
            "    longs  = bb_long  & rsi_oversold   & atr_ok & garch_ok & time_ok\n"
            "    shorts = bb_short & rsi_overbought & atr_ok & garch_ok & time_ok\n"
            "    df.loc[longs,  \"signal\"] =  1\n"
            "    df.loc[shorts, \"signal\"] = -1\n"
            f"    df[\"SL_dist\"] = df[\"ATR14\"] * {sl_mult}\n"
            f"    df[\"TP_dist\"] = df[\"ATR14\"] * {tp_mult}\n"
            "    return df\n"
        )

    else:
        strategy_type = _hint_type or "breakout"
        strategy_name = f"Stat-Derived ATR Breakout — {asset}"
        rationale = (
            f"Hurst={hurst:.4f}≈0.5 → quasi-random-walk / breakout regime; "
            f"kurtosis={kurt:.2f}→SL={sl_mult}×ATR; "
            f"active_hours={active_hours}."
        )
        code = (
            "def generate_signals_agent(df):\n"
            "    df = df.copy()\n"
            f"    time_ok = (df[\"hour\"] >= {h_start}) & (df[\"hour\"] <= {h_end})\n"
            f"    # ATR breakout: Hurst={hurst:.3f}≈0.5 → breakout\n"
            "    bo_long  = df[\"Close\"] > df[\"RollHigh6\"]\n"
            "    bo_short = df[\"Close\"] < df[\"RollLow6\"]\n"
            "    rsi_long  = df[\"RSI14\"] < 65\n"
            "    rsi_short = df[\"RSI14\"] > 35\n"
            "    atr_ok = df[\"ATR_pct\"] > 0.003\n"
            f"{garch_block}\n"
            "    df[\"signal\"] = 0\n"
            "    df.loc[bo_long  & rsi_long  & atr_ok & garch_ok & time_ok, \"signal\"] =  1\n"
            "    df.loc[bo_short & rsi_short & atr_ok & garch_ok & time_ok, \"signal\"] = -1\n"
            f"    df[\"SL_dist\"] = df[\"ATR14\"] * {sl_mult}\n"
            f"    df[\"TP_dist\"] = df[\"ATR14\"] * {tp_mult}\n"
            "    return df\n"
        )

    _validate_code(code)

    # When a hint overrides the Hurst decision, reflect that in the name
    if _hint_type and _hint_type != (
        "trend_following" if hurst > 0.55 else
        "mean_reversion"  if hurst < 0.45 else "breakout"
    ):
        strategy_name = f"Stat-Derived {_hint_type.replace('_', ' ').title()} — {asset}"
        rationale = f"[Hint: '{strategy_hint[:60]}'] " + rationale

    config = _validate_config({
        "asset":          asset,
        "strategy_type":  strategy_type,
        "strategy_name":  strategy_name,
        "sl_mult":        sl_mult,
        "tp_mult":        tp_mult,
        "active_hours":   active_hours,
        "commission":     0.0004,
        "slippage":       0.0001,
        "risk_per_trade": 0.01,
        "rationale":      rationale,
    }, source="stats_derived")

    report = (
        f"# Strategy Report: {strategy_name}\n"
        f"*Source: stats_derived (Hurst={hurst:.4f}, regime={regime})*\n\n"
        f"**Type**: {strategy_type}\n"
        f"**SL**: {sl_mult}×ATR | **TP**: {tp_mult}×ATR | "
        f"**R:R**: {tp_mult/sl_mult:.1f}:1 | "
        f"**Active hours**: {active_hours} UTC\n\n"
        f"**Rationale**: {rationale}\n\n"
        f"---\n\n```python\n{code}\n```"
    )

    print(
        f"  [agent] Stats-derived strategy: {strategy_name}\n"
        f"          Regime: {regime} | SL={sl_mult}×ATR | TP={tp_mult}×ATR | "
        f"hours={active_hours}"
    )
    return config, code, report


# ── Public entry point ────────────────────────────────────────────────────────

def run_agent(
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
    asset: str = "BTC-USD",
    max_iterations: int = 3,
) -> tuple:
    """
    Returns (config: dict, code: str, report: str).
    Priority: Anthropic → OpenRouter → V5 defaults.
    Runs up to max_iterations refinement loops until profitability gates pass.
    """
    ant = (anthropic_key or "").strip() or os.environ.get("ANTHROPIC_API_KEY",  "").strip()
    ort = (openrouter_key or "").strip() or os.environ.get("OPENROUTER_API_KEY", "").strip()

    if not ant and not ort:
        print("  [agent] No API key — generating strategy from statistical analysis...")
        try:
            return _generate_strategy_from_stats(asset)
        except Exception as exc:
            print(f"  [agent] Stats-derived generation failed ({exc}) — using V5 defaults.")
            cfg = V5_DEFAULT_CONFIG.copy()
            cfg["asset"] = asset
            return cfg, DEFAULT_CODE, DEFAULT_REPORT

    print(f"  [agent] Building analysis context for {asset}...")
    ctx = _build_context(asset)

    # Determine minimum targets from V4 baseline
    target_sharpe = 0.5
    target_cagr   = 5.0
    target_pf     = 1.2
    try:
        rpt_path = os.path.join(OUTPUT_DIR, "analysis_report.json")
        if os.path.exists(rpt_path):
            with open(rpt_path) as _f:
                _rpt = json.load(_f)
            _v4 = _rpt.get("v4_baseline", {})
            target_sharpe = max(0.5, float(_v4.get("sharpe_ratio", -999) or -999) + 0.5)
            target_cagr   = max(5.0, float(_v4.get("cagr_pct",     -999) or -999) + 5.0)
    except Exception:
        pass

    best_result: tuple | None = None
    best_pf: float = -999.0
    last_error = ""

    for iteration in range(1, max_iterations + 1):
        print(f"  [agent] Iteration {iteration}/{max_iterations}...")

        prompt_ctx = ctx
        if iteration > 1 and last_error:
            prompt_ctx = (
                ctx
                + f"\n\n### ⚠️ Previous Attempt Failed (iteration {iteration - 1})\n"
                + last_error
                + "\n\nRevise the strategy to fix ALL issues above. "
                  "Focus on commission mathematics: ensure TP/SL ≥ 2.5 and "
                  "the expected win rate exceeds the break-even threshold."
            )

        try:
            if ant:
                config, code, report = _call_anthropic(ant, prompt_ctx, asset=asset)
            else:
                config, code, report = _call_openrouter(ort, prompt_ctx,
                                                         model=openrouter_model, asset=asset)
        except Exception as exc:
            print(f"  [agent] API error on iteration {iteration}: {exc}")
            last_error = f"API error: {exc}"
            if iteration == max_iterations:
                break
            continue

        print(f"  [agent] Running quick backtest...")
        metrics = _quick_backtest(code, asset)

        if not metrics:
            print(f"  [agent] Backtest execution failed.")
            last_error = ("Backtest failed to run. Use only standard indicators "
                          "(ATR14, RSI14, EMA50, EMA200, RollHigh6/Low6, ATR_pct, hour, dow).")
            if iteration == max_iterations:
                break
            continue

        n    = metrics.get("n_trades", 0)
        sh   = metrics.get("sharpe", -999.0)
        cagr = metrics.get("cagr", -999.0)
        pf   = metrics.get("profit_factor", 0.0)
        wr   = metrics.get("win_rate", 0.0)
        aw   = metrics.get("avg_win", 0.0)
        al   = metrics.get("avg_loss", 0.0)
        rr   = abs(aw / al) if al != 0 else 0.0

        print(f"  [agent] N={n}  WR={wr:.1f}%  Sharpe={sh:.3f}  "
              f"CAGR={cagr:.1f}%  PF={pf:.3f}  R:R≈{rr:.2f}")

        if pf > best_pf:
            best_result, best_pf = (config, code, report), pf

        if sh >= target_sharpe and cagr >= target_cagr and pf >= target_pf and n >= 20:
            print(f"  [agent] ✅ All profitability gates passed on iteration {iteration}.")
            return config, code, report

        failures: list[str] = []
        if n < 20:
            failures.append(
                f"- Only {n} trades (need ≥ 20). Relax entry conditions or extend active_hours."
            )
        if pf < target_pf:
            be_wr = rr / (1 + rr) * 100 if rr > 0 else 50.0
            failures.append(
                f"- Profit Factor {pf:.3f} < {target_pf:.2f}. "
                f"R:R≈{rr:.2f} → break-even WR ≈ {be_wr:.1f}%, actual WR={wr:.1f}%. "
                + ("Increase TP/SL ratio to ≥ 2.5." if rr < 2.5 else "Improve entry signal.")
            )
        if sh < target_sharpe:
            failures.append(
                f"- Sharpe {sh:.3f} < {target_sharpe:.2f}. "
                "Reduce noise trades (add GARCH filter) or improve R:R."
            )
        if cagr < target_cagr:
            failures.append(
                f"- CAGR {cagr:.1f}% < {target_cagr:.1f}%. "
                "Increase TP multiple or trade more selectively in trend direction."
            )

        last_error = "\n".join(failures)
        print(f"  [agent] Gates not met:\n  " + "\n  ".join(failures))

    if best_result is not None:
        print(f"  [agent] Using best result (PF={best_pf:.3f}) after {max_iterations} iterations.")
        return best_result

    print("  [agent] All iterations failed — using V5 defaults.")
    cfg = V5_DEFAULT_CONFIG.copy()
    cfg["asset"] = asset
    return cfg, DEFAULT_CODE, DEFAULT_REPORT

# ── Save helpers ──────────────────────────────────────────────────────────────

def save_outputs(config: dict, code: str, report: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(OUTPUT_DIR, "agent_strategy_config.json"), "w") as f:
        json.dump(config, f, indent=2)

    header = (
        f'"""\nAgent strategy: {config.get("strategy_name","")}\n'
        f'Type: {config.get("strategy_type","")}  |  '
        f'Source: {config.get("source","")}\n"""\n'
        "import numpy as np\nimport pandas as pd\n\n"
    )
    with open(os.path.join(OUTPUT_DIR, "agent_strategy_code.py"), "w") as f:
        f.write(header + code + "\n")

    if report:
        with open(os.path.join(OUTPUT_DIR, "agent_strategy_report.md"), "w") as f:
            f.write(report)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  AGENT STRATEGY — Analisi e generazione strategia")
    print("=" * 60)

    config, code, report = run_agent()
    save_outputs(config, code, report)

    ah = config["active_hours"]
    print(f"\n  Strategia : {config.get('strategy_name','')}")
    print(f"  Tipo      : {config.get('strategy_type','')}")
    print(f"  SL/TP     : {config['sl_mult']:.2f}×ATR / {config['tp_mult']:.2f}×ATR")
    print(f"  Ore UTC   : {ah[0]:02d}:00 – {ah[1]:02d}:00")
    print(f"  Source    : {config.get('source','')}")
    print(f"\n  Rationale : {config.get('rationale','')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
