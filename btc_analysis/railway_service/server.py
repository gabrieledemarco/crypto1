"""
server.py — Railway microservice: LLM strategy generator.

Calls the LLM (Anthropic or OpenRouter) directly to generate a trading
strategy function. Bypasses vibe-trading (which ignores our model config
and uses a hardcoded broken default).

Endpoints:
  GET  /health   → {"status": "ok"}
  POST /generate → {"code": "...", "error": ""}

Authentication (optional):
  Set SERVICE_TOKEN env var on Railway; send  Authorization: Bearer <token>.
  If SERVICE_TOKEN is not set the endpoint is open (dev mode).

Environment variables expected on Railway:
  SERVICE_TOKEN  — shared secret (recommended)
  PORT           — injected by Railway automatically
"""

import os
import re as _re
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Strategy Generator Service", version="2.0.0")

SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "")
_port = os.environ.get("PORT", "8080")
print(
    f"[startup] Strategy service v2 — PORT={_port}  "
    f"SERVICE_TOKEN={'SET' if SERVICE_TOKEN else 'OPEN'}",
    flush=True,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(authorization: str = ""):
    if not SERVICE_TOKEN:
        return
    token = authorization.removeprefix("Bearer ").strip()
    if token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Models ────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    anthropic_key: str = ""
    openrouter_key: str = ""
    openrouter_model: str = ""


class GenerateResponse(BaseModel):
    code: str = ""
    error: str = ""


# ── LLM caller ───────────────────────────────────────────────────────────────

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _call_llm(req: GenerateRequest) -> str:
    """Call Anthropic or OpenRouter and return the raw LLM text response."""
    if req.anthropic_key:
        import anthropic
        print("[llm] Anthropic claude-opus-4-7 …", flush=True)
        client = anthropic.Anthropic(api_key=req.anthropic_key)
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            messages=[{"role": "user", "content": req.prompt}],
        )
        result = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        print(f"[llm] Anthropic ok ({len(result)} chars)", flush=True)
        return result

    if req.openrouter_key:
        import requests as _req
        model = req.openrouter_model or "anthropic/claude-opus-4-7"
        print(f"[llm] OpenRouter {model} …", flush=True)
        resp = _req.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {req.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/gabrieledemarco/crypto1",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": req.prompt}],
            },
            timeout=300,
        )
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"]
        print(f"[llm] OpenRouter ok ({len(result)} chars)", flush=True)
        return result

    raise RuntimeError(
        "No API keys provided — set anthropic_key or openrouter_key in the request."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    authorization: str = Header(default=""),
):
    _check_auth(authorization)
    try:
        code = _call_llm(req)
        return GenerateResponse(code=code)
    except Exception as exc:
        return GenerateResponse(error=str(exc))
