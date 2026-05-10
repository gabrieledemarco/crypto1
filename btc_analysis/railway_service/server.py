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


# ── Code extraction helpers ───────────────────────────────────────────────────

import re as _re


def _find_python_in_text(text: str) -> str:
    """Return the largest Python block found in text (markdown or raw)."""
    # ```python ... ``` blocks
    blocks = _re.findall(r"```python\s*\n(.*?)```", text, _re.DOTALL)
    if not blocks:
        blocks = _re.findall(r"```\s*\n(.*?)```", text, _re.DOTALL)
    if blocks:
        return max(blocks, key=len)
    # raw Python heuristic
    if "def " in text and "return" in text and len(text) > 80:
        return text
    return ""


def _walk_json(obj, depth: int = 0) -> list:
    """Recursively collect string leaves from JSON that look like Python."""
    if depth > 12:
        return []
    if isinstance(obj, str):
        code = _find_python_in_text(obj)
        return [code] if code else []
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out.extend(_walk_json(v, depth + 1))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_walk_json(item, depth + 1))
        return out
    return []


def _extract_code_from_run_dir(run_dir: str, all_files: list) -> str:
    """
    vibe-trading stores its output in JSON files (trace.jsonl, state.json).
    Parse them all and return the longest Python snippet found.
    req.json is the saved prompt file — always excluded to avoid extracting
    the placeholder function from the prompt template itself.
    """
    candidates: list[tuple[int, str]] = []

    for fpath in all_files:
        # Skip the request/prompt file — it contains our template placeholder code
        if os.path.basename(fpath) == "req.json":
            continue

        try:
            raw = open(fpath, encoding="utf-8").read()
        except Exception:
            continue

        # JSONL: each line is a JSON object
        if fpath.endswith(".jsonl"):
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    for snippet in _walk_json(obj):
                        candidates.append((len(snippet), snippet))
                except json.JSONDecodeError:
                    pass
            # also scan the raw text for code blocks
            code = _find_python_in_text(raw)
            if code:
                candidates.append((len(code), code))

        elif fpath.endswith(".json"):
            try:
                obj = json.loads(raw)
                for snippet in _walk_json(obj):
                    candidates.append((len(snippet), snippet))
            except json.JSONDecodeError:
                pass

        elif fpath.endswith(".py"):
            if len(raw) > 30:
                candidates.append((len(raw), raw))

    if not candidates:
        return ""
    best = sorted(candidates, reverse=True)[0][1]
    print(f"[vibe] extracted code ({len(best)} chars) from run_dir", flush=True)
    return best


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

        print(f"[vibe] exit={r.returncode} stdout_len={len(r.stdout)} stderr_len={len(r.stderr)}", flush=True)
        print(f"[vibe] stdout (last 600): {r.stdout[-600:]!r}", flush=True)
        if r.stderr:
            print(f"[vibe] stderr (last 300): {r.stderr[-300:]!r}", flush=True)

        if not run_data:
            raise RuntimeError(
                f"vibe-trading exit={r.returncode}. "
                f"stdout: {r.stdout[-400:]!r}  stderr: {r.stderr[-300:]!r}"
            )

        run_id  = run_data.get("run_id", "")
        run_dir = run_data.get("run_dir", "")
        if run_dir and not os.path.isabs(run_dir):
            run_dir = os.path.join(vibe_home, run_dir)

        # Method 0: scan full stdout for Python blocks
        # (vibe-trading may stream LLM output to stdout before the JSON line)
        stdout_code = _find_python_in_text(r.stdout)
        if stdout_code and len(stdout_code) > 150:
            print(f"[vibe] found code in stdout ({len(stdout_code)} chars)", flush=True)
            return stdout_code

        # Method 1: vibe-trading --code <run_id>
        try:
            rc = subprocess.run(
                ["vibe-trading", "--code", run_id],
                capture_output=True, text=True, timeout=30, env=env,
            )
            print(f"[vibe] --code exit={rc.returncode} len={len(rc.stdout)}", flush=True)
            if rc.returncode == 0 and len(rc.stdout.strip()) > 20:
                return rc.stdout
        except Exception as e:
            print(f"[vibe] --code exception: {e}", flush=True)

        # Method 2: extract code from JSON files in run_dir
        # vibe-trading stores output in trace.jsonl / state.json (no .py files).
        # req.json is the saved prompt file and is excluded by _extract_code_from_run_dir.
        if run_dir and os.path.isdir(run_dir):
            all_files = []
            for root, _, files in os.walk(run_dir):
                for fname in files:
                    all_files.append(os.path.join(root, fname))
            print(f"[vibe] run_dir={run_dir!r} files={all_files}", flush=True)

            # Diagnostic: dump first 800 chars of each non-req file so we can
            # see the actual format and fix extraction if needed.
            for fpath in all_files:
                if os.path.basename(fpath) == "req.json":
                    continue
                try:
                    raw = open(fpath, encoding="utf-8").read()
                    print(
                        f"[vibe] {os.path.basename(fpath)} "
                        f"({len(raw)} chars): {raw[:800]!r}",
                        flush=True,
                    )
                except Exception as exc:
                    print(f"[vibe] cannot read {fpath}: {exc}", flush=True)

            code = _extract_code_from_run_dir(run_dir, all_files)
            if code:
                return code

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
