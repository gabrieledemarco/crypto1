"""
agent_vibe.py
=============
Step 2: generazione strategia tramite Vibe-Trading CLI.

Compatibile con Streamlit Cloud: non avvia server locali, usa solo
subprocess sincroni e il filesystem temporaneo.

Flusso:
  1. Costruisce un prompt ricco dal contesto statistico (analysis_report.json)
  2. Esegue: vibe-trading run -f <prompt_file> --json --no-rich
     (API keys iniettate come env vars per il provider LLM)
  3. Legge il codice generato da run_dir o via `vibe-trading --code`
  4. Adatta il codice al contratto generate_signals_agent(df) con una
     chiamata rapida (haiku) se necessario
  5. Salva agent_config.json + agent_strategy_code.py

Fallback automatico su agent_strategy.run_agent() se:
  - vibe-trading-ai non installato  (pip install vibe-trading-ai)
  - il run fallisce per qualsiasi motivo
  - l'adattamento del codice fallisce

Ritorno: tuple (config, code, report, engine_used)
  engine_used: "vibe-trading" | "agent_strategy (fallback: ...)"
"""

import os, sys, json, re, subprocess, tempfile

sys.path.insert(0, os.path.dirname(__file__))

from agent_strategy import (
    _build_context, _atr_stats,
    _extract_block, _validate_config, _validate_code,
    save_outputs,
    run_agent as _fallback_run_agent,
    OPENROUTER_API_URL, OPENROUTER_DEFAULT_MODEL,
)
from strategy_core import OUTPUT_DIR

VIBE_TIMEOUT = 600   # 10 min: vibe-trading scarica dati + genera + backtest

# ── Install check ─────────────────────────────────────────────────────────────

def _is_vibe_installed() -> bool:
    try:
        r = subprocess.run(
            ["vibe-trading", "--help"],
            capture_output=True, timeout=8,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


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


# ── LLM env vars for vibe-trading subprocess ─────────────────────────────────

def _make_vibe_env(
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
) -> dict:
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
    return env


# ── CLI execution ─────────────────────────────────────────────────────────────

def _run_cli(prompt_file: str, env: dict) -> dict:
    """Esegue vibe-trading run e ritorna il dict JSON con run_id / run_dir."""
    r = subprocess.run(
        ["vibe-trading", "run", "-f", prompt_file, "--json", "--no-rich"],
        capture_output=True, text=True,
        timeout=VIBE_TIMEOUT, env=env,
    )
    # Il JSON può essere preceduto da output colorato — cerca l'ultima riga JSON
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
        f"stdout: {r.stdout[-400:]!r}  stderr: {r.stderr[-200:]!r}"
    )


def _fetch_code(run_id: str, run_dir: str, env: dict) -> str:
    """Recupera il codice Python generato da vibe-trading."""
    # Metodo 1: vibe-trading --code <run_id>
    try:
        r = subprocess.run(
            ["vibe-trading", "--code", run_id],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if r.returncode == 0 and "def " in r.stdout:
            return r.stdout
    except Exception:
        pass

    # Metodo 2: legge i .py dal run_dir (il più grande, escl. test)
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


# ── Code adaptation ───────────────────────────────────────────────────────────

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


def _adapt_code(
    raw: str,
    anthropic_key: str,
    openrouter_key: str,
    openrouter_model: str,
) -> str:
    """Se il codice non ha generate_signals_agent, lo adatta con una chiamata haiku."""
    if "def generate_signals_agent" in raw and 'df["signal"]' in raw:
        return raw

    prompt = _ADAPT_USER.format(code=raw[:4000])
    text = ""

    if anthropic_key:
        try:
            import anthropic as _sdk
            resp = _sdk.Anthropic(api_key=anthropic_key).messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=_ADAPT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
        except Exception as e:
            print(f"  [vibe] Adattamento haiku fallito: {e}")

    elif openrouter_key:
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
            text = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"  [vibe] Adattamento openrouter fallito: {e}")

    if text:
        adapted = _extract_block(text, "python")
        if adapted and "def generate_signals_agent" in adapted:
            return adapted

    return raw   # ritorna il raw se l'adattamento fallisce


# ── Main entry point ──────────────────────────────────────────────────────────

def run_vibe_agent(
    asset: str = "BTC-USD",
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
) -> tuple:
    """
    Genera (config, code, report, engine_used).

    engine_used: "vibe-trading" | "agent_strategy (fallback: <motivo>)"
    """
    def _do_fallback(reason: str) -> tuple:
        print(f"  [vibe] Fallback: {reason}")
        cfg, code, report = _fallback_run_agent(
            anthropic_key=anthropic_key,
            openrouter_key=openrouter_key,
            openrouter_model=openrouter_model,
            asset=asset,
        )
        return cfg, code, report, f"agent_strategy (fallback: {reason})"

    if not _is_vibe_installed():
        return _do_fallback("vibe-trading-ai non installato")

    env    = _make_vibe_env(anthropic_key, openrouter_key, openrouter_model)
    prompt = _build_vibe_prompt(asset)

    prompt_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        print(f"  [vibe] Avvio run (timeout {VIBE_TIMEOUT}s)…")
        data    = _run_cli(prompt_file, env)
        run_id  = data.get("run_id", "")
        run_dir = data.get("run_dir", "")
        print(f"  [vibe] Run completato: {run_id}")

        raw_code = _fetch_code(run_id, run_dir, env)
        print(f"  [vibe] Codice ({len(raw_code)} chars). Adattamento contratto…")

        code = _adapt_code(raw_code, anthropic_key, openrouter_key, openrouter_model)

    except Exception as exc:
        if prompt_file:
            try: os.unlink(prompt_file)
            except: pass
        return _do_fallback(str(exc)[:120])

    finally:
        if prompt_file:
            try: os.unlink(prompt_file)
            except: pass

    # Prova a estrarre il config dal codice generato / raw
    cfg = None
    for src in (raw_code, code):
        raw_json = _extract_block(src, "json")
        if raw_json:
            try:
                cfg = _validate_config(json.loads(raw_json), source="vibe-trading")
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
            "rationale":      "Generated by Vibe-Trading",
        }

    # Valida il codice (raise se la funzione non è presente)
    try:
        _validate_code(code)
    except ValueError as ve:
        return _do_fallback(f"codice non valido dopo adattamento: {ve}")

    report = (
        f"# Strategy Report — {asset}\n"
        f"*Engine: Vibe-Trading | Run ID: {run_id}*\n\n"
        f"**{cfg.get('strategy_name')}** ({cfg.get('strategy_type')})\n"
        f"SL {cfg.get('sl_mult')}×ATR | TP {cfg.get('tp_mult')}×ATR | "
        f"active_hours {cfg.get('active_hours')}\n\n"
        f"---\n\n```python\n{code}\n```"
    )
    print(f"  [vibe] ✅ Strategia: {cfg.get('strategy_name')}")
    return cfg, code, report, "vibe-trading"


if __name__ == "__main__":
    import agent_strategy as _ag

    asset    = os.environ.get("STRATEGY_ASSET",    "BTC-USD")
    ant_key  = os.environ.get("ANTHROPIC_API_KEY",  "")
    or_key   = os.environ.get("OPENROUTER_API_KEY", "")
    or_model = os.environ.get("OPENROUTER_MODEL",   "")

    print("=" * 60)
    print(f"  AGENT VIBE — {asset}")
    print("=" * 60)

    cfg, code, report, engine = run_vibe_agent(
        asset=asset,
        anthropic_key=ant_key,
        openrouter_key=or_key,
        openrouter_model=or_model,
    )
    print(f"  Engine: {engine}")
    _ag.save_outputs(cfg, code, report)
    print("\nAgent Vibe completato.")
