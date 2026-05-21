"""
/vibe router — Claude streaming proxy
POST /vibe/generate  → SSE stream: {type:"delta",text} … {type:"done",config:{}}
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
Given a natural language description, generate a trading strategy configuration as JSON.

After a brief explanation, output the config in a ```json block with exactly these fields:
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
"""


def _extract_config(text: str) -> dict:
    """Extract JSON config from Claude response text."""
    # Try ```json block first
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: first {...} object
    m = re.search(r"\{[^{}]*\"ticker\"[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def _mock_stream(body: VibeGenerateRequest):
    """Fallback stream when ANTHROPIC_API_KEY is not set."""
    asset = body.asset or "BTC-USD"
    ticker = asset if "-USD" in asset else f"{asset}-USD"
    timeframe = body.timeframe or "1h"
    mock_text = (
        f"Analyzing your strategy idea for {asset} on {timeframe}…\n\n"
        "Based on your description I recommend a momentum approach with "
        "dynamic ATR-based stops. The configuration below uses a conservative "
        "risk-per-trade and filters activity to liquid trading hours.\n\n"
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
        "```"
    )
    chunk_size = 30
    for i in range(0, len(mock_text), chunk_size):
        chunk = mock_text[i : i + chunk_size]
        yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"
        await asyncio.sleep(0.04)

    config = _extract_config(mock_text)
    yield f"data: {json.dumps({'type': 'done', 'config': config})}\n\n"


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
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"{body.prompt}\n\nAsset: {body.asset}\nTimeframe: {body.timeframe or '1h'}",
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
            yield f"data: {json.dumps({'type': 'done', 'config': {}})}\n\n"
            break
        else:
            config = _extract_config(full_text)
            yield f"data: {json.dumps({'type': 'done', 'config': config})}\n\n"
            break


@router.post("/generate")
async def vibe_generate(body: VibeGenerateRequest):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return StreamingResponse(_mock_stream(body), media_type="text/event-stream")
    return StreamingResponse(_claude_stream(body), media_type="text/event-stream")


@router.post("/improve")
async def vibe_improve(body: dict):
    return {"status": "stub"}
