"""
/vibe/generate-v2 — Orchestrated 3-agent strategy pipeline (SSE)

Agents:
  1. Orchestrator (claude-opus-4-5): analyzes market context -> strategy brief
  2. Generator (claude-sonnet-4-6): implements brief -> code + config
  3. Evaluator (claude-opus-4-5): 6-dimension expert scorecard
  4. Orchestrator synthesis: promote / iterate (max 3) / reject decision

POST /vibe/generate-v2  -> SSE stream of phase events
"""
import asyncio
import json
import logging
import re
import uuid
from asyncio import AbstractEventLoop
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator

import os

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.db import get_conn
from api.limiter import limiter

log = logging.getLogger("vibe_v2")
router = APIRouter()

_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

_MODEL_ORCHESTRATOR = "claude-opus-4-8"
_MODEL_GENERATOR    = "claude-sonnet-4-6"
_MODEL_EVALUATOR    = "claude-opus-4-8"

_executor = ThreadPoolExecutor(max_workers=2)

MAX_ATTEMPTS = 3

# ── Models ─────────────────────────────────────────────────────────────────────

class VibeV2Request(BaseModel):
    ticker: str = "BTC-USD"
    asset: str = "BTC-USD"   # frontend alias for ticker
    timeframe: str = "1h"
    period: str = "2y"
    prompt: str = ""          # user's strategy idea (optional)
    asset_stats: dict = {}
    quant_analysis: dict = {}
    garch_forecast: dict = {}

    @property
    def resolved_ticker(self) -> str:
        return self.ticker if self.ticker != "BTC-USD" else self.asset


# ── System Prompts ─────────────────────────────────────────────────────────────

ORCHESTRATOR_SYSTEM = """\
You are a Senior Quantitative Trading Systems Architect. Your job is to analyze market data and design a precise strategy brief for the code generator.

Analyze the provided market context and output a JSON brief in a ```json block:
{
  "regime_assessment": "<1-2 sentences: Hurst value + what it implies, GARCH persistence + what it implies>",
  "dominant_pattern": "<most exploitable pattern found in seasonality/autocorrelation/vol cone>",
  "strategy_type": "trend_following|mean_reversion|breakout|volatility_expansion",
  "entry_logic": "<specific entry logic: which indicators, which crossover/threshold, in what order>",
  "recommended_indicators": ["<e.g. BB(20,2.0) for band touches>", "<e.g. RSI(14) < 30 as confirmation>"],
  "entry_filters": ["<filter 1: e.g. only trade when garch_h < median vol>", "<filter 2>"],
  "risk_params": {
    "sl_mult": 2.0,
    "tp_mult": 4.0,
    "active_hours": [6, 22],
    "direction": "LONG|SHORT|ALL",
    "risk_per_trade": 0.5
  },
  "patterns_to_avoid": ["<e.g. momentum signals in ranging market>"],
  "edge_hypothesis": "<1 sentence: why this edge should persist>",
  "confidence": "high|medium|low"
}

Rules:
- All indicator parameters must be DATA-DRIVEN (based on the autocorrelation lags, seasonality peaks, vol cone provided)
- If Hurst > 0.55: trend_following or breakout only
- If Hurst < 0.45: mean_reversion only
- If 0.45 <= Hurst <= 0.55: volatility_expansion or hybrid
- sl_mult must be proportional to current vol regime (higher vol -> wider stops)
- active_hours must match the seasonality data (use hours with highest drift/volume)
"""

ORCHESTRATOR_SYNTHESIS_SYSTEM = """\
You are a Senior Quantitative Trading Systems Architect making a final decision on a generated strategy.

You have:
1. The strategy brief you originally designed
2. The backtest metrics
3. The expert evaluator's scorecard

Decide and respond in JSON in a ```json block:
{
  "decision": "promote|iterate|reject",
  "rationale": "<2-3 sentences>",
  "refined_brief_changes": {
    "<field>": "<new value with specific justification>"
  }
}

Decision rules:
- "promote": Sharpe >= 0.8 AND DD <= 25% AND evaluator overall_score >= 3.0 AND no fatal_flaws
- "iterate": Sharpe >= 0 AND evaluator has specific_improvements AND attempt < max_attempts
- "reject": Sharpe < 0 OR evaluator fatal_flaws present AND not fixable in one iteration

For "iterate", refined_brief_changes must address EVERY weakness from evaluator.specific_improvements with a concrete change.
"""

GENERATOR_SYSTEM = """\
You are an expert quantitative trading strategy developer. Implement the strategy brief EXACTLY as specified by the architecture agent. Do not generalize, simplify, or substitute.

Output format:
Step 1 -- Rationale (2-4 sentences): how your implementation maps to the brief's edge_hypothesis.
Step 2 -- JSON config in ```json block
Step 3 -- Python code in ```python block

## Execution environment — READ CAREFULLY
`pd` (pandas) and `np` (numpy) are pre-injected into the namespace.
DO NOT write any import statements — `import pandas as pd` will crash the executor.
DO NOT use type annotations on the function signature — `pd.DataFrame` in annotations also crashes.

## Function signature (MANDATORY — no annotations)
def agent_fn(df, ind):

`df` is a pandas DataFrame. `ind` is a callable passed as the second argument by the engine.
Use `ind` for ALL custom indicators. Pre-computed df columns are available directly.

## Pre-computed df columns
Open, High, Low, Close, Volume, ATR14, RSI14, EMA50, EMA200, RollHigh6, RollLow6,
garch_h, garch_regime (LOW/MED/HIGH), size_mult, ret, hour, dow

## ind() usage
ind("EMA", N)            -> pd.Series
ind("RSI", N)            -> pd.Series
ind("BB", 20, 2.0)       -> (upper, mid, lower) tuple of pd.Series
ind("MACD", 12, 26, 9)   -> (line, signal, hist) tuple
ind("STOCH", 14)         -> (K, D) tuple
ind("ATR", N)            -> pd.Series
ind("VWAP")              -> pd.Series

## Strict rules
- Function MUST be named agent_fn and accept exactly (df, ind) — no type annotations
- .shift(1) on ALL signal conditions (no lookahead bias)
- At minimum 2 independent entry conditions
- ATR-based SL_dist and TP_dist only (use df["ATR14"] or ind("ATR", N))
- NO import statements of any kind
- Return df with columns: signal (1=LONG, -1=SHORT, 0=flat), SL_dist, TP_dist
- Implement the brief's entry_logic and entry_filters exactly

## Minimal correct example
```python
def agent_fn(df, ind):
    ema_fast = ind("EMA", 20)
    ema_slow = ind("EMA", 50)
    rsi = ind("RSI", 14)
    long_cond = (ema_fast.shift(1) > ema_slow.shift(1)) & (rsi.shift(1) < 60)
    short_cond = (ema_fast.shift(1) < ema_slow.shift(1)) & (rsi.shift(1) > 40)
    signal = long_cond.astype(int) - short_cond.astype(int)
    return df.assign(signal=signal, SL_dist=df["ATR14"] * 2.0, TP_dist=df["ATR14"] * 4.0)
```
"""

EVALUATOR_SYSTEM = """\
You are a Senior Quantitative Researcher and Portfolio Manager with 20 years of live trading experience. Evaluate this trading strategy with professional rigor.

## Evaluation Dimensions (score 1-5 each)

1. **Alpha Source** (1-5): Is the exploited inefficiency real (behavioral/structural) or spurious (data-mined)? Does it have economic rationale?

2. **Signal Logic** (1-5): Are entry conditions independent and non-redundant? Too many conditions = overfitting. Does the code actually implement the stated edge?

3. **Risk Management** (1-5): Is SL/TP appropriate for this asset's vol profile? Position sizing vs GARCH vol? Worst-case single-trade loss?

4. **Regime Sensitivity** (1-5): What market conditions BREAK this strategy? Is there an implicit regime assumption? What happens when Hurst shifts?

5. **Statistical Robustness** (1-5): Are n_trades sufficient (< 30 = suspect)? IS vs OOS degradation (> 50% = suspect)? Sharpe consistency?

6. **Implementation Quality** (1-5): Lookahead bias audit (any condition that could peek at future bars?). Code clarity. Edge dilution from slippage?

## Required output -- respond ONLY with this JSON in a ```json block:
Set overall_score = average of the 6 dimension scores (so it is also on the 1.0-5.0 scale).
{
  "scores": {
    "alpha_source": 3,
    "signal_logic": 3,
    "risk_management": 3,
    "regime_sensitivity": 3,
    "statistical_robustness": 3,
    "implementation_quality": 3
  },
  "overall_score": 3.0,
  "strengths": ["<specific strength>", "<specific strength>"],
  "weaknesses": ["<specific weakness with reference to code/metrics>"],
  "specific_improvements": ["<concrete change to make>"],
  "fatal_flaws": [],
  "verdict": "promote|iterate|reject",
  "verdict_rationale": "<2-3 sentences>"
}
"""


# ── Context builder ────────────────────────────────────────────────────────────

def _build_context(body: VibeV2Request) -> str:
    """Build a comprehensive market context string for the orchestrator and evaluator."""
    stats = body.asset_stats
    quant = body.quant_analysis
    garch = body.garch_forecast

    def _fmt(val, fmt=".2f"):
        if val is None or val == "N/A":
            return "N/A"
        try:
            return format(float(val), fmt)
        except (TypeError, ValueError):
            return str(val)

    hurst_data = quant.get("hurst", {}) or {}
    stat_data = quant.get("stationarity", {}) or {}
    garch_fc = garch.get("forecast_vol_pct", {}) or {}
    garch_params = garch.get("params", {}) or {}
    lb_data = (garch.get("ljung_box", {}) or {}).get("sq_returns", {}) or {}

    idea_section = f"## User Strategy Idea\n{body.prompt}\n\n" if body.prompt.strip() else ""
    return (
        idea_section
        + f"ASSET: {body.resolved_ticker} | TIMEFRAME: {body.timeframe} | PERIOD: {body.period}\n\n"
        f"## Market Statistics\n"
        f"CAGR: {_fmt(stats.get('cagr'), '.1f')}% | Ann Vol: {_fmt(stats.get('ann_vol'), '.1f')}%\n"
        f"Sharpe: {_fmt(stats.get('sharpe'), '.2f')} | Sortino: {_fmt(stats.get('sortino'), '.2f')}\n"
        f"Max DD: {_fmt(stats.get('max_dd'), '.1f')}% | Skew: {_fmt(stats.get('skew'), '.2f')}\n"
        f"VaR 95%: {_fmt(stats.get('var95'), '.2f')}% | CVaR 95%: {_fmt(stats.get('cvar95'), '.2f')}%\n"
        f"Best day: {_fmt(stats.get('best_day'), '.1f')}% | Worst day: {_fmt(stats.get('worst_day'), '.1f')}%\n\n"
        f"## Regime Analysis\n"
        f"Hurst: {_fmt(hurst_data.get('hurst'), '.3f')} -> {hurst_data.get('regime', 'N/A')}\n"
        f"ADF stationary: {stat_data.get('adf_stationary', 'N/A')} "
        f"(p={_fmt(stat_data.get('adf_pvalue'), '.4f')})\n\n"
        f"## GARCH Volatility\n"
        f"Current vol: {_fmt(garch.get('current_vol_pct'), '.3f')}% | "
        f"Ann vol: {_fmt(garch.get('ann_vol_pct'), '.1f')}%\n"
        f"Forecasts: 1h={_fmt(garch_fc.get('h1'), '.3f')}% "
        f"5h={_fmt(garch_fc.get('h5'), '.3f')}% "
        f"22h={_fmt(garch_fc.get('h22'), '.3f')}%\n"
        f"Persistence (alpha+beta): {_fmt(garch_params.get('persistence'), '.3f')}\n"
        f"Half-life: {garch_params.get('half_life_bars', 'N/A')} bars\n"
        f"ARCH effects significant: {lb_data.get('significant', 'N/A')}"
    )


# ── JSON / code extractors ─────────────────────────────────────────────────────

def _extract_json_block(text: str) -> dict:
    """Extract first JSON object from a ```json block in text."""
    for m in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
    # Fallback: find largest {...} block
    best: dict = {}
    for m in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", text, re.DOTALL):
        try:
            obj = json.loads(m.group(0))
            if len(obj) > len(best):
                best = obj
        except json.JSONDecodeError:
            continue
    return best


def _extract_code(text: str) -> str:
    """Extract Python code from ```python block."""
    m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_config(text: str) -> dict:
    """Extract the JSON config block (must contain sl_mult or ticker) from generator output."""
    for m in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            if any(k in obj for k in ("sl_mult", "ticker", "timeframe")):
                return obj
        except json.JSONDecodeError:
            continue
    return {}


# ── Agent callers ──────────────────────────────────────────────────────────────

async def _call_orchestrator_brief(
    context: str, client: AsyncAnthropic
) -> tuple[str, dict]:
    """Call orchestrator to design strategy brief. Returns (raw_text, parsed_brief)."""
    response = await client.messages.create(
        model=_MODEL_ORCHESTRATOR,
        max_tokens=1500,
        system=ORCHESTRATOR_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Analyze this market context and design a strategy brief:\n\n{context}",
        }],
    )
    raw = response.content[0].text
    brief = _extract_json_block(raw)
    return raw, brief


async def _stream_generator(
    brief: dict,
    context: str,
    attempt: int,
    client: AsyncAnthropic,
) -> AsyncIterator[tuple[str, str]]:
    """
    Stream generator output.
    Yields (event_type, value): event_type='chunk' for text, 'done' with full text.
    """
    prompt = (
        f"Implement this strategy brief exactly:\n\n"
        f"```json\n{json.dumps(brief, indent=2)}\n```\n\n"
        f"Market context:\n{context}\n\n"
        f"Attempt {attempt}/{MAX_ATTEMPTS}. Output Step 1 (rationale), "
        f"Step 2 (JSON config), Step 3 (Python agent_fn)."
    )

    full_text = ""
    async with client.messages.stream(
        model=_MODEL_GENERATOR,
        max_tokens=3000,
        system=GENERATOR_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for chunk in stream.text_stream:
            full_text += chunk
            yield ("chunk", chunk)

    yield ("done", full_text)


async def _call_evaluator(
    code: str,
    config: dict,
    metrics: dict,
    context: str,
    brief: dict,
    client: AsyncAnthropic,
) -> dict:
    """Call evaluator for deep assessment. Returns parsed evaluation dict."""
    is_m = metrics.get("is_metrics", {})
    oos_m = metrics.get("oos_metrics", {})

    def _mval(m: dict, *keys):
        for k in keys:
            v = m.get(k)
            if v is not None:
                return v
        return "N/A"

    prompt = (
        f"Evaluate this trading strategy:\n\n"
        f"## Strategy Brief (what was requested)\n```json\n{json.dumps(brief, indent=2)}\n```\n\n"
        f"## Implementation Code\n```python\n{code}\n```\n\n"
        f"## Config\n```json\n{json.dumps(config, indent=2)}\n```\n\n"
        f"## Backtest Metrics (In-Sample)\n"
        f"Sharpe: {_mval(is_m, 'sharpe_ratio', 'sharpe')}\n"
        f"Max DD: {_mval(is_m, 'max_drawdown_pct', 'max_dd')}%\n"
        f"N Trades: {_mval(is_m, 'n_trades')}\n"
        f"Win Rate: {_mval(is_m, 'win_rate_pct')}%\n\n"
        f"## Backtest Metrics (Out-of-Sample, last 20%)\n"
        f"Sharpe: {_mval(oos_m, 'sharpe_ratio', 'sharpe')}\n"
        f"Max DD: {_mval(oos_m, 'max_drawdown_pct', 'max_dd')}%\n"
        f"N Trades: {_mval(oos_m, 'n_trades')}\n\n"
        f"## Market Context\n{context}\n\n"
        "Provide your expert evaluation as the required JSON."
    )

    response = await client.messages.create(
        model=_MODEL_EVALUATOR,
        max_tokens=1200,
        system=EVALUATOR_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    return _extract_json_block(raw)


async def _call_orchestrator_synthesis(
    brief: dict,
    metrics: dict,
    evaluation: dict,
    attempt: int,
    client: AsyncAnthropic,
) -> dict:
    """Call orchestrator Phase B to decide promote/iterate/reject."""
    is_m = metrics.get("is_metrics", {})

    def _mval(m: dict, *keys):
        for k in keys:
            v = m.get(k)
            if v is not None:
                return v
        return "N/A"

    prompt = (
        f"## Original Brief\n```json\n{json.dumps(brief, indent=2)}\n```\n\n"
        f"## Backtest Results\n"
        f"IS Sharpe: {_mval(is_m, 'sharpe_ratio', 'sharpe')}\n"
        f"IS Max DD: {_mval(is_m, 'max_drawdown_pct', 'max_dd')}%\n"
        f"IS N Trades: {_mval(is_m, 'n_trades')}\n\n"
        f"## Evaluator Scorecard\n```json\n{json.dumps(evaluation, indent=2)}\n```\n\n"
        f"This was attempt {attempt}/{MAX_ATTEMPTS}. Decide: promote, iterate, or reject."
    )

    response = await client.messages.create(
        model=_MODEL_ORCHESTRATOR,
        max_tokens=800,
        system=ORCHESTRATOR_SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    return _extract_json_block(raw)


# ── Backtest (sync, runs in thread) ───────────────────────────────────────────

def _run_backtest_sync(
    code: str, config: dict, ticker: str, timeframe: str, period: str
) -> dict:
    """Fetch data, compute indicators, run IS + OOS backtest. Returns metrics dict."""
    from engine.providers.ccxt_client import is_crypto_ticker, fetch as ccxt_fetch
    from engine.providers.yfinance_client import fetch as yf_fetch
    from engine.strategy_core import compute_indicators_v2
    from engine.backtest import run_versions, INITIAL_CAPITAL
    from engine.safe_exec import safe_exec_strategy

    # Fetch OHLCV
    df_raw = None
    try:
        if is_crypto_ticker(ticker):
            df_raw = ccxt_fetch(ticker, period=period, interval=timeframe)
    except Exception:
        pass

    if df_raw is None or (hasattr(df_raw, "empty") and df_raw.empty):
        df_raw = yf_fetch(ticker, period=period, interval=timeframe)

    if df_raw is None or df_raw.empty:
        raise ValueError(f"No data returned for {ticker}/{timeframe}")

    # Compute indicators (includes GARCH)
    df_ind = compute_indicators_v2(df_raw, fit_garch=True)

    # Build engine config
    risk = float(config.get("risk_per_trade", 0.5))
    if risk > 0.1:
        risk /= 100.0

    cfg = {
        "sl_mult": float(config.get("sl_mult", 2.0)),
        "tp_mult": float(config.get("tp_mult", 4.0)),
        "active_hours": list(config.get("active_hours", [6, 22])),
        "commission_pips": 1.0,
        "slippage_pips": 0.5,
        "leverage": 1.0,
        "risk_per_trade": risk,
        "direction": config.get("direction", "ALL"),
        "max_positions": 1,
        "cooldown_bars": 0,
        "initial_capital": INITIAL_CAPITAL,
    }

    # Execute strategy code safely
    safe_exec_error_msg: str | None = None
    if code:
        try:
            ns = safe_exec_strategy(code, strategy_id="vibe_v2")
            if "agent_fn" in ns:
                cfg["agent_fn"] = ns["agent_fn"]
            else:
                safe_exec_error_msg = "agent_fn not found in executed code"
        except Exception as exc:
            safe_exec_error_msg = str(exc)
            log.warning("safe_exec failed: %s", exc)

    # IS backtest (full data)
    versions = run_versions(df_ind, cfg, direction=cfg["direction"])
    pref_keys = ["V_Agent", "V4 +GARCH+Costi", "V2 +Costi", "V1 Base"]
    best_key = next(
        (k for k in pref_keys if k in versions and "metrics" in versions[k]), None
    )
    if not best_key and versions:
        best_key = next(iter(versions))

    is_metrics = versions.get(best_key, {}).get("metrics", {}) if best_key else {}

    # Sample equity curve (up to 100 points)
    equity_sample: list = []
    if best_key:
        bt_result = versions.get(best_key, {}).get("result") or {}
        equity = bt_result.get("equity")
        if equity is not None and len(equity) > 0:
            step = max(1, len(equity) // 100)
            equity_sample = [round(float(v), 2) for v in equity[::step]]

    # OOS backtest: last 20% of data
    oos_metrics: dict = {}
    n_oos = len(df_ind) // 5
    if n_oos >= 80 and best_key:
        try:
            df_oos = df_ind.iloc[-n_oos:]
            oos_cfg = dict(cfg)
            v_oos = run_versions(df_oos, oos_cfg, direction=cfg["direction"])
            oos_metrics = v_oos.get(best_key, {}).get("metrics", {})
        except Exception as exc:
            log.warning("OOS backtest failed: %s", exc)

    return {
        "is_metrics": is_metrics,
        "oos_metrics": oos_metrics,
        "equity_sample": equity_sample,
        "best_version": best_key,
        "agent_fn_loaded": "agent_fn" in cfg,
        "safe_exec_error": safe_exec_error_msg,
    }


# ── DB save ────────────────────────────────────────────────────────────────────

async def _save_strategy(
    ticker: str,
    timeframe: str,
    code: str,
    config: dict,
    metrics: dict,
    evaluation: dict,
    verdict: str,
) -> str:
    """Save promoted strategy to DB. Returns strategy_id."""
    loop = asyncio.get_event_loop()

    def _do_save() -> str:
        conn = get_conn()
        sid = uuid.uuid4().hex[:8]
        is_m = metrics.get("is_metrics", {})
        oos_m = metrics.get("oos_metrics", {})

        def _mval(m: dict, *keys):
            for k in keys:
                v = m.get(k)
                if v is not None:
                    return v
            return 0

        cfg_save = dict(config)
        cfg_save["pipeline"] = "vibe_v2"
        cfg_save["perf"] = {
            "sharpe": float(_mval(is_m, "sharpe_ratio", "sharpe") or 0),
            "dd": float(_mval(is_m, "max_drawdown_pct", "max_dd") or 0),
            "n_trades": int(_mval(is_m, "n_trades") or 0),
            "win_rate": float(_mval(is_m, "win_rate_pct") or 0),
        }
        if oos_m:
            cfg_save["perf"]["oos_sharpe"] = float(
                _mval(oos_m, "sharpe_ratio", "sharpe") or 0
            )
        cfg_save["evaluation"] = {
            "overall_score": evaluation.get("overall_score"),
            "verdict": evaluation.get("verdict"),
            "strengths": evaluation.get("strengths", []),
            "weaknesses": evaluation.get("weaknesses", []),
        }
        status = "live" if verdict == "promote" else "research"
        name = f"vibev2_{verdict}_{ticker.replace('-', '_')}_{timeframe}_{sid}"
        conn.execute(
            "INSERT INTO strategies (id,name,strategy_type,config,code,status) VALUES (?,?,?,?,?,?)",
            [sid, name, "vibe_v2", json.dumps(cfg_save), code, status],
        )
        return sid

    return await loop.run_in_executor(_executor, _do_save)


# ── SSE endpoint ───────────────────────────────────────────────────────────────

@router.post("/generate-v2")
@limiter.limit("3/minute")
async def generate_v2(request: Request, body: VibeV2Request):
    """SSE endpoint: orchestrated 3-agent strategy generation pipeline."""

    async def event_stream():
        if not _ANTHROPIC_KEY:
            yield f"data: {json.dumps({'phase': 'error', 'msg': '[ANTHROPIC_API_KEY not set — configure it in Railway environment variables]'})}\n\n"
            return
        client = AsyncAnthropic(api_key=_ANTHROPIC_KEY)
        loop: AbstractEventLoop = asyncio.get_event_loop()

        def _sse(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            # ── 1. Build market context ────────────────────────────────────────
            context = _build_context(body)

            # ── 2. Orchestrator: design brief ──────────────────────────────────
            yield _sse({"phase": "orchestrating", "pct": 10, "msg": "Analyzing market context..."})

            brief_raw, brief = await _call_orchestrator_brief(context, client)

            # Stream orchestrator text as brief_chunk events
            for line in brief_raw.splitlines(keepends=True):
                yield _sse({"phase": "brief_chunk", "text": line})

            yield _sse({"phase": "brief_done", "brief": brief})

            if not brief:
                yield _sse({"phase": "error", "msg": "Orchestrator failed to produce a valid brief"})
                return

            # ── 3. Iteration loop ──────────────────────────────────────────────
            current_brief = brief
            # Track best attempt so we can always save something at the end
            last_code: str = ""
            last_config: dict = {}
            last_bt_metrics: dict = {"is_metrics": {}, "oos_metrics": {}, "equity_sample": []}
            last_evaluation: dict = {}

            for attempt in range(1, MAX_ATTEMPTS + 1):
                pct_gen = 30 + (attempt - 1) * 5
                yield _sse({
                    "phase": "generating",
                    "pct": pct_gen,
                    "attempt": attempt,
                    "msg": f"Generating strategy (attempt {attempt}/{MAX_ATTEMPTS})...",
                })

                # ── 3a. Stream generator ───────────────────────────────────────
                full_generator_text = ""
                async for event_type, value in _stream_generator(
                    current_brief, context, attempt, client
                ):
                    if event_type == "chunk":
                        yield _sse({"phase": "code_chunk", "text": value})
                    else:
                        full_generator_text = value

                code = _extract_code(full_generator_text)
                config = _extract_config(full_generator_text)

                # Apply risk params from brief if config is sparse
                if not config:
                    rp = current_brief.get("risk_params", {}) or {}
                    config = {
                        "ticker": body.resolved_ticker,
                        "timeframe": body.timeframe,
                        "sl_mult": rp.get("sl_mult", 2.0),
                        "tp_mult": rp.get("tp_mult", 4.0),
                        "active_hours": rp.get("active_hours", [6, 22]),
                        "direction": rp.get("direction", "ALL"),
                        "risk_per_trade": rp.get("risk_per_trade", 0.5),
                    }
                else:
                    config.setdefault("ticker", body.resolved_ticker)
                    config.setdefault("timeframe", body.timeframe)

                if not code:
                    msg = f"Generator produced no code on attempt {attempt}"
                    log.warning(msg)
                    if attempt < MAX_ATTEMPTS:
                        yield _sse({"phase": "warn", "msg": msg})
                        continue
                    break

                # ── 3b. Run backtest in thread ─────────────────────────────────
                yield _sse({"phase": "backtesting", "pct": 60, "msg": "Running backtest..."})

                try:
                    bt_metrics = await loop.run_in_executor(
                        _executor,
                        _run_backtest_sync,
                        code,
                        config,
                        body.resolved_ticker,
                        body.timeframe,
                        body.period,
                    )
                    yield _sse({"phase": "backtest_result", "metrics": bt_metrics, "config": config})
                    # Surface safe_exec / agent_fn load errors immediately
                    if bt_metrics.get("safe_exec_error"):
                        yield _sse({
                            "phase": "warn",
                            "msg": f"agent_fn exec error: {bt_metrics['safe_exec_error'][:120]}",
                        })
                    if not bt_metrics.get("agent_fn_loaded") and code:
                        yield _sse({
                            "phase": "warn",
                            "msg": f"agent_fn not loaded — backtest ran {bt_metrics.get('best_version', 'fallback')} signals",
                        })
                except Exception as exc:
                    log.warning("Backtest failed (attempt %d): %s", attempt, exc)
                    bt_metrics = {"is_metrics": {}, "oos_metrics": {}, "equity_sample": []}
                    yield _sse({
                        "phase": "backtest_result",
                        "metrics": bt_metrics,
                        "msg": f"Backtest error: {str(exc)[:100]}",
                    })

                # Track best attempt state
                last_code = code
                last_config = config
                last_bt_metrics = bt_metrics


                # ── 3c. Evaluator ──────────────────────────────────────────────
                yield _sse({"phase": "evaluating", "pct": 75, "msg": "Expert evaluation..."})

                try:
                    evaluation = await _call_evaluator(
                        code, config, bt_metrics, context, current_brief, client
                    )
                except Exception as exc:
                    log.warning("Evaluator failed (attempt %d): %s", attempt, exc)
                    evaluation = {
                        "scores": {},
                        "overall_score": 0,
                        "strengths": [],
                        "weaknesses": [],
                        "specific_improvements": [],
                        "fatal_flaws": [],
                        "verdict": "iterate",
                        "verdict_rationale": f"Evaluation error: {exc}",
                    }

                yield _sse({"phase": "evaluation", "result": evaluation})
                last_evaluation = evaluation

                # ── 3d. Orchestrator synthesis ─────────────────────────────────
                try:
                    synthesis = await _call_orchestrator_synthesis(
                        current_brief, bt_metrics, evaluation, attempt, client
                    )
                except Exception as exc:
                    log.warning("Synthesis failed (attempt %d): %s", attempt, exc)
                    synthesis = {
                        "decision": "iterate",
                        "rationale": str(exc),
                        "refined_brief_changes": {},
                    }

                decision = synthesis.get("decision", "iterate")
                yield _sse({
                    "phase": "decision",
                    "pct": 90,
                    "verdict": decision,
                    "msg": synthesis.get("rationale", ""),
                })

                # ── 3e. Act on decision ────────────────────────────────────────
                if decision == "promote":
                    sid = None
                    try:
                        sid = await _save_strategy(
                            body.resolved_ticker, body.timeframe,
                            code, config, bt_metrics, evaluation, "promote",
                        )
                    except Exception as exc:
                        log.warning("DB save failed: %s", exc)

                    is_m = bt_metrics.get("is_metrics", {})
                    sharpe = float(
                        is_m.get("sharpe_ratio", is_m.get("sharpe", 0)) or 0
                    )
                    yield _sse({
                        "phase": "done",
                        "pct": 100,
                        "strategy_id": sid,
                        "name": f"{body.resolved_ticker}_v2_{body.timeframe}",
                        "sharpe": round(sharpe, 3),
                        "overall_score": evaluation.get("overall_score", 0),
                        "attempts": attempt,
                    })
                    return

                elif decision == "reject":
                    # Save as research (rejected) and return done rather than error
                    sid = None
                    try:
                        sid = await _save_strategy(
                            body.resolved_ticker, body.timeframe,
                            code, config, bt_metrics, evaluation, "reject",
                        )
                    except Exception as exc:
                        log.warning("DB save on reject failed: %s", exc)
                    is_m = bt_metrics.get("is_metrics", {})
                    sharpe = float(is_m.get("sharpe_ratio", is_m.get("sharpe", 0)) or 0)
                    yield _sse({
                        "phase": "done",
                        "pct": 100,
                        "strategy_id": sid,
                        "name": f"{body.resolved_ticker}_v2_{body.timeframe}_rejected",
                        "sharpe": round(sharpe, 3),
                        "overall_score": evaluation.get("overall_score", 0),
                        "attempts": attempt,
                        "note": f"Rejected: {synthesis.get('rationale', 'fatal flaws')[:120]}",
                    })
                    return

                else:
                    # iterate: merge refined brief changes and loop
                    if attempt < MAX_ATTEMPTS:
                        changes = synthesis.get("refined_brief_changes", {}) or {}
                        if changes:
                            updated = dict(current_brief)
                            for field, value in changes.items():
                                if field == "risk_params" and isinstance(value, dict):
                                    updated["risk_params"] = {
                                        **(updated.get("risk_params") or {}),
                                        **value,
                                    }
                                else:
                                    updated[field] = value
                            current_brief = updated
                        yield _sse({
                            "phase": "iteration",
                            "attempt": attempt + 1,
                            "pct": 35,
                            "msg": (
                                f"Refining strategy (attempt {attempt + 1}/{MAX_ATTEMPTS})..."
                            ),
                        })

            # All attempts exhausted — save best result as research grade
            sid = None
            if last_code:
                try:
                    sid = await _save_strategy(
                        body.resolved_ticker, body.timeframe,
                        last_code, last_config, last_bt_metrics, last_evaluation, "iterate",
                    )
                except Exception as exc:
                    log.warning("DB save on exhaust failed: %s", exc)
            is_m = last_bt_metrics.get("is_metrics", {})
            sharpe = float(is_m.get("sharpe_ratio", is_m.get("sharpe", 0)) or 0)
            yield _sse({
                "phase": "done",
                "pct": 100,
                "strategy_id": sid,
                "name": f"{body.resolved_ticker}_v2_{body.timeframe}_research",
                "sharpe": round(sharpe, 3),
                "overall_score": last_evaluation.get("overall_score", 0),
                "attempts": MAX_ATTEMPTS,
                "note": f"Research grade — best of {MAX_ATTEMPTS} attempts (promote threshold not met)",
            })

        except Exception as exc:
            log.exception("vibe-v2 pipeline error")
            yield _sse({"phase": "error", "msg": str(exc)[:200]})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
