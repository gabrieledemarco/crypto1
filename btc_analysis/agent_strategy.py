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


def _build_context(asset: str = "BTC-USD") -> str:
    report_json = os.path.join(OUTPUT_DIR, "analysis_report.json")
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
                f"- Win Rate: {v4.get('win_rate','?')}%\n"
                f"- N trades: {v4.get('n_trades','?')}\n\n"
                f"### Minimum Targets (non-negotiable)\n"
                f"- Target Sharpe  ≥ {target_sharpe:.2f}\n"
                f"- Target CAGR    ≥ {target_cagr:.1f}%\n"
                f"- Profit Factor  ≥ 1.3\n"
                f"- N trades       ≥ 20\n\n"
            )
            for title, fname in [
                ("Enhanced Strategy Comparison", "enhanced_strategy_comparison.csv"),
                ("Walk-Forward Results",          "walk_forward_results.csv"),
            ]:
                content = _read_safe(os.path.join(OUTPUT_DIR, fname))
                if not content.startswith("[not found"):
                    ctx += f"### {title}\n```\n{content}\n```\n\n"
            ctx += f"\n### Target Asset\nDesign the strategy for **{asset}**.\n"
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
Every parameter choice must be justified through the commission mathematics below.

## NON-NEGOTIABLE PROFITABILITY GATES
Your strategy MUST achieve ALL of these in backtesting:
- Profit Factor  > 1.3   (gross_profit / |gross_loss|)
- Sharpe Ratio   > 0.5   (annualised, after commission)
- CAGR           > 5%    (after commission)
- N trades       ≥ 20    (statistical significance)

If your strategy fails any gate, REVISE the parameters before responding.

## COMMISSION MATHEMATICS (mandatory knowledge)
Taker fee: 0.04%/side = 0.08% round-trip.
Break-even win rate by R:R ratio (0.08% commission):

| R:R  | Break-even WR |
|------|--------------|
| 1:1  | ~50.1%       |
| 1:2  | ~33.5%       |
| 1:2.5| ~28.8%       |
| 1:3  | ~25.1%       |
| 1:4  | ~20.2%       |

KEY RULE: Always use TP/SL ≥ 2.5 so commission < 5% of expected gain.
Commission eats ~0.3–0.5 ATR per trade on typical crypto. Use SL ≥ 1.5×ATR.

## STRATEGY-TYPE SELECTION
| Hurst exponent | Best strategy type |
|---|---|
| > 0.55 | TREND FOLLOWING — EMA crossover, ATR momentum |
| < 0.45 | MEAN REVERSION — Bollinger Bands, RSI reversal |
| 0.45–0.55 | BREAKOUT or RANGE TRADING |

Additional signals: positive ACF→ momentum, negative ACF→ mean-reversion,
high kurtosis (>5)→ widen SL to ≥ 2.5×ATR to survive fat-tail spikes.

## PROVEN PROFITABLE PATTERNS (start with one of these)

### Pattern A — ATR Momentum Breakout (trend regime)
Entry: Close > RollHigh6 AND EMA50 > EMA200 AND RSI14 < 70
SL=2×ATR14, TP=5×ATR14 | Filter: garch_regime != "LOW", active hours
Typically achieves WR 35-45%, PF 1.3-1.8

### Pattern B — RSI Reversal (mean-reversion regime)
Entry long: RSI14 < 35 AND Close < EMA200*0.99
Entry short: RSI14 > 65 AND Close > EMA200*1.01
SL=1.5×ATR14, TP=3.5×ATR14 | Typically achieves WR 45-55%, PF 1.2-1.6

### Pattern C — EMA Crossover Momentum (trend regime)
Entry: fast EMA (20) crosses slow EMA (100), confirmed RSI direction
SL=2×ATR14, TP=4.5×ATR14 | Filter: trade only best UTC hours

### Pattern D — Bollinger Squeeze Breakout
Entry: Close breaks 2σ Bollinger band after low-ATR_pct period
SL=2×ATR14, TP=5×ATR14 | Filter: ATR_pct > 0.004

## ANTI-PATTERNS (NEVER DO THESE)
1. ❌ SL < 1×ATR — stops out on noise before TP is reached
2. ❌ TP/SL ratio < 2 — commission makes profitability mathematically impossible
3. ❌ Trading all 24 hours — worst hours have negative EV; restrict to best 8-14 UTC hours
4. ❌ No trend/regime filter — random entries into counter-trend trades kill Sharpe
5. ❌ Over-filtering to < 20 trades — insufficient sample; strategy won't survive OOS

## FUNCTION CONTRACT
The function receives `df` already processed by `compute_indicators_v2()`.
Available columns: Open, High, Low, Close, Volume, ATR14, RSI14, EMA50, EMA200,
RollHigh6, RollLow6, ATR_pct, hour, dow, ret, garch_h, garch_regime, size_mult.

The function **must**:
- Start with `df = df.copy()`
- Set `df["signal"]` to 1 (long), -1 (short), or 0 (flat) for every row
- Set `df["SL_dist"]` = stop-loss distance in absolute price units (use ATR14)
- Set `df["TP_dist"]` = take-profit distance (TP_dist / SL_dist ≥ 2.5)
- Return `df`
- Use only `numpy` (as `np`) and `pandas` (as `pd`) — both are pre-imported

## RESPONSE FORMAT
Return **exactly** these three fenced blocks in order — nothing else:

```json
{{
  "strategy_type": "<trend_following|mean_reversion|breakout|range_trading|momentum>",
  "strategy_name": "<descriptive name>",
  "sl_mult": <float, ATR multiple for SL, minimum 1.5>,
  "tp_mult": <float, ATR multiple for TP, minimum sl_mult * 2.5>,
  "active_hours": [<start 0-23>, <end 0-23>],
  "commission": 0.0004,
  "slippage":   0.0001,
  "risk_per_trade": 0.01,
  "rationale": "<one sentence: why this R:R beats commission given the expected win rate>"
}}
```

```python
def generate_signals_agent(df):
    df = df.copy()
    # ... implementation ...
    return df
```

```markdown
# Strategy Report: <strategy_name>

## Statistical Analysis Summary
[Key findings: Hurst, ACF, kurtosis, GARCH regimes, intraday patterns]

## Strategy Choice Rationale
[Why this type is optimal for these statistical properties]

## Commission Analysis
[Break-even WR at chosen R:R, expected actual WR, why the edge survives fees]

## Implementation Details
[Entry/exit logic, filters, position sizing]

## Risk Parameters
[SL/TP rationale with ATR multiples, active hours justification, expected N trades/year]

## Expected Edge
[Quantified: expected WR, PF, Sharpe based on historical data properties]
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
        df["RollHigh6"] = df["High"].rolling(6).max()
        df["RollLow6"]  = df["Low"].rolling(6).min()
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
        print("  [agent] No API key — using V5 defaults.")
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
