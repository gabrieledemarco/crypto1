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
    "commission": 0.0001,
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


def _build_context(asset: str = "BTC-USD") -> str:
    files = [
        ("Statistical Report", "REPORT.txt"),
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

## TASK
Analyse the {asset} statistical analysis results supplied by the user and:
1. Choose the optimal **strategy TYPE** based on the time-series properties.
2. Write a Python function `generate_signals_agent(df)` implementing that strategy.
3. Write a Markdown report explaining your analysis and choices.

## STRATEGY-TYPE SELECTION GUIDE
| Statistical signal | Recommended strategy |
|---|---|
| Hurst exponent > 0.55 | TREND FOLLOWING — EMA crossover, momentum breakout |
| Hurst exponent < 0.45 | MEAN REVERSION — Bollinger Bands, RSI reversal, Z-score |
| 0.45 ≤ Hurst ≤ 0.55 | BREAKOUT or RANGE TRADING |
| Positive ACF lag-1 | Strengthen trend case |
| Negative ACF lag-1 | Strengthen mean-reversion case |
| High kurtosis (> 5) | Widen SL to avoid fat-tail stop-outs |
| Strong intraday pattern | Restrict active_hours to the best window |
| Many LOW GARCH periods | Add GARCH regime filter |

## FUNCTION CONTRACT
The function receives `df` already processed by `compute_indicators_v2()`.
Available columns: Open, High, Low, Close, Volume, ATR14, RSI14, EMA50, EMA200,
RollHigh6, RollLow6, ATR_pct, hour, dow, ret, garch_h, garch_regime, size_mult.

The function **must**:
- Start with `df = df.copy()`
- Set `df["signal"]` to 1 (long), -1 (short), or 0 (flat) for every row
- Set `df["SL_dist"]` = stop-loss distance in absolute price units
- Set `df["TP_dist"]` = take-profit distance in absolute price units
- Return `df`
- Use only `numpy` (as `np`) and `pandas` (as `pd`) — both are pre-imported

## RESPONSE FORMAT
Return **exactly** these three fenced blocks in order — nothing else:

```json
{
  "strategy_type": "<trend_following|mean_reversion|breakout|range_trading|momentum>",
  "strategy_name": "<descriptive name>",
  "sl_mult": <float, ATR multiple for SL>,
  "tp_mult": <float, ATR multiple for TP>,
  "active_hours": [<start 0-23>, <end 0-23>],
  "commission": <float e.g. 0.0001>,
  "slippage":   <float e.g. 0.0001>,
  "risk_per_trade": <float e.g. 0.01>,
  "rationale": "<one sentence>"
}
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

## Implementation Details
[Entry/exit logic, filters, position sizing]

## Risk Parameters
[SL/TP rationale, active hours justification]

## Expected Edge
[Why this strategy should be profitable given the data]
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

def _call_openrouter(api_key: str, context: str, model: str = "", asset: str = "BTC-USD") -> tuple:
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


# ── Public entry point ────────────────────────────────────────────────────────

def run_agent(
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
    asset: str = "BTC-USD",
) -> tuple:
    """
    Returns (config: dict, code: str, report: str).
    Priority: Anthropic → OpenRouter → V5 defaults.
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

    if ant:
        try:
            return _call_anthropic(ant, ctx, asset=asset)
        except Exception as exc:
            print(f"  [agent] Anthropic error: {exc}")
            if not ort:
                print("  [agent] Falling back to V5 defaults.")
                return V5_DEFAULT_CONFIG.copy(), DEFAULT_CODE, DEFAULT_REPORT
            print("  [agent] Retrying via OpenRouter...")

    try:
        return _call_openrouter(ort, ctx, model=openrouter_model, asset=asset)
    except Exception as exc:
        print(f"  [agent] OpenRouter error: {exc}")
        print("  [agent] Falling back to V5 defaults.")
        return V5_DEFAULT_CONFIG.copy(), DEFAULT_CODE, DEFAULT_REPORT

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
