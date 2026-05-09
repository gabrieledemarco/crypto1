"""
server.py — Railway microservice wrapping vibe-trading-ai.

Endpoints:
  GET  /health            → {"status": "ok"}
  POST /generate          → {"code": "...", "error": ""}

Authentication (optional):
  Set SERVICE_TOKEN env var on Railway; send  Authorization: Bearer <token>.
  If SERVICE_TOKEN is not set the endpoint is open (dev mode).

Environment variables expected on Railway:
  SERVICE_TOKEN   — shared secret to protect the endpoint (recommended)
  PORT            — injected by Railway automatically

The endpoint is synchronous and may take up to 10 minutes; Railway does not
impose a hard HTTP timeout, so this is fine.
"""

import os
import json
import subprocess
import tempfile
import shutil
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Vibe-Trading Strategy Service", version="1.0.0")

VIBE_TIMEOUT = int(os.environ.get("VIBE_TIMEOUT", 600))
SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "")

_port = os.environ.get("PORT", "8080")
print(f"[startup] Vibe-Trading service — PORT={_port}  SERVICE_TOKEN={'SET' if SERVICE_TOKEN else 'OPEN'}", flush=True)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _check_auth(authorization: str = ""):
    if not SERVICE_TOKEN:
        return  # open mode — no token configured
    token = authorization.removeprefix("Bearer ").strip()
    if token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Request / Response models ─────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str
    anthropic_key: str = ""
    openrouter_key: str = ""
    openrouter_model: str = ""


class GenerateResponse(BaseModel):
    code: str = ""
    error: str = ""


# ── Core vibe-trading runner ──────────────────────────────────────────────────

def _run_vibe(req: GenerateRequest) -> str:
    """Run vibe-trading CLI and return the generated Python code."""
    vibe_home = tempfile.mkdtemp(prefix="vibe_home_")
    prompt_file = None
    try:
        env = os.environ.copy()
        if req.anthropic_key:
            env["LANGCHAIN_PROVIDER"]   = "anthropic"
            env["ANTHROPIC_API_KEY"]    = req.anthropic_key
            env["LANGCHAIN_MODEL_NAME"] = "claude-opus-4-7"
        elif req.openrouter_key:
            env["LANGCHAIN_PROVIDER"]   = "openai"
            env["OPENAI_API_KEY"]       = req.openrouter_key
            env["OPENAI_BASE_URL"]      = "https://openrouter.ai/api/v1"
            env["LANGCHAIN_MODEL_NAME"] = (
                req.openrouter_model or "anthropic/claude-opus-4-7"
            )

        env["HOME"]              = vibe_home
        env["VIBE_TRADING_HOME"] = vibe_home
        env["XDG_DATA_HOME"]     = os.path.join(vibe_home, ".local", "share")
        env["XDG_CONFIG_HOME"]   = os.path.join(vibe_home, ".config")
        env["XDG_CACHE_HOME"]    = os.path.join(vibe_home, ".cache")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            encoding="utf-8", dir=vibe_home,
        ) as f:
            f.write(req.prompt)
            prompt_file = f.name

        r = subprocess.run(
            ["vibe-trading", "run", "-f", prompt_file, "--json", "--no-rich"],
            capture_output=True, text=True,
            timeout=VIBE_TIMEOUT, env=env, cwd=vibe_home,
        )

        run_data: dict = {}
        for line in reversed(r.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = json.loads(line)
                    if "run_id" in d:
                        run_data = d
                        break
                except json.JSONDecodeError:
                    pass

        if not run_data:
            raise RuntimeError(
                f"vibe-trading exit={r.returncode}. "
                f"stdout: {r.stdout[-400:]!r}  stderr: {r.stderr[-300:]!r}"
            )

        run_id  = run_data.get("run_id", "")
        run_dir = run_data.get("run_dir", "")
        if run_dir and not os.path.isabs(run_dir):
            run_dir = os.path.join(vibe_home, run_dir)

        # Method 1: vibe-trading --code <run_id>
        try:
            rc = subprocess.run(
                ["vibe-trading", "--code", run_id],
                capture_output=True, text=True, timeout=30, env=env,
            )
            if rc.returncode == 0 and "def " in rc.stdout:
                return rc.stdout
        except Exception:
            pass

        # Method 2: largest .py in run_dir
        if run_dir and os.path.isdir(run_dir):
            candidates = []
            for fname in os.listdir(run_dir):
                if not fname.endswith(".py") or "test" in fname.lower():
                    continue
                fpath = os.path.join(run_dir, fname)
                try:
                    content = open(fpath, encoding="utf-8").read()
                    if "def " in content and len(content) > 100:
                        candidates.append((len(content), content))
                except Exception:
                    pass
            if candidates:
                return sorted(candidates, reverse=True)[0][1]

        raise RuntimeError(
            f"No code found: run_id={run_id!r}  run_dir={run_dir!r}"
        )

    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except Exception:
                pass
        shutil.rmtree(vibe_home, ignore_errors=True)


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
        code = _run_vibe(req)
        return GenerateResponse(code=code)
    except Exception as exc:
        return GenerateResponse(error=str(exc))
