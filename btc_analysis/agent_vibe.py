"""
agent_vibe.py
=============
Step 2: generazione strategia tramite Vibe-Trading.

Modalità (in ordine di priorità):
  1. RAILWAY  — se VIBE_TRADING_API_URL è impostato (o passato come parametro),
                chiama il microservizio Railway via HTTP.
  2. CLI      — se vibe-trading-ai è installato localmente, usa subprocess.

In caso di errore, propaga l'eccezione (nessun fallback silenzioso).

Ritorno: tuple (config, code, report, engine_used)
  engine_used: "vibe-trading (Railway)" | "vibe-trading (CLI)"
"""

import os, sys, json, subprocess, tempfile

sys.path.insert(0, os.path.dirname(__file__))

from agent_strategy import (
    _build_context, _atr_stats,
    _extract_block, _validate_config, _validate_code,
    save_outputs,
    OPENROUTER_API_URL, OPENROUTER_DEFAULT_MODEL,
)
from strategy_core import OUTPUT_DIR

VIBE_TIMEOUT = 600   # 10 min


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_vibe_prompt(asset: str) -> str:
    context = _build_context(asset)
    atr     = _atr_stats(asset)
    return f"""You are a quantitative trading developer for {asset}.
Your task: write one Python function `generate_signals_agent(df)`.

IMPORTANT: Do NOT download data. Do NOT import libraries. ONLY write the function.

══ STATISTICAL ANALYSIS ══
{context}

ATR: median {atr.get('median_atr_pct', 0.003)*100:.3f}%
2×ATR stop-loss: {atr.get('sl2x_pct', 0.006)*100:.3f}%

══ FUNCTION CONTRACT ══
Input df has pre-computed columns:
  Open, High, Low, Close, Volume
  ATR14       — 14-period ATR (absolute price)
  RSI14       — RSI 0-100
  EMA50       — 50-period EMA
  EMA200      — 200-period EMA
  RollHigh6   — 6-bar rolling High (shifted 1 bar)
  RollLow6    — 6-bar rolling Low  (shifted 1 bar)
  ATR_pct     — ATR14 / Close
  hour        — UTC hour 0-23
  dow         — weekday 0=Mon
  ret         — pct_change()
  garch_h     — GARCH variance
  garch_regime — "LOW" / "MED" / "HIGH"
  size_mult   — 0.0/0.5/1.0 from GARCH

Rules:
1. Start: df = df.copy()
2. df["signal"]  = 1 (long) / -1 (short) / 0 (flat)
3. df["SL_dist"] = ATR14 × sl_mult  (absolute price, sl_mult ≥ 1.5)
4. df["TP_dist"] = ATR14 × tp_mult  (TP/SL ≥ 2.5)
5. Return df
6. Use ONLY pd and np (already imported). Extra indicators inline are OK:
   ema20 = df["Close"].ewm(span=20, adjust=False).mean()

Commission: 0.04%/side. Targets: Sharpe > 0.5, PF > 1.3, CAGR > 5%, N_trades ≥ 20.

══ OUTPUT FORMAT — nothing else ══

```json
{{
  "strategy_type": "<trend_following|mean_reversion|breakout|momentum>",
  "strategy_name": "<descriptive name>",
  "sl_mult": <float ≥ 1.5>,
  "tp_mult": <float ≥ sl_mult × 2.5>,
  "active_hours": [<start 0-23>, <end 0-23>],
  "commission": 0.0004,
  "slippage": 0.0001,
  "risk_per_trade": 0.01,
  "rationale": "<one sentence>"
}}
```

```python
def generate_signals_agent(df):
    df = df.copy()
    # implementation using only pd and np
    return df
```
"""


# ── Mode 1: Railway remote API ────────────────────────────────────────────────

def _call_railway_api(
    prompt: str,
    api_url: str,
    anthropic_key: str,
    openrouter_key: str,
    openrouter_model: str,
    service_token: str = "",
) -> str:
    """POST to Railway microservice and return the raw generated code."""
    import requests as _req

    if not api_url.startswith(("http://", "https://")):
        api_url = "https://" + api_url
    url = api_url.rstrip("/") + "/generate"
    headers = {"Content-Type": "application/json"}
    if service_token:
        headers["Authorization"] = f"Bearer {service_token}"

    resp = _req.post(
        url,
        json={
            "prompt": prompt,
            "anthropic_key": anthropic_key,
            "openrouter_key": openrouter_key,
            "openrouter_model": openrouter_model,
        },
        headers=headers,
        timeout=VIBE_TIMEOUT + 30,  # slightly over internal timeout
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"Railway service error: {data['error']}")

    code = data.get("code", "")
    if not code:
        raise RuntimeError("Railway service returned empty code")
    return code


# ── Mode 2: Local CLI ─────────────────────────────────────────────────────────

def _is_vibe_installed() -> bool:
    try:
        r = subprocess.run(
            ["vibe-trading", "--help"],
            capture_output=True, timeout=8,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _make_vibe_env(
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
) -> tuple:
    env = os.environ.copy()
    if anthropic_key:
        env["LANGCHAIN_PROVIDER"]   = "anthropic"
        env["ANTHROPIC_API_KEY"]    = anthropic_key
        env["LANGCHAIN_MODEL_NAME"] = "claude-opus-4-7"
    elif openrouter_key:
        env["LANGCHAIN_PROVIDER"]   = "openai"
        env["OPENAI_API_KEY"]       = openrouter_key
        env["OPENAI_BASE_URL"]      = "https://openrouter.ai/api/v1"
        env["LANGCHAIN_MODEL_NAME"] = openrouter_model or "anthropic/claude-opus-4-7"

    import tempfile as _tf
    _vibe_home = os.path.join(_tf.gettempdir(), "vibe_trading_home")
    os.makedirs(_vibe_home, exist_ok=True)
    env["HOME"]              = _vibe_home
    env["VIBE_TRADING_HOME"] = _vibe_home
    env["XDG_DATA_HOME"]     = os.path.join(_vibe_home, ".local", "share")
    env["XDG_CONFIG_HOME"]   = os.path.join(_vibe_home, ".config")
    env["XDG_CACHE_HOME"]    = os.path.join(_vibe_home, ".cache")
    return env, _vibe_home


def _run_cli(prompt_file: str, env: dict, cwd: str) -> dict:
    r = subprocess.run(
        ["vibe-trading", "run", "-f", prompt_file, "--json", "--no-rich"],
        capture_output=True, text=True,
        timeout=VIBE_TIMEOUT, env=env, cwd=cwd,
    )
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if "run_id" in data:
                    return data
            except json.JSONDecodeError:
                pass
    raise RuntimeError(
        f"vibe-trading exit={r.returncode}. "
        f"stdout: {r.stdout[-400:]!r}  stderr: {r.stderr[-300:]!r}"
    )


def _fetch_code(run_id: str, run_dir: str, env: dict) -> str:
    try:
        r = subprocess.run(
            ["vibe-trading", "--code", run_id],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if r.returncode == 0 and "def " in r.stdout:
            return r.stdout
    except Exception:
        pass

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
        f"Codice non trovato: run_id={run_id!r}  run_dir={run_dir!r}"
    )


# ── Code adaptation (shared by all modes) ────────────────────────────────────

_ADAPT_SYSTEM = "You adapt trading strategy code to an exact Python function contract."

_ADAPT_USER = """\
Rewrite the following code to match this EXACT signature:

def generate_signals_agent(df):
    df = df.copy()
    # use only pd and np (already imported)
    # df["signal"]  = 1 / -1 / 0
    # df["SL_dist"] = ATR14 * sl_mult  (absolute price, sl_mult >= 1.5)
    # df["TP_dist"] = ATR14 * tp_mult  (TP_dist / SL_dist >= 2.5)
    return df

Available df columns: Open, High, Low, Close, Volume, ATR14, RSI14, EMA50, EMA200,
RollHigh6, RollLow6, ATR_pct, hour, dow, ret, garch_h, garch_regime, size_mult.
Extra indicators may be computed inline. Do NOT import anything.

Original code:
```python
{code}
```

Return ONLY a ```python block containing the adapted function.
"""

_ADAPT_RETRY = """\
CRITICAL: your previous adaptation is missing required columns.
The function MUST assign ALL three of:
  df["signal"]  = 1 (long) / -1 (short) / 0 (flat)
  df["SL_dist"] = df["ATR14"] * sl_mult   (sl_mult >= 1.5)
  df["TP_dist"] = df["ATR14"] * tp_mult   (tp_mult >= 3.75)

Rewrite `generate_signals_agent(df)` preserving the trading logic below
but ensuring every row has all three columns. Use ONLY pd and np. No imports.

Source:
```python
{code}
```

Return ONLY a ```python block.
"""

_REQUIRED_COLS = ("signal", "SL_dist", "TP_dist")

# Sentinel present in the prompt template placeholder — if this appears in the
# extracted code it means the Railway service returned the prompt example instead
# of the actual LLM-generated strategy.
_PLACEHOLDER_SENTINEL = "# implementation using only pd and np"


def _has_cols(code: str) -> bool:
    """Accept both single and double quote styles for column assignment."""
    return all(
        f'"{c}"' in code or f"'{c}'" in code
        for c in _REQUIRED_COLS
    )


def _adapt_code(
    raw: str,
    anthropic_key: str,
    openrouter_key: str,
    openrouter_model: str,
) -> str:
    # Detect the prompt placeholder — Railway extracted the template instead of
    # the real strategy (happens when req.json is scanned instead of trace.jsonl)
    if _PLACEHOLDER_SENTINEL in raw:
        raise ValueError(
            "Il servizio Railway ha restituito il codice placeholder del prompt "
            "invece della strategia generata. Verifica che vibe-trading stia "
            "completando correttamente l'esecuzione (controlla i log Railway)."
        )

    # Test raw first with actual execution
    if "def generate_signals_agent" in raw:
        try:
            _validate_code(raw)
            return raw
        except Exception:
            pass

    print(f"  [vibe] Adattamento codice ({len(raw)} chars): {raw[:120]!r}…")

    def _call_llm(prompt: str) -> str:
        """Try anthropic first, then openrouter as cascade."""
        if anthropic_key:
            try:
                import anthropic as _sdk
                resp = _sdk.Anthropic(api_key=anthropic_key).messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    system=_ADAPT_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
                result = resp.content[0].text
                print(f"  [vibe] haiku ok ({len(result)} chars)")
                return result
            except Exception as e:
                print(f"  [vibe] haiku fallito: {e} — provo openrouter…")
        if openrouter_key:
            try:
                import requests as _req
                model = openrouter_model or "anthropic/claude-haiku-4-5"
                resp = _req.post(
                    OPENROUTER_API_URL,
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/gabrieledemarco/crypto1",
                    },
                    json={
                        "model": model,
                        "max_tokens": 2048,
                        "messages": [
                            {"role": "system", "content": _ADAPT_SYSTEM},
                            {"role": "user",   "content": prompt},
                        ],
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]
                print(f"  [vibe] openrouter ok ({len(result)} chars)")
                return result
            except Exception as e:
                print(f"  [vibe] openrouter fallito: {e}")
        return ""

    def _try_adapt(prompt: str, label: str):
        text = _call_llm(prompt)
        if not text:
            print(f"  [vibe] {label}: LLM non ha risposto")
            return None
        adapted = _extract_block(text, "python")
        if not adapted:
            print(f"  [vibe] {label}: nessun blocco ```python trovato")
            return None
        if "def generate_signals_agent" not in adapted:
            print(f"  [vibe] {label}: funzione mancante. Inizio: {adapted[:80]!r}")
            return None
        try:
            _validate_code(adapted)
            print(f"  [vibe] {label}: ✅ codice valido")
            return adapted
        except Exception as ve:
            print(f"  [vibe] {label}: _validate_code fallita → {ve}")
            return None

    result = _try_adapt(_ADAPT_USER.format(code=raw[:4000]), "Attempt 1")
    if result:
        return result

    result = _try_adapt(_ADAPT_RETRY.format(code=raw[:4000]), "Attempt 2")
    if result:
        return result

    raise ValueError(
        f"Adattamento fallito dopo 2 tentativi LLM. "
        f"Codice estratto ({len(raw)} chars): {raw[:200]!r}"
    )


# ── Shared post-processing ────────────────────────────────────────────────────

def _post_process(
    raw_code: str,
    asset: str,
    engine_label: str,
    anthropic_key: str,
    openrouter_key: str,
    openrouter_model: str,
    run_id: str = "",
) -> tuple:
    """Adapt code, extract config, validate, build report. Returns (cfg, code, report)."""
    code = _adapt_code(raw_code, anthropic_key, openrouter_key, openrouter_model)
    _validate_code(code)  # raises ValueError if function missing

    cfg = None
    for src in (raw_code, code):
        raw_json = _extract_block(src, "json")
        if raw_json:
            try:
                cfg = _validate_config(json.loads(raw_json), source=engine_label)
                break
            except Exception:
                pass
    if not cfg:
        cfg = {
            "strategy_type":  "unknown",
            "strategy_name":  f"VibeTrade {asset}",
            "sl_mult":        2.0,  "tp_mult": 5.0,
            "active_hours":   [6, 22],
            "commission":     0.0004, "slippage": 0.0001,
            "risk_per_trade": 0.01,
            "rationale":      f"Generated by {engine_label}",
        }

    run_suffix = f" | Run: {run_id}" if run_id else ""
    report = (
        f"# Strategy Report — {asset}\n"
        f"*Engine: {engine_label}{run_suffix}*\n\n"
        f"**{cfg.get('strategy_name')}** ({cfg.get('strategy_type')})\n"
        f"SL {cfg.get('sl_mult')}×ATR | TP {cfg.get('tp_mult')}×ATR | "
        f"active_hours {cfg.get('active_hours')}\n\n"
        f"---\n\n```python\n{code}\n```"
    )
    return cfg, code, report


# ── Main entry point ──────────────────────────────────────────────────────────

def run_vibe_agent(
    asset: str = "BTC-USD",
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
    vibe_api_url: str = "",
    vibe_service_token: str = "",
) -> tuple:
    """
    Genera (config, code, report, engine_used).

    engine_used: "vibe-trading (Railway)" | "vibe-trading (CLI)"

    Priority:
      1. Railway API  — if vibe_api_url is set (Streamlit Cloud / production)
      2. Local CLI    — if vibe-trading-ai is installed

    Raises RuntimeError or ValueError on failure (no fallback).
    """
    if not vibe_api_url:
        vibe_api_url = os.environ.get("VIBE_TRADING_API_URL", "")
    if not vibe_service_token:
        vibe_service_token = os.environ.get("VIBE_SERVICE_TOKEN", "")

    prompt = _build_vibe_prompt(asset)

    # ── Mode 1: Railway remote API ────────────────────────────────────────────
    if vibe_api_url:
        print(f"  [vibe] Modalità Railway: {vibe_api_url}")
        raw_code = _call_railway_api(
            prompt, vibe_api_url, anthropic_key,
            openrouter_key, openrouter_model, vibe_service_token,
        )
        print(f"  [vibe] Codice ricevuto ({len(raw_code)} chars). Adattamento contratto…")
        cfg, code, report = _post_process(
            raw_code, asset, "Vibe-Trading (Railway)",
            anthropic_key, openrouter_key, openrouter_model,
        )
        print(f"  [vibe] ✅ Strategia: {cfg.get('strategy_name')}")
        return cfg, code, report, "vibe-trading (Railway)"

    # ── Mode 2: Local CLI ─────────────────────────────────────────────────────
    if not _is_vibe_installed():
        raise RuntimeError(
            "vibe-trading-ai non installato e nessun URL Railway configurato. "
            "Configura VIBE_TRADING_API_URL nella sidebar."
        )

    env, vibe_home = _make_vibe_env(anthropic_key, openrouter_key, openrouter_model)
    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8",
            dir=vibe_home,
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        print(f"  [vibe] CLI run (timeout {VIBE_TIMEOUT}s, cwd={vibe_home})…")
        data    = _run_cli(prompt_file, env, cwd=vibe_home)
        run_id  = data.get("run_id", "")
        run_dir = data.get("run_dir", "")
        if run_dir and not os.path.isabs(run_dir):
            run_dir = os.path.join(vibe_home, run_dir)
        print(f"  [vibe] Run completato: {run_id}  run_dir={run_dir}")

        raw_code = _fetch_code(run_id, run_dir, env)
        print(f"  [vibe] Codice ({len(raw_code)} chars). Adattamento contratto…")

    finally:
        if prompt_file:
            try:
                os.unlink(prompt_file)
            except Exception:
                pass

    cfg, code, report = _post_process(
        raw_code, asset, "Vibe-Trading (CLI)",
        anthropic_key, openrouter_key, openrouter_model,
        run_id=run_id,
    )
    print(f"  [vibe] ✅ Strategia: {cfg.get('strategy_name')}")
    return cfg, code, report, "vibe-trading (CLI)"


if __name__ == "__main__":
    import agent_strategy as _ag

    asset    = os.environ.get("STRATEGY_ASSET",    "BTC-USD")
    ant_key  = os.environ.get("ANTHROPIC_API_KEY",  "")
    or_key   = os.environ.get("OPENROUTER_API_KEY", "")
    or_model = os.environ.get("OPENROUTER_MODEL",   "")
    api_url  = os.environ.get("VIBE_TRADING_API_URL", "")
    svc_tok  = os.environ.get("VIBE_SERVICE_TOKEN", "")

    print("=" * 60)
    print(f"  AGENT VIBE — {asset}")
    print("=" * 60)

    cfg, code, report, engine = run_vibe_agent(
        asset=asset,
        anthropic_key=ant_key,
        openrouter_key=or_key,
        openrouter_model=or_model,
        vibe_api_url=api_url,
        vibe_service_token=svc_tok,
    )
    print(f"  Engine: {engine}")
    _ag.save_outputs(cfg, code, report)
    print("\nAgent Vibe completato.")
