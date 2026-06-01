"""
/vibe router — Claude streaming proxy
POST /vibe/generate  → SSE stream: {type:"delta",text} … {type:"done",config:{},code:""}
"""
import atexit
import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.models import VibeGenerateRequest
from api.routers.brain import get_brain_context, sync_brain

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)
atexit.register(_executor.shutdown, wait=False)
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

# Auto-sync brain once per process if DB is empty
_brain_sync_lock = asyncio.Lock()
_brain_ready = False


async def _ensure_brain_ready() -> None:
    """Sync brain chapters from GitHub if none are in DuckDB yet."""
    global _brain_ready
    if _brain_ready:
        return
    async with _brain_sync_lock:
        if _brain_ready:
            return
        try:
            from api.db import get_conn
            count = get_conn().execute("SELECT COUNT(*) FROM brain_chunks").fetchone()[0]
            if count == 0:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, sync_brain)
        except Exception:
            pass
        _brain_ready = True

SYSTEM_PROMPT = """You are a professional quantitative trading strategy designer for the Pareto Terminal.
Generate ORIGINAL, custom trading strategies — not generic templates.

## Performance Targets (hard requirements)
- Sharpe ratio > 1.0 (primary objective)
- Max drawdown < 8% (hard constraint)
- Minimum 20 trades per year (statistical significance)

## Step 1 — Brief explanation (2-4 sentences)
Explain regime fit (use Hurst exponent), why DD < 8% is achievable with this approach,
and what gives this strategy its edge. Be specific about signal mechanics.

Regime mapping:
- Hurst > 0.55 → TREND (momentum, breakout, trend continuation — trade WITH the trend)
- Hurst < 0.45 → MEAN-REVERSION (fade extremes: BB touches, RSI <25/>75, VWAP deviation)
- Hurst ≈ 0.50 → VOLATILITY BREAKOUT (squeeze expansion, ATR spike entries)

## Step 2 — JSON config in a ```json block:
{
  "ticker": "BTC-USD",
  "timeframe": "1h",
  "sl_mult": 2.0,
  "tp_mult": 4.0,
  "active_hours": [6, 22],
  "risk_per_trade": 0.5,
  "direction": "ALL"
}

Risk management rules:
- risk_per_trade: 0.3–0.5% for volatile assets (ann_vol > 50%), 0.5–1.0% for moderate vol
- TP/SL ratio must be ≥ 2.0 (tp_mult ≥ 2 × sl_mult) for positive expectancy
- sl_mult 1.5–2.0 for mean-reversion, 2.5–3.5 for trend-following
- direction: "LONG" for bullish-trending, "SHORT" for bearish, "ALL" for ranging/symmetric

## Step 3 — Python agent_fn in a ```python block.

The function receives:
- df: DataFrame with columns Open, High, Low, Close, Volume, ATR14, RSI14, EMA50, EMA200,
  RollHigh6, RollLow6, garch_h, garch_regime (LOW/MED/HIGH), size_mult, ret, hour, dow
- ind: optional indicator helper — call ind("EMA", 20), ind("BB", 20, 2.0), ind("VWAP"),
  ind("ATR", 14), ind("MACD", 12, 26, 9), ind("STOCH", 14) etc.
  BB and MACD/STOCH return tuples: (upper, mid, lower) and (line, signal, hist) respectively.

The function MUST:
- Return df with columns: signal (1/−1/0), SL_dist, TP_dist (absolute price distances)
- Use .shift(1) on ALL indicator conditions to avoid lookahead bias
- Use only pandas/numpy (no external imports)
- Have at least 2 confirming conditions (primary signal + filter) to reduce false entries
- NOT use garch_regime/size_mult as per-bar entry signals (lookahead risk)

FORBIDDEN patterns (too generic, overfit easily):
- Simple RSI crossover through 50 alone
- Simple dual-EMA crossover alone (without volume/volatility filter)
- Fixed-percentage stops (always use ATR-based SL_dist/TP_dist)

RECOMMENDED patterns:
- Volume-confirmed breakout (price breaks N-bar high + volume > avg)
- Multi-indicator confluence (momentum + trend alignment + volatility filter)
- Mean-reversion with exhaustion signal (RSI extreme + volume declining)
- Volatility squeeze + momentum direction (BB width at low + momentum sign)

```python
import pandas as pd
import numpy as np

def agent_fn(df: pd.DataFrame, ind=None) -> pd.DataFrame:
    df = df.copy()
    # At least 2 confirming conditions for entry
    ema20 = ind("EMA", 20) if ind else df["EMA50"]
    # Example: primary + filter (use .shift(1) to avoid lookahead)
    df["signal"] = 0
    df["SL_dist"] = df["ATR14"] * 2.0   # absolute price distance
    df["TP_dist"] = df["ATR14"] * 4.0
    return df
```
"""

_MOCK_CODE = """\
import pandas as pd

def agent_fn(df: pd.DataFrame) -> pd.DataFrame:
    \"\"\"Momentum strategy — RSI crossover with EMA trend filter.\"\"\"
    df = df.copy()
    df["signal"] = 0
    long_cond = (
        (df["RSI14"].shift(1) < 50) & (df["RSI14"] >= 50) &
        (df["close"] > df["EMA20"])
    )
    short_cond = (
        (df["RSI14"].shift(1) > 50) & (df["RSI14"] <= 50) &
        (df["close"] < df["EMA20"])
    )
    df.loc[long_cond, "signal"] = 1
    df.loc[short_cond, "signal"] = -1
    df["SL_dist"] = df["ATR14"] * 2.0
    df["TP_dist"] = df["ATR14"] * 4.0
    return df\
"""


def _extract_config(text: str) -> dict:
    """Extract JSON config from Claude response text."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[^{}]*\"ticker\"[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _extract_code(text: str) -> str:
    """Extract Python agent_fn from Claude response text."""
    m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


async def _mock_stream(body: VibeGenerateRequest):
    """Fallback stream when ANTHROPIC_API_KEY is not set."""
    asset = body.asset or "BTC-USD"
    ticker = asset if "-USD" in asset else f"{asset}-USD"
    timeframe = body.timeframe or "1h"
    has_prompt = bool(body.prompt and body.prompt.strip())
    intro = (
        f"Analyzing your strategy idea for {asset} on {timeframe}…\n\n"
        "Based on your description I recommend a momentum approach with "
        "dynamic ATR-based stops. The configuration below uses a conservative "
        "risk-per-trade and filters activity to liquid trading hours.\n\n"
        if has_prompt else
        f"Analyzing historical statistics for {asset} on {timeframe}…\n\n"
        "Based on the asset statistics I recommend a mean-reversion approach — "
        "the asset shows elevated volatility relative to trend strength, suggesting "
        "reversion-to-mean strategies with tight ATR stops outperform pure momentum here.\n\n"
    )
    mock_text = (
        intro
        + "```json\n"
        "{\n"
        f'  "ticker": "{ticker}",\n'
        f'  "timeframe": "{timeframe}",\n'
        '  "sl_mult": 2.0,\n'
        '  "tp_mult": 4.0,\n'
        '  "active_hours": [6, 22],\n'
        '  "risk_per_trade": 1.0,\n'
        '  "direction": "ALL"\n'
        "}\n"
        "```\n\n"
        "```python\n"
        + _MOCK_CODE + "\n"
        "```"
    )
    chunk_size = 30
    for i in range(0, len(mock_text), chunk_size):
        chunk = mock_text[i : i + chunk_size]
        yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"
        await asyncio.sleep(0.04)

    config = _extract_config(mock_text)
    code = _extract_code(mock_text)
    yield f"data: {json.dumps({'type': 'done', 'config': config, 'code': code})}\n\n"


def _build_user_message(body: VibeGenerateRequest) -> str:
    parts = []
    if body.asset_stats:
        s = body.asset_stats
        stats_lines = [f"Asset: {body.asset}  Timeframe: {body.timeframe or '1h'}"]
        for key in ("cagr", "ann_vol", "sharpe", "sortino", "max_dd", "skew", "kurt", "var95", "cvar95", "best_day", "worst_day"):
            if key in s:
                stats_lines.append(f"  {key}: {s[key]}")
        parts.append("Historical statistics:\n" + "\n".join(stats_lines))
    else:
        parts.append(f"Asset: {body.asset}\nTimeframe: {body.timeframe or '1h'}")

    if body.quant_analysis:
        q = body.quant_analysis
        lines = ["Quantitative regime analysis:"]
        hurst = (q.get("hurst") or {})
        if hurst.get("hurst") is not None:
            lines.append(f"  Hurst exponent: {hurst['hurst']} ({hurst.get('regime', '?')})")
        stat = (q.get("stationarity") or {})
        if stat.get("adf_pvalue") is not None:
            verdict = "stationary" if stat.get("adf_stationary") else "non-stationary"
            lines.append(f"  ADF test: {verdict} (p={stat['adf_pvalue']})")
        vc = (q.get("var_cvar") or {})
        if vc.get("var") is not None:
            lines.append(f"  VaR 95%: {vc['var']}%  CVaR 95%: {vc.get('cvar')}%")
        roll = (q.get("rolling") or {})
        if roll.get("ann_vol") is not None:
            lines.append(f"  Rolling ann. vol: {roll['ann_vol']}%  Sharpe: {roll.get('sharpe')}")
        parts.append("\n".join(lines))

    if body.garch_forecast:
        g = body.garch_forecast
        if not g.get("garch_error"):
            lines = ["Volatility regime (GARCH):"]
            lines.append(f"  Current conditional vol: {g.get('current_vol_pct')}%/bar  Annualised: {g.get('ann_vol_pct')}%")
            fc = g.get("forecast_vol_pct") or {}
            lines.append(f"  Forecast: h1={fc.get('h1')}%  h5={fc.get('h5')}%  h22={fc.get('h22')}%")
            p = g.get("params") or {}
            lines.append(f"  Persistence: {p.get('persistence')}  Half-life: {p.get('half_life_bars')} bars")
            lb = (g.get("ljung_box") or {}).get("sq_returns") or {}
            arch_str = "ARCH effects present" if lb.get("significant") else "no significant ARCH effects"
            lines.append(f"  Squared-returns Ljung-Box: {arch_str} (p={lb.get('pvalue')})")
            parts.append("\n".join(lines))

    if body.prompt and body.prompt.strip():
        parts.append(f"Strategy idea: {body.prompt.strip()}")
    else:
        parts.append("No strategy idea provided — analyze all statistics above and suggest the best strategy.")
    return "\n\n".join(parts)


# ── Tool definitions for Claude ────────────────────────────────────────────────

_ANALYSIS_TOOLS = [
    {
        "name": "get_autocorrelation",
        "description": (
            "Compute return autocorrelation to detect momentum or mean-reversion patterns at various lags. "
            "Call this to understand if the asset has persistent trends or tends to mean-revert."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":   {"type": "string", "description": "Asset ticker e.g. BTC-USD"},
                "interval": {"type": "string", "enum": ["5m", "15m", "1h", "4h", "1d"],
                             "description": "Bar interval matching the strategy timeframe"},
            },
            "required": ["ticker", "interval"],
        },
    },
    {
        "name": "get_seasonality",
        "description": (
            "Get intraday (hour UTC) and day-of-week return/volume seasonality. "
            "Call this to find optimal active_hours and avoid low-liquidity periods."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":   {"type": "string"},
                "interval": {"type": "string", "enum": ["5m", "15m", "1h", "4h", "1d"]},
            },
            "required": ["ticker", "interval"],
        },
    },
    {
        "name": "get_volatility_cone",
        "description": (
            "Compare current ATR to its historical distribution. "
            "Call this to calibrate SL multiplier — elevated ATR needs wider stops."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":   {"type": "string"},
                "interval": {"type": "string", "enum": ["5m", "15m", "1h", "4h", "1d"]},
            },
            "required": ["ticker", "interval"],
        },
    },
    {
        "name": "get_return_distribution",
        "description": (
            "Analyze return distribution: skewness, excess kurtosis, fat tails, VaR. "
            "Call this to adjust risk_per_trade and SL width for asymmetric distributions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":   {"type": "string"},
                "interval": {"type": "string", "enum": ["5m", "15m", "1h", "4h", "1d"]},
            },
            "required": ["ticker", "interval"],
        },
    },
]


async def _execute_analysis_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch Claude tool call to internal analysis functions."""
    from api.routers.analysis import (
        get_autocorrelation, get_intraday_seasonality,
        get_volatility_cone, get_return_distribution,
    )
    ticker   = tool_input.get("ticker", "BTC-USD")
    interval = tool_input.get("interval", "1h")
    loop = asyncio.get_event_loop()
    dispatch = {
        "get_autocorrelation":     lambda: get_autocorrelation(ticker, interval),
        "get_seasonality":         lambda: get_intraday_seasonality(ticker, interval),
        "get_volatility_cone":     lambda: get_volatility_cone(ticker, interval),
        "get_return_distribution": lambda: get_return_distribution(ticker, interval),
    }
    fn = dispatch.get(tool_name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = await loop.run_in_executor(None, fn)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _claude_stream(body: VibeGenerateRequest):
    """Real Claude stream with tool-use analysis loop then strategy generation."""
    import anthropic as _anthropic

    if not _ANTHROPIC_KEY:
        yield f"data: {json.dumps({'type': 'delta', 'text': '[Error: ANTHROPIC_API_KEY not configured]'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': ''})}\n\n"
        return

    client = _anthropic.Anthropic(api_key=_ANTHROPIC_KEY, timeout=60.0)
    loop = asyncio.get_event_loop()

    await _ensure_brain_ready()
    brain_ctx = get_brain_context(body.prompt or "")
    # Cap brain context at ~4000 tokens (16000 chars) to avoid filling the context window
    _MAX_BRAIN_CHARS = 16_000
    if len(brain_ctx) > _MAX_BRAIN_CHARS:
        brain_ctx = brain_ctx[:_MAX_BRAIN_CHARS] + "\n…[brain context truncated]\n\n"
    effective_system = brain_ctx + SYSTEM_PROMPT if brain_ctx else SYSTEM_PROMPT

    messages = [{"role": "user", "content": _build_user_message(body)}]
    tools_used: list[str] = []

    # ── Phase 1: Tool-use analysis loop ──────────────────────────────────────
    MAX_TOOL_ROUNDS = 4
    for _round in range(MAX_TOOL_ROUNDS):
        try:
            response = await loop.run_in_executor(
                _executor,
                lambda msgs=messages: client.messages.create(
                    model="claude-opus-4-7",
                    max_tokens=512,
                    system=effective_system,
                    tools=_ANALYSIS_TOOLS,
                    tool_choice={"type": "auto"},
                    messages=msgs,
                )
            )
        except Exception as e:
            yield f"data: {json.dumps({'type': 'delta', 'text': f'[Analysis error: {e}]'})}\n\n"
            break

        if response.stop_reason != "tool_use":
            break

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        for block in tool_use_blocks:
            tools_used.append(block.name)
            yield f"data: {json.dumps({'type': 'analysis_start', 'tool': block.name})}\n\n"
            result_str = await _execute_analysis_tool(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })
            yield f"data: {json.dumps({'type': 'analysis_done', 'tool': block.name})}\n\n"

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # ── Phase 2: Strategy generation (streaming) ──────────────────────────────
    queue: asyncio.Queue = asyncio.Queue()
    full_text = ""

    def _run_stream():
        try:
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=4096,
                system=effective_system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    asyncio.run_coroutine_threadsafe(queue.put(("delta", text)), loop)
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(queue.put(("error", str(exc))), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

    loop.run_in_executor(_executor, _run_stream)

    while True:
        kind, val = await queue.get()
        if kind == "delta":
            full_text += val
            yield f"data: {json.dumps({'type': 'delta', 'text': val})}\n\n"
        elif kind == "error":
            yield f"data: {json.dumps({'type': 'delta', 'text': f'[Error: {val}]'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': '', 'tools_used': tools_used})}\n\n"
            break
        else:
            config = _extract_config(full_text)
            code   = _extract_code(full_text)
            yield f"data: {json.dumps({'type': 'done', 'config': config, 'code': code, 'tools_used': tools_used})}\n\n"
            break


@router.post("/generate")
async def vibe_generate(body: VibeGenerateRequest):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return StreamingResponse(_mock_stream(body), media_type="text/event-stream")

    async def generator():
        try:
            async with asyncio.timeout(90):  # 90s hard limit
                async for chunk in _claude_stream(body):
                    yield chunk
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'delta', 'text': '[Error: stream timeout after 90s]'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': ''})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'delta', 'text': f'[Error: {str(e)}]'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': ''})}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.post("/improve")
async def vibe_improve(body: dict):
    return {"status": "stub"}
