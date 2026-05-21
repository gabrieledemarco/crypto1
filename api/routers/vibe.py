"""
/vibe router — Claude streaming proxy
POST /vibe/generate  → SSE stream: {type:"delta",text} … {type:"done",config:{},code:""}
"""
import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.models import VibeGenerateRequest

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=2)

SYSTEM_PROMPT = """You are a quantitative trading strategy assistant for the Pareto Terminal.
Given an asset's historical statistics and optionally a natural language description, generate a trading strategy configuration and Python code.
If no strategy idea is provided, analyze the statistics and suggest the most appropriate strategy yourself.

## Step 1 — Brief explanation (2-4 sentences)
If no prompt is given, start by explaining what the statistics reveal about the asset and why you chose this strategy.

## Step 2 — JSON config in a ```json block with exactly these fields:
{
  "ticker": "BTC-USD",
  "timeframe": "1h",
  "sl_mult": 2.0,
  "tp_mult": 4.0,
  "active_hours": [6, 22],
  "risk_per_trade": 1.0,
  "direction": "ALL"
}

Field constraints:
- ticker: one of "BTC-USD", "ETH-USD", "SOL-USD", "ARB-USD", "OP-USD", "AVAX-USD"
- timeframe: one of "5m", "15m", "1h", "4h", "1d"
- sl_mult: 0.5 – 5.0 (ATR stop loss multiplier)
- tp_mult: 1.0 – 10.0 (take profit multiplier)
- active_hours: [start_hour, end_hour] UTC (0-23)
- risk_per_trade: 0.1 – 3.0 (% of equity)
- direction: "ALL", "LONG", or "SHORT"

## Step 3 — Python agent_fn in a ```python block.
The function receives a DataFrame with columns: open, high, low, close, volume,
ATR14, RSI14, EMA20, EMA50, VWAP, BBupper, BBlower.
It must return the DataFrame with added columns: signal (1/−1/0), SL_dist, TP_dist.
Use only pandas/numpy. Keep it self-contained.
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
        "```json\n"
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
    if body.prompt and body.prompt.strip():
        parts.append(f"Strategy idea: {body.prompt.strip()}")
    else:
        parts.append("No strategy idea provided — please analyze the statistics above and suggest the best strategy for this asset.")
    return "\n\n".join(parts)


async def _claude_stream(body: VibeGenerateRequest):
    """Real Claude stream via anthropic SDK."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run():
        try:
            with client.messages.stream(
                model="claude-opus-4-7",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_message(body),
                    }
                ],
            ) as stream:
                for text in stream.text_stream:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(("delta", text)), loop
                    )
        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                queue.put(("error", str(exc))), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

    loop.run_in_executor(_executor, _run)

    full_text = ""
    while True:
        kind, val = await queue.get()
        if kind == "delta":
            full_text += val
            yield f"data: {json.dumps({'type': 'delta', 'text': val})}\n\n"
        elif kind == "error":
            yield f"data: {json.dumps({'type': 'delta', 'text': f'[Error: {val}]'})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': ''})}\n\n"
            break
        else:
            config = _extract_config(full_text)
            code = _extract_code(full_text)
            yield f"data: {json.dumps({'type': 'done', 'config': config, 'code': code})}\n\n"
            break


@router.post("/generate")
async def vibe_generate(body: VibeGenerateRequest):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return StreamingResponse(_mock_stream(body), media_type="text/event-stream")
    return StreamingResponse(_claude_stream(body), media_type="text/event-stream")


@router.post("/improve")
async def vibe_improve(body: dict):
    return {"status": "stub"}
