"""
test_vibe_pipeline.py — Verifica end-to-end del pipeline vibe-trading.

Esegui da terminale con le tue credenziali:
  OPENROUTER_API_KEY=sk-or-v1-... python3 test_vibe_pipeline.py

Oppure con il Railway service:
  VIBE_TRADING_API_URL=https://your-service.up.railway.app \
  OPENROUTER_API_KEY=sk-or-v1-... \
  python3 test_vibe_pipeline.py

Output: stampa la strategia generata e la valida.
"""

import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b")
VIBE_URL        = os.environ.get("VIBE_TRADING_API_URL", "")
ASSET           = os.environ.get("STRATEGY_ASSET", "BTC-USD")

if not OPENROUTER_KEY and not ANTHROPIC_KEY:
    print("❌ Imposta OPENROUTER_API_KEY o ANTHROPIC_API_KEY nell'ambiente.")
    sys.exit(1)

# ── Step 1: build statistical context ────────────────────────────────────────
print("=" * 60)
print(f"  TEST PIPELINE VIBE-TRADING — {ASSET}")
print("=" * 60)

from agent_strategy import _build_context, _atr_stats
from agent_vibe import _build_vibe_prompt, _adapt_code, _post_process, _call_railway_api, _is_vibe_installed, _make_vibe_env, _run_cli, _fetch_code

ctx = _build_context(ASSET)
atr = _atr_stats(ASSET)
prompt = _build_vibe_prompt(ASSET)

print(f"\n[1] Contesto statistico ({len(ctx)} chars):")
for line in ctx.split("\n")[:12]:
    if line.strip():
        print(f"    {line}")
print(f"    ... ATR median={atr.get('median_atr_pct',0):.3f}%")

# ── Step 2: call vibe-trading (Railway or CLI) ────────────────────────────────
print(f"\n[2] Generazione strategia via {'Railway' if VIBE_URL else 'CLI locale'}…")
t0 = time.time()

raw_code = None

if VIBE_URL:
    print(f"    POST → {VIBE_URL}/generate")
    try:
        raw_code = _call_railway_api(
            prompt, VIBE_URL, ANTHROPIC_KEY, OPENROUTER_KEY, OPENROUTER_MODEL,
        )
        print(f"    ✅ Ricevuto codice ({len(raw_code)} chars) in {time.time()-t0:.1f}s")
    except Exception as e:
        print(f"    ❌ Railway error: {e}")
        sys.exit(1)

elif _is_vibe_installed():
    import tempfile
    print("    vibe-trading CLI locale")
    env, vibe_home = _make_vibe_env(ANTHROPIC_KEY, OPENROUTER_KEY, OPENROUTER_MODEL)
    if OPENROUTER_KEY:
        with open(os.path.join(vibe_home, ".env"), "w") as f:
            f.write(
                f"LANGCHAIN_PROVIDER=openrouter\n"
                f"LANGCHAIN_MODEL_NAME={OPENROUTER_MODEL}\n"
                f"OPENROUTER_API_KEY={OPENROUTER_KEY}\n"
                f"OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n"
            )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8", dir=vibe_home) as f:
        f.write(prompt)
        pfile = f.name
    try:
        data = _run_cli(pfile, env, cwd=vibe_home)
        run_id  = data.get("run_id", "")
        run_dir = data.get("run_dir", "")
        if run_dir and not os.path.isabs(run_dir):
            run_dir = os.path.join(vibe_home, run_dir)
        raw_code = _fetch_code(run_id, run_dir, env)
        print(f"    ✅ CLI completato in {time.time()-t0:.1f}s ({len(raw_code)} chars)")
    finally:
        try: os.unlink(pfile)
        except: pass
else:
    print("    ❌ Né VIBE_TRADING_API_URL né vibe-trading CLI disponibili.")
    sys.exit(1)

# ── Step 3: adapt + validate ──────────────────────────────────────────────────
print(f"\n[3] Adattamento e validazione codice…")
try:
    cfg, code, report = _post_process(
        raw_code, ASSET, "Test",
        ANTHROPIC_KEY, OPENROUTER_KEY, OPENROUTER_MODEL,
    )
    print(f"    ✅ Strategia valida!")
    print(f"    Nome    : {cfg.get('strategy_name')}")
    print(f"    Tipo    : {cfg.get('strategy_type')}")
    print(f"    SL      : {cfg.get('sl_mult')}×ATR")
    print(f"    TP      : {cfg.get('tp_mult')}×ATR")
    print(f"    Ore UTC : {cfg.get('active_hours')}")
    print(f"    Rationale: {cfg.get('rationale','')[:80]}")
except Exception as e:
    print(f"    ❌ Validazione fallita: {e}")
    print(f"    Codice raw (primi 300 chars): {raw_code[:300]!r}")
    sys.exit(1)

# ── Step 4: show code ─────────────────────────────────────────────────────────
print(f"\n[4] Codice generate_signals_agent (prime 20 righe):")
for i, line in enumerate(code.split("\n")[:20], 1):
    print(f"    {i:2d}: {line}")
if len(code.split("\n")) > 20:
    print(f"    ... ({len(code.split(chr(10)))} righe totali)")

print(f"\n{'='*60}")
print(f"  ✅ PIPELINE COMPLETATO in {time.time()-t0:.1f}s")
print(f"     Asset: {ASSET} | Engine: {'Railway' if VIBE_URL else 'CLI'}")
print(f"{'='*60}\n")
