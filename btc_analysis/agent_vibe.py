"""
agent_vibe.py
=============
Step 2 della pipeline: generazione della strategia tramite Vibe-Trading
(https://github.com/HKUDS/Vibe-Trading).

Flusso:
  1. Legge analysis_report.json prodotto dallo Step 1
  2. Avvia vibe-trading serve localmente come subprocess
  3. Configura il provider LLM con le nostre API key esistenti
  4. Crea una sessione, invia il contesto statistico + contratto funzione
  5. Raccoglie la risposta via SSE stream
  6. Estrae generate_signals_agent(df) e agent_config.json
  7. Arresta il server
  8. I nostri 04_backtest.py + 05_montecarlo.py girano come verifica esterna

Fallback: se vibe-trading-ai non è installato o il server fallisce,
chiama direttamente agent_strategy.run_agent().

Installazione:  pip install vibe-trading-ai

Output (stesso formato di agent_strategy.py):
  output/agent_config.json
  output/agent_strategy_code.py
  output/agent_strategy_report.md
"""

import subprocess, time, json, re, os, sys

sys.path.insert(0, os.path.dirname(__file__))

from agent_strategy import (
    _build_context, _atr_stats,
    save_outputs,
    run_agent as _fallback_run_agent,
)
from strategy_core import OUTPUT_DIR

VIBE_PORT       = 8899
VIBE_BASE       = f"http://127.0.0.1:{VIBE_PORT}"
STARTUP_TIMEOUT = 60    # secondi di attesa per il server
RESPONSE_TIMEOUT = 360  # secondi di attesa per la risposta LLM


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_vibe_prompt(asset: str) -> str:
    """Costruisce il prompt da passare a Vibe-Trading dalla nostra analisi statistica."""
    context = _build_context(asset)
    atr     = _atr_stats(asset)

    return f"""You are a quantitative trading developer. Your ONLY task is to write
a single Python function `generate_signals_agent(df)` for {asset}.

DO NOT fetch data. DO NOT run a backtest. DO NOT import any library.
ONLY write the function as specified below.

══════════════════════════════════════════
STATISTICAL ANALYSIS FOR {asset}
══════════════════════════════════════════
{context}

ATR Calibration:
- Median ATR%: {atr.get('median_atr_pct', 0.003)*100:.3f}%  (typical move per bar)
- 2×ATR suggested SL: {atr.get('sl2x_pct', 0.006)*100:.3f}%

══════════════════════════════════════════
FUNCTION CONTRACT (mandatory)
══════════════════════════════════════════
Input `df` is a pandas DataFrame with these pre-computed columns:
  Open, High, Low, Close, Volume
  ATR14       — 14-period Average True Range (absolute price units)
  RSI14       — 14-period RSI (0–100)
  EMA50       — 50-period EMA of Close
  EMA200      — 200-period EMA of Close
  RollHigh6   — 6-bar rolling High, shifted 1 bar (breakout reference)
  RollLow6    — 6-bar rolling Low,  shifted 1 bar
  ATR_pct     — ATR14 / Close  (normalised volatility)
  hour        — UTC hour 0–23
  dow         — day of week 0=Mon
  ret         — Close.pct_change()
  garch_h     — GARCH(1,1) conditional variance
  garch_regime — "LOW" / "MED" / "HIGH"  (GARCH volatility regime)
  size_mult   — 0.0 (LOW) / 0.5 (HIGH) / 1.0 (MED)  (GARCH position size)

The function MUST:
  1. Start with:  df = df.copy()
  2. Set df["signal"]   = 1 (long) / -1 (short) / 0 (flat) for EVERY row
  3. Set df["SL_dist"]  = stop-loss distance in ABSOLUTE price units
                         (recommended: ATR14 × sl_mult, where sl_mult ≥ 1.5)
  4. Set df["TP_dist"]  = take-profit distance in ABSOLUTE price units
                         (TP_dist / SL_dist MUST be ≥ 2.5)
  5. Return df
  6. Use ONLY pandas (pd) and numpy (np) — both are already imported
  7. You MAY compute extra indicators inline, for example:
       ema20    = df["Close"].ewm(span=20, adjust=False).mean()
       bb_upper = df["Close"].rolling(20).mean() + 2*df["Close"].rolling(20).std()

Commission context: 0.04%/side (0.08% round-trip).
Required after-cost performance: Profit Factor > 1.3 | Sharpe > 0.5 |
CAGR > 5% | N_trades ≥ 20.

══════════════════════════════════════════
REQUIRED OUTPUT FORMAT — nothing else
══════════════════════════════════════════

```json
{{
  "strategy_type": "<trend_following|mean_reversion|breakout|range_trading|momentum>",
  "strategy_name": "<descriptive name>",
  "sl_mult": <float ≥ 1.5>,
  "tp_mult": <float ≥ sl_mult × 2.5>,
  "active_hours": [<start_hour 0-23>, <end_hour 0-23>],
  "commission": 0.0004,
  "slippage": 0.0001,
  "risk_per_trade": 0.01,
  "rationale": "<one sentence: regime → pattern → why R:R beats commission>"
}}
```

```python
def generate_signals_agent(df):
    df = df.copy()
    # ... implementation using only pd and np ...
    return df
```
"""


# ── Server management ─────────────────────────────────────────────────────────

def _is_vibe_installed() -> bool:
    try:
        r = subprocess.run(
            ["vibe-trading", "--help"],
            capture_output=True, timeout=8,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _start_server(extra_env: dict | None = None) -> subprocess.Popen:
    import requests
    env = {**os.environ, **(extra_env or {})}
    proc = subprocess.Popen(
        ["vibe-trading", "serve", "--port", str(VIBE_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    for _ in range(STARTUP_TIMEOUT):
        if proc.poll() is not None:
            raise RuntimeError("Il processo vibe-trading è uscito prematuramente")
        try:
            r = requests.get(f"{VIBE_BASE}/health", timeout=2)
            if r.status_code == 200:
                print(f"  [vibe] Server pronto su :{VIBE_PORT}")
                return proc
        except Exception:
            pass
        time.sleep(1)
    proc.terminate()
    raise RuntimeError(
        f"Vibe-Trading server non avviato entro {STARTUP_TIMEOUT}s"
    )


def _stop_server(proc: subprocess.Popen):
    import requests
    try:
        requests.post(f"{VIBE_BASE}/system/shutdown", timeout=3)
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── LLM provider configuration ────────────────────────────────────────────────

def _configure_llm(
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
):
    """Configura il provider LLM di Vibe-Trading con le nostre API key."""
    import requests
    if not anthropic_key and not openrouter_key:
        print("  [vibe] Nessuna API key fornita — usando configurazione default di Vibe-Trading.")
        return

    if anthropic_key:
        payload = {
            "provider": "anthropic",
            "model":    "claude-opus-4-7",
            "api_key":  anthropic_key,
        }
    else:
        payload = {
            "provider": "openai",
            "model":    openrouter_model or "anthropic/claude-opus-4-7",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key":  openrouter_key,
        }

    try:
        r = requests.put(f"{VIBE_BASE}/settings/llm", json=payload, timeout=10)
        if r.status_code == 200:
            print(f"  [vibe] LLM: {payload['provider']} / {payload['model']}")
        else:
            print(f"  [vibe] Avviso configurazione LLM: {r.status_code} {r.text[:120]}")
    except Exception as e:
        print(f"  [vibe] Avviso: impossibile configurare LLM ({e}) — usando default.")


# ── Session / messaging ───────────────────────────────────────────────────────

def _create_session(title: str) -> str:
    import requests
    r = requests.post(
        f"{VIBE_BASE}/sessions",
        json={"title": title},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def _send_message(session_id: str, content: str) -> str:
    import requests
    r = requests.post(
        f"{VIBE_BASE}/sessions/{session_id}/messages",
        json={"content": content},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("message_id", "")


def _collect_sse(session_id: str, timeout: int = RESPONSE_TIMEOUT) -> str:
    """
    Legge lo stream SSE di una sessione e restituisce il testo completo.
    Gestisce diversi formati di evento (type:text, type:token, data string).
    """
    import requests

    collected: list[str] = []
    deadline = time.time() + timeout

    try:
        with requests.get(
            f"{VIBE_BASE}/sessions/{session_id}/events",
            stream=True,
            timeout=timeout,
        ) as stream:
            buffer = ""
            for raw in stream.iter_content(chunk_size=None):
                if time.time() > deadline:
                    print("  [vibe] Timeout risposta raggiunto.")
                    break
                buffer += raw.decode("utf-8", errors="replace")
                # Process complete SSE lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        evt = json.loads(payload)
                    except json.JSONDecodeError:
                        # plain text payload
                        collected.append(payload)
                        continue

                    etype = evt.get("type", "")
                    if etype == "done":
                        return "".join(collected)

                    # Extract text from various event shapes
                    for key in ("content", "text", "delta", "data", "message"):
                        val = evt.get(key)
                        if isinstance(val, str) and val:
                            collected.append(val)
                            break
                        elif isinstance(val, dict):
                            # openai-style: {"delta": {"content": "..."}}
                            inner = val.get("content") or val.get("text", "")
                            if inner:
                                collected.append(inner)
                            break

    except Exception as e:
        print(f"  [vibe] SSE stream interrotto: {e}")

    return "".join(collected)


# ── Code and config extraction ────────────────────────────────────────────────

def _extract_json_config(text: str) -> dict | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _extract_python_code(text: str) -> str:
    # 1. Fenced block containing the function
    match = re.search(
        r"```python\s*(def generate_signals_agent.*?)```",
        text, re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    # 2. Any fenced python block
    match = re.search(r"```python\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        if "def generate_signals_agent" in code:
            return code
    # 3. Bare function anywhere in text
    match = re.search(r"(def generate_signals_agent\s*\(df\).*)", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    raise ValueError(
        "Nessun codice generate_signals_agent trovato nella risposta di Vibe-Trading.\n"
        f"Risposta ricevuta (primi 500 char): {text[:500]}"
    )


_DEFAULT_CONFIG = {
    "strategy_type":  "unknown",
    "strategy_name":  "VibeTrade Strategy",
    "sl_mult":        2.0,
    "tp_mult":        5.0,
    "active_hours":   [6, 22],
    "commission":     0.0004,
    "slippage":       0.0001,
    "risk_per_trade": 0.01,
    "rationale":      "Generated by Vibe-Trading",
}


# ── Main entry point ──────────────────────────────────────────────────────────

def run_vibe_agent(
    asset: str = "BTC-USD",
    anthropic_key: str = "",
    openrouter_key: str = "",
    openrouter_model: str = "",
) -> tuple:
    """
    Genera (config_dict, code_str, report_str) usando Vibe-Trading come motore.

    Falls back to agent_strategy.run_agent() se:
    - vibe-trading-ai non è installato
    - il server non si avvia
    - la risposta è vuota o non parsabile
    """
    if not _is_vibe_installed():
        print("  [vibe] vibe-trading-ai non trovato.")
        print("  Suggerimento: pip install vibe-trading-ai")
        print("  Fallback: agent_strategy.run_agent()")
        return _fallback_run_agent(
            anthropic_key=anthropic_key,
            openrouter_key=openrouter_key,
            openrouter_model=openrouter_model,
            asset=asset,
        )

    prompt = _build_vibe_prompt(asset)
    proc = None
    response = ""

    try:
        print("  [vibe] Avvio server Vibe-Trading...")
        proc = _start_server()

        _configure_llm(anthropic_key, openrouter_key, openrouter_model)

        session_id = _create_session(f"Strategy {asset}")
        print(f"  [vibe] Sessione: {session_id}")

        print("  [vibe] Invio contesto statistico ({} chars)...".format(len(prompt)))
        _send_message(session_id, prompt)

        print(f"  [vibe] Generazione strategia (timeout {RESPONSE_TIMEOUT}s)...")
        response = _collect_sse(session_id, timeout=RESPONSE_TIMEOUT)

        if not response.strip():
            raise ValueError("Risposta vuota da Vibe-Trading")

        print(f"  [vibe] Risposta ricevuta ({len(response)} chars).")

    except Exception as exc:
        print(f"  [vibe] Errore: {exc}")
        print("  Fallback: agent_strategy.run_agent()")
        if proc is not None:
            _stop_server(proc)
        return _fallback_run_agent(
            anthropic_key=anthropic_key,
            openrouter_key=openrouter_key,
            openrouter_model=openrouter_model,
            asset=asset,
        )

    finally:
        if proc is not None:
            _stop_server(proc)
            print("  [vibe] Server arrestato.")

    # Parse extracted output
    try:
        code = _extract_python_code(response)
    except ValueError as e:
        print(f"  [vibe] Parsing codice fallito: {e}")
        print("  Fallback: agent_strategy.run_agent()")
        return _fallback_run_agent(
            anthropic_key=anthropic_key,
            openrouter_key=openrouter_key,
            openrouter_model=openrouter_model,
            asset=asset,
        )

    cfg = _extract_json_config(response) or dict(_DEFAULT_CONFIG)
    cfg.setdefault("strategy_name", f"VibeTrade {asset}")
    cfg.setdefault("commission",    0.0004)
    cfg.setdefault("slippage",      0.0001)
    cfg.setdefault("risk_per_trade", 0.01)

    report = (
        f"# Strategy Report — {asset}\n"
        f"*Generated by Vibe-Trading*\n\n"
        f"**Strategy**: {cfg.get('strategy_name')}\n"
        f"**Type**: {cfg.get('strategy_type')}\n"
        f"**SL**: {cfg.get('sl_mult')}×ATR  |  "
        f"**TP**: {cfg.get('tp_mult')}×ATR  |  "
        f"**Hours**: {cfg.get('active_hours')}\n\n"
        f"---\n\n{response}"
    )

    print(f"  [vibe] Strategia generata: {cfg.get('strategy_name')}")
    return cfg, code, report


if __name__ == "__main__":
    import agent_strategy as _ag

    asset    = os.environ.get("STRATEGY_ASSET",    "BTC-USD")
    ant_key  = os.environ.get("ANTHROPIC_API_KEY",  "")
    or_key   = os.environ.get("OPENROUTER_API_KEY", "")
    or_model = os.environ.get("OPENROUTER_MODEL",   "")

    print("=" * 60)
    print(f"  AGENT VIBE — {asset}")
    print("=" * 60)

    cfg, code, report = run_vibe_agent(
        asset=asset,
        anthropic_key=ant_key,
        openrouter_key=or_key,
        openrouter_model=or_model,
    )
    _ag.save_outputs(cfg, code, report)

    print("\nAgent Vibe completato.")
