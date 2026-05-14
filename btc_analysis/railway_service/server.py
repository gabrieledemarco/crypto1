"""
server.py — Railway microservice: vibe-trading strategy generator.

Runs vibe-trading-ai with the user's LLM keys to generate trading
strategies using its built-in finance skills. Before each run, writes
the correct model/key to vibe-trading's agent/.env file (which it reads
instead of standard env vars).

Falls back to a direct Anthropic/OpenRouter call if vibe-trading fails.

Endpoints:
  GET  /health   → {"status": "ok"}
  POST /generate → {"code": "...", "error": ""}

Environment (Railway):
  SERVICE_TOKEN  — shared secret (recommended)
  PORT           — injected by Railway
  VIBE_TIMEOUT   — max seconds for vibe-trading run (default 600)
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
import importlib.util
import re as _re
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Strategy Generator Service", version="3.0.0")

SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "")
VIBE_TIMEOUT  = int(os.environ.get("VIBE_TIMEOUT", 600))
_port = os.environ.get("PORT", "8080")
print(
    f"[startup] Strategy service v3 — PORT={_port}  "
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


# ── Code extraction helpers ───────────────────────────────────────────────────

def _find_python_in_text(text: str) -> str:
    """Return the largest Python block found in text (markdown or raw)."""
    blocks = _re.findall(r"```python\s*\n(.*?)```", text, _re.DOTALL)
    if not blocks:
        blocks = _re.findall(r"```\s*\n(.*?)```", text, _re.DOTALL)
    if blocks:
        return max(blocks, key=len)
    if "def " in text and "return" in text and len(text) > 80:
        return text
    return ""


def _walk_json(obj, depth: int = 0) -> list:
    """Recursively collect string leaves from a JSON object that look like Python."""
    if depth > 12:
        return []
    if isinstance(obj, str):
        code = _find_python_in_text(obj)
        return [code] if code else []
    if isinstance(obj, dict):
        # Prioritise fields likely to hold generated code
        for key in ("code", "generated_code", "strategy_code", "result", "output"):
            if key in obj and isinstance(obj[key], str):
                code = _find_python_in_text(obj[key])
                if code:
                    return [code]
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
    Parse vibe-trading output files (trace.jsonl, state.json) and return
    the longest Python snippet found. Skips req.json (the saved prompt).
    """
    candidates: list[tuple[int, str]] = []

    for fpath in all_files:
        if os.path.basename(fpath) == "req.json":
            continue
        try:
            raw = open(fpath, encoding="utf-8").read()
        except Exception:
            continue

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
            code = _find_python_in_text(raw)
            if code:
                candidates.append((len(code), code))

        elif fpath.endswith(".json"):
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and isinstance(obj.get("code"), str):
                    candidates.append((len(obj["code"]), obj["code"]))
                for snippet in _walk_json(obj):
                    candidates.append((len(snippet), snippet))
            except json.JSONDecodeError:
                pass

        elif fpath.endswith(".py"):
            if len(raw) > 30:
                candidates.append((len(raw), raw))

    valid = [(l, c) for l, c in candidates if l >= 80]
    if not valid:
        return ""
    best = sorted(valid, reverse=True)[0][1]
    print(f"[vibe] extracted code ({len(best)} chars) from run_dir", flush=True)
    return best


# ── vibe-trading config writer ────────────────────────────────────────────────

def _find_vibe_env_path() -> str:
    """
    Find the path where vibe-trading reads its .env config.

    The vibe-trading-ai package (HKUDS/Vibe-Trading) installs the contents
    of its agent/ directory directly into site-packages, so:
      agent/src/providers/llm.py  →  <site-packages>/src/providers/llm.py
      agent/.env                  →  <site-packages>/.env

    We locate site-packages via src.providers.llm (visible in stack traces).
    """
    # Strategy 1: src.providers.llm → 3×dirname → site-packages
    try:
        spec = importlib.util.find_spec("src.providers.llm")
        if spec and spec.origin:
            site_pkgs = os.path.dirname(  # site-packages
                os.path.dirname(          # src/
                    os.path.dirname(spec.origin)  # src/providers/
                )
            )
            path = os.path.join(site_pkgs, ".env")
            print(f"[vibe] .env path (via src.providers.llm): {path}", flush=True)
            return path
    except Exception as exc:
        print(f"[vibe] src.providers.llm lookup failed: {exc}", flush=True)

    # Strategy 2: scan sys.path — find the entry that contains src/providers/
    for p in sys.path:
        if os.path.isfile(os.path.join(p, "src", "providers", "llm.py")):
            path = os.path.join(p, ".env")
            print(f"[vibe] .env path (via sys.path scan): {path}", flush=True)
            return path

    # Strategy 3: hardcoded Railway Python 3.11 location
    hardcoded = "/usr/local/lib/python3.11/site-packages/.env"
    print(f"[vibe] .env path (hardcoded fallback): {hardcoded}", flush=True)
    return hardcoded


def _write_vibe_config(
    anthropic_key: str,
    openrouter_key: str,
    openrouter_model: str,
    dest: str = "",
) -> bool:
    """Write vibe-trading's .env so it uses the caller's LLM.

    dest: explicit path; if empty, auto-detect via _find_vibe_env_path().
    """
    env_path = dest or _find_vibe_env_path()
    lines: list[str] = []

    if openrouter_key:
        model = openrouter_model or "anthropic/claude-opus-4-7"
        # vibe-trading has a native openrouter provider that reads
        # OPENROUTER_API_KEY + OPENROUTER_BASE_URL (without OPENROUTER_BASE_URL
        # it silently falls back to OpenAI's endpoint → 401)
        lines = [
            "LANGCHAIN_PROVIDER=openrouter",
            f"LANGCHAIN_MODEL_NAME={model}",
            f"OPENROUTER_API_KEY={openrouter_key}",
            "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1",
        ]
        print(f"[vibe] writing config: openrouter/{model} → {env_path}", flush=True)

    elif anthropic_key:
        lines = [
            "LANGCHAIN_PROVIDER=anthropic",
            "LANGCHAIN_MODEL_NAME=claude-opus-4-7",
            f"ANTHROPIC_API_KEY={anthropic_key}",
        ]
        print(f"[vibe] writing config: anthropic/claude-opus-4-7 → {env_path}", flush=True)

    if not lines:
        return False

    try:
        with open(env_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception as exc:
        print(f"[vibe] WARNING: cannot write {env_path}: {exc}", flush=True)
        return False


# ── vibe-trading CLI runner ───────────────────────────────────────────────────

def _run_vibe_cli(req: GenerateRequest) -> str:
    """Run vibe-trading CLI and return the generated code. Raises on failure."""
    # Resolve effective keys FIRST: request takes priority, Railway env as fallback
    _ant_key = req.anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")
    _or_key  = req.openrouter_key or os.environ.get("OPENROUTER_API_KEY", "")
    _model   = req.openrouter_model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-4-7")

    # Write vibe-trading's site-packages .env with resolved keys
    _write_vibe_config(_ant_key, _or_key, _model)

    vibe_home  = tempfile.mkdtemp(prefix="vibe_home_")
    prompt_file = None
    try:
        env = os.environ.copy()
        # Clear any stale LLM config that may be in the container env
        for _k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE",
                   "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL",
                   "ANTHROPIC_API_KEY",
                   "LANGCHAIN_PROVIDER", "LANGCHAIN_MODEL_NAME"):
            env.pop(_k, None)

        if _or_key:
            # vibe-trading native openrouter provider: needs OPENROUTER_BASE_URL
            # Without it, vibe-trading falls back to OpenAI endpoint → 401
            env["LANGCHAIN_PROVIDER"]    = "openrouter"
            env["LANGCHAIN_MODEL_NAME"]  = _model
            env["OPENROUTER_API_KEY"]    = _or_key
            env["OPENROUTER_BASE_URL"]   = "https://openrouter.ai/api/v1"
        elif _ant_key:
            env["LANGCHAIN_PROVIDER"]   = "anthropic"
            env["LANGCHAIN_MODEL_NAME"] = "claude-opus-4-7"
            env["ANTHROPIC_API_KEY"]    = _ant_key
        env["HOME"]              = vibe_home
        env["VIBE_TRADING_HOME"] = vibe_home
        env["XDG_DATA_HOME"]     = os.path.join(vibe_home, ".local", "share")
        env["XDG_CONFIG_HOME"]   = os.path.join(vibe_home, ".config")
        env["XDG_CACHE_HOME"]    = os.path.join(vibe_home, ".cache")

        # Write .env to vibe_home (CWD of subprocess) — load_dotenv() checks CWD first
        _write_vibe_config(_ant_key, _or_key, _model, dest=os.path.join(vibe_home, ".env"))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            encoding="utf-8", dir=vibe_home,
        ) as f:
            f.write(req.prompt)
            prompt_file = f.name

        print(f"[vibe] CLI run (timeout={VIBE_TIMEOUT}s)…", flush=True)
        r = subprocess.run(
            ["vibe-trading", "run", "-f", prompt_file, "--json", "--no-rich"],
            capture_output=True, text=True,
            timeout=VIBE_TIMEOUT, env=env, cwd=vibe_home,
        )
        print(
            f"[vibe] exit={r.returncode} stdout={len(r.stdout)}c stderr={len(r.stderr)}c",
            flush=True,
        )

        # Parse run metadata from last JSON line in stdout
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
        print(f"[vibe] run_id={run_id}  run_dir={run_dir}", flush=True)

        # Detect failed runs early via state.json
        if run_dir:
            state_path = os.path.join(run_dir, "state.json")
            if os.path.isfile(state_path):
                try:
                    state = json.loads(open(state_path).read())
                    if state.get("status") == "failed":
                        raise RuntimeError(
                            f"vibe-trading run failed: {state.get('reason', 'unknown')}"
                        )
                    print(f"[vibe] state.json status={state.get('status')}", flush=True)
                except (json.JSONDecodeError, OSError):
                    pass

        # Method 1: vibe-trading --code <run_id>
        try:
            rc = subprocess.run(
                ["vibe-trading", "--code", run_id],
                capture_output=True, text=True, timeout=30, env=env,
            )
            print(f"[vibe] --code exit={rc.returncode} len={len(rc.stdout)}", flush=True)
            if rc.returncode == 0 and len(rc.stdout.strip()) > 50:
                return rc.stdout
        except Exception as exc:
            print(f"[vibe] --code exception: {exc}", flush=True)

        # Method 2: scan stdout
        stdout_code = _find_python_in_text(r.stdout)
        if stdout_code and len(stdout_code) > 150:
            print(f"[vibe] found code in stdout ({len(stdout_code)} chars)", flush=True)
            return stdout_code

        # Method 3: parse run_dir JSON files
        if run_dir and os.path.isdir(run_dir):
            all_files = []
            for root, _, files in os.walk(run_dir):
                for fname in files:
                    all_files.append(os.path.join(root, fname))
            print(
                f"[vibe] scanning run_dir files: {[os.path.basename(f) for f in all_files]}",
                flush=True,
            )
            for fpath in all_files:
                if os.path.basename(fpath) == "req.json":
                    continue
                try:
                    raw = open(fpath, encoding="utf-8").read()
                    print(
                        f"[vibe] {os.path.basename(fpath)} ({len(raw)}c): {raw[:400]!r}",
                        flush=True,
                    )
                except Exception:
                    pass

            code = _extract_code_from_run_dir(run_dir, all_files)
            if code:
                return code

        raise RuntimeError(f"No code found: run_id={run_id!r}  run_dir={run_dir!r}")

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
        code = _run_vibe_cli(req)
        return GenerateResponse(code=code)
    except Exception as exc:
        return GenerateResponse(error=str(exc))
