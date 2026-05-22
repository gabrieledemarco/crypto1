# REPORT DI CODE QUALITY — Pareto Terminal
**Autore:** Principal Software Architect / Code Quality Assurance  
**Data:** 2026-05-22  
**Repository:** `gabrieledemarco/crypto1`  
**Stack:** FastAPI + DuckDB + Next.js 14 + TypeScript  

---

## Executive Summary

Il codebase è funzionalmente corretto nelle funzionalità principali (backtest, SSE streaming, Monte Carlo, WFO) e dimostra una buona separazione engine/router/frontend. Tuttavia sono stati identificati **2 problemi critici di sicurezza** (credenziali reali committate, CORS wildcard), **6 problemi ad alta priorità** che causano bug runtime o indeboliscono la security posture, e **9 problemi medi/bassi** che impattano stabilità e manutenibilità a lungo termine.

Il rischio più urgente riguarda credenziali Binance in chiaro nel repository Git (history permanente). Il secondo rischio riguarda un endpoint (`/assets/{ticker}/quant`) che presenta un bug SQL silenzioso che lo rende non funzionale su tutti gli ambienti.

**Score di salute del codice: 62/100** (bloccante su deploy production-grade per i punti critici)

---

## Mappa dei Problemi per Severità

| # | Severità | File | Problema |
|---|----------|------|---------|
| C1 | 🔴 CRITICA | `crypto_portfolio/portfolio/testapi.py` | Credenziali Binance hardcoded nel repository |
| C2 | 🔴 CRITICA | `api/main.py` | CORS `allow_origins=["*"]` senza autenticazione |
| A1 | 🟠 ALTA | `api/routers/assets.py:207` | Bug SQL: colonna `interval` non esiste nello schema DuckDB |
| A2 | 🟠 ALTA | `api/models.py` | Mancanza di validatori Pydantic su parametri critici (DoS, bad data) |
| A3 | 🟠 ALTA | `api/routers/vibe.py:168` | `os.environ[]` senza fallback → KeyError non gestito in prod |
| A4 | 🟠 ALTA | `api/routers/runs.py:59,114-115` | Pattern f-string SQL — anti-pattern strutturalmente pericoloso |
| A5 | 🟠 ALTA | `api/routers/runs.py:319` | `asyncio.get_event_loop()` deprecato in Python 3.10+ |
| A6 | 🟠 ALTA | `api/routers/runs.py:246-248` | Bootstrap CI: fallback sintetico silenzioso produce dati falsi |
| M1 | 🟡 MEDIA | `engine/strategy_core.py:20` | `warnings.filterwarnings("ignore")` globale mascherava errori numerici |
| M2 | 🟡 MEDIA | `api/routers/runs.py:41` | Memory leak: `_sse_queues` dict non ha cleanup |
| M3 | 🟡 MEDIA | Nessun endpoint | Nessun rate limiting su endpoint CPU-intensivi |
| M4 | 🟡 MEDIA | `engine/montecarlo.py:73` | `except Exception: pass` ingoia errori MC silenziosamente |
| M5 | 🟡 MEDIA | `api/routers/assets.py:149` | CAGR in `/stats` senza guardia su `days=0` (al contrario del engine) |
| M6 | 🟡 MEDIA | `api/routers/runs.py:443` | `mc_bars` senza upper bound → potenziale OOM |
| M7 | 🟡 MEDIA | `api/main.py` | `@app.on_event("startup")` deprecato in FastAPI 0.95+ |
| B1 | 🔵 BASSA | `api/routers/runs.py:269` | `uuid.uuid4()[:8]` — 8 caratteri, probabilità collisione non trascurabile |
| B2 | 🔵 BASSA | `api/routers/runs.py:382` | Stringa hardcoded `"V4 +GARCH+Costi"` per selezione versione — fragile |
| B3 | 🔵 BASSA | Multipli file `.py` | `sys.path.insert(0, ...)` ripetuto dentro funzioni invece che a livello modulo |

---

## Analisi Dettagliata e Refactoring

---

### 🔴 C1 — Credenziali Binance Hardcoded nel Repository

**File:** `crypto_portfolio/portfolio/testapi.py:7-8` e `tests.py:89`

**Codice problematico:**
```python
# crypto_portfolio/portfolio/testapi.py
api_key = 'x9KAJ0OLKL5CtGWccR7a2xnFeJcRzrHLDo0xYlt5fETPLc4D40lgLeOW03srpHrU'
api_secret = '4eFv0el5mR3Qc6FpdqXZr3OtxpX9NXWLmN0N8GOEoQxBJyjK6dTYkMsOqYIt2KlX'

# crypto_portfolio/portfolio/tests.py:89
api_key = "x9KAJ0OLKL5CtGWccR7a2xnFeJcRzrHLDo0xYlt5fETPLc4D40lgLeOW03srpHrU"
```

**Perché è critico:** Le credenziali Binance sono visibili a chiunque abbia accesso al repository (inclusi tutti i fork e la history Git). Chiunque può accedere all'account Binance associato, piazzare ordini, prelevare fondi. Git history è permanente: anche rimuovendoli ora, sono stati esposti.

**Fix immediato (ordine di esecuzione):**
1. **Revocare immediatamente** le chiavi API Binance dal pannello Binance → API Management
2. Generare nuove chiavi
3. Fare `git filter-branch` o `BFG Repo Cleaner` per rimuovere dalla history
4. Spostare su variabili d'ambiente

```python
# CORRETTO: crypto_portfolio/portfolio/testapi.py
import os

api_key = os.environ["BINANCE_API_KEY"]
api_secret = os.environ["BINANCE_API_SECRET"]
```

```bash
# .env (mai committato — aggiungere a .gitignore)
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

**Verifica .gitignore:**
```
.env
.env.*
*.env
```

---

### 🔴 C2 — CORS Wildcard Senza Autenticazione

**File:** `api/main.py:11-13`

**Codice problematico:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Perché è critico:** Con `allow_origins=["*"]`, qualsiasi sito web malevolo può fare richieste cross-origin all'API. In un'applicazione crypto, questo significa che una pagina phishing può inviare ordini, leggere dati privati di backtest, o lanciare backtest computazionalmente costosi a spese del server. In combinazione con l'assenza di autenticazione, l'intera API è esposta a CSRF e scraping.

**Codice corretto:**
```python
# api/main.py
import os

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000"  # dev fallback
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,  # no cookie-based auth in use
)
```

```bash
# Railway env vars
ALLOWED_ORIGINS=https://humorous-insight-production-340f.up.railway.app
```

---

### 🟠 A1 — Bug SQL: Colonna `interval` Non Esiste

**File:** `api/routers/assets.py:203-211`

**Codice problematico:**
```python
@router.get("/{ticker}/quant")
def get_quant_stats(ticker: str, interval: str = Query("1h")):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker = ? AND interval = ? ORDER BY ts ASC",
            #                                               ^^^^^^^^ COLONNA NON ESISTE
            [ticker.replace("-USD", ""), interval]
        ).fetchall()
    except Exception:
        rows = []  # swallowed silently → sempre 404
```

**Perché è un bug:** La tabella `assets` (definita in `api/db.py`) ha colonne: `ticker, source, ts, open, high, low, close, volume`. La colonna `interval` non esiste. DuckDB genera un errore che viene catturato dal `except Exception: rows = []`, quindi l'endpoint restituisce sempre 404 in modo silenzioso. L'endpoint è completamente non funzionale su qualsiasi ambiente reale.

**Codice corretto:**
```python
@router.get("/{ticker}/quant")
def get_quant_stats(ticker: str, interval: str = Query("1h")):
    from engine.quant_stats import compute_hurst, test_stationarity, compute_var_cvar, rolling_metrics
    conn = get_conn()
    source_key = f"yfinance:{interval}"
    
    if interval == "1d":
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker=? AND (source=? OR source=?) ORDER BY ts ASC",
            [ticker, source_key, "yfinance"]
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT close FROM assets WHERE ticker=? AND source=? ORDER BY ts ASC",
            [ticker, source_key]
        ).fetchall()
    
    if not rows or len(rows) < 50:
        raise HTTPException(404, f"No data for {ticker}/{interval} (need ≥50 bars)")
    
    prices = np.array([r[0] for r in rows], dtype=float)
    rets = np.diff(np.log(prices[prices > 0]))
    return {
        "ticker": ticker,
        "interval": interval,
        "n_bars": len(prices),
        "hurst": compute_hurst(prices),
        "stationarity": test_stationarity(prices),
        "var_cvar": compute_var_cvar(rets),
        "rolling": rolling_metrics(prices),
    }
```

---

### 🟠 A2 — Mancanza di Validatori Pydantic (DoS + Bad Data)

**File:** `api/models.py`

**Codice problematico:**
```python
class RunParams(BaseModel):
    ticker: str = "BTC-USD"          # nessun limite di lunghezza
    direction: str = "ALL"            # nessuna validazione enum
    mc_sims: int = 1000              # nessun max → mc_sims=10_000_000 = OOM
    active_hours: list[int] = [6, 22] # nessun bounds check
    risk_per_trade: float = 0.01     # nessun range
```

**Perché è un problema:** Un attaccante (o semplicemente un bug frontend) può inviare `mc_sims=10000000` che alloca una matrice numpy di miliardi di celle causando OOM/crash del pod Railway. `direction="DROP TABLE runs"` non causa SQL injection (la colonna non è usata in query), ma valori non previsti causano comportamenti undefined nel engine. `active_hours=[-100, 500]` causa `hour >= -100` sempre true, invalidando il filtro.

**Codice corretto:**
```python
# api/models.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
import re

VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"}

class RunParams(BaseModel):
    ticker: str = Field("BTC-USD", min_length=1, max_length=20)
    timeframe: str = Field("1h", pattern=r"^(1m|5m|15m|30m|1h|4h|1d|1wk|1mo)$")
    sl_mult: float = Field(2.0, ge=0.1, le=20.0)
    tp_mult: float = Field(5.0, ge=0.1, le=30.0)
    active_hours: list[int] = Field([6, 22], min_length=2, max_length=2)
    risk_per_trade: float = Field(0.01, ge=0.001, le=0.1)
    commission: float = Field(0.0004, ge=0.0, le=0.01)
    slippage: float = Field(0.0001, ge=0.0, le=0.005)
    direction: Literal["ALL", "LONG", "SHORT"] = "ALL"
    run_wfo: bool = True
    run_sweep: bool = True
    run_mc: bool = True
    mc_sims: int = Field(1000, ge=100, le=10_000)
    mc_bars: Optional[int] = Field(None, ge=1, le=100_000)

    @field_validator("ticker")
    @classmethod
    def sanitize_ticker(cls, v: str) -> str:
        if not re.match(r"^[A-Z0-9\-\^=\.]+$", v):
            raise ValueError("ticker contains invalid characters")
        return v

    @field_validator("active_hours")
    @classmethod
    def validate_hours(cls, v: list[int]) -> list[int]:
        if len(v) != 2 or not (0 <= v[0] <= 23) or not (0 <= v[1] <= 23):
            raise ValueError("active_hours must be two values in [0, 23]")
        return v
```

---

### 🟠 A3 — `os.environ[]` Senza Fallback in Produzione

**File:** `api/routers/vibe.py:168`

**Codice problematico:**
```python
async def _claude_stream(body: VibeGenerateRequest):
    # ...
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ KeyError se variabile assente → eccezione
    # in un generatore asincrono, l'eccezione rompe lo stream silenziosamente
```

**Perché è un problema:** `os.environ["KEY"]` lancia `KeyError` se la variabile non è impostata. All'interno di un generatore asincrono (usato da `StreamingResponse`), questa eccezione non viene trasformata in HTTP 500 ma causa la chiusura prematura dello stream. Il client frontend vede lo stream che si chiude senza dati e senza messaggio di errore, rendendo il debug impossibile.

**Codice corretto:**
```python
# api/routers/vibe.py — top-level, non dentro la funzione
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

async def _claude_stream(body: VibeGenerateRequest):
    if not _ANTHROPIC_KEY:
        yield f"data: {json.dumps({'type': 'error', 'text': 'ANTHROPIC_API_KEY not configured'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'config': {}, 'code': ''})}\n\n"
        return
    
    client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
    # resto della funzione invariato
```

---

### 🟠 A4 — Pattern f-string SQL Strutturalmente Pericoloso

**File:** `api/routers/runs.py:59` e `114-115`

**Codice problematico:**
```python
# Riga 59: f-string per clause WHERE
rows = conn.execute(f"""
    SELECT r.id, ...
    FROM runs r
    LEFT JOIN run_results rr ON r.id = rr.run_id
    {where}              # ← interpolazione f-string nel corpo SQL
    ORDER BY r.created_at DESC
""", args).fetchall()

# Righe 114-115: f-string per IN clause
placeholders = ",".join(["?" for _ in ids])
conn.execute(f"DELETE FROM run_results WHERE run_id IN ({placeholders})", ids)
conn.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", ids)
```

**Perché è un problema:** Anche se attualmente sicuro (le variabili interpolate sono stringhe fisse o placeholder `?`), questo pattern stabilisce una convenzione nel codebase. Il primo sviluppatore che estende questo codice usando f-string con input utente produce SQL injection. Nella riga 59, `{where}` è tecnicamente safe, ma se domani viene aggiunto un filtro basato su input utente (es. `WHERE name LIKE '{search}'`) la vulnerabilità è immediata.

**Codice corretto:**
```python
# Riga 59: eliminare f-string usando WHERE condizionale parametrizzato
if strategy_id:
    query = """
        SELECT r.id, r.name, r.ticker, r.timeframe, r.status, r.params, r.created_at,
               r.strategy_id, rr.metrics, rr.equity
        FROM runs r
        LEFT JOIN run_results rr ON r.id = rr.run_id
        WHERE r.strategy_id = ?
        ORDER BY r.created_at DESC
    """
    rows = conn.execute(query, [strategy_id]).fetchall()
else:
    query = """
        SELECT r.id, r.name, r.ticker, r.timeframe, r.status, r.params, r.created_at,
               r.strategy_id, rr.metrics, rr.equity
        FROM runs r
        LEFT JOIN run_results rr ON r.id = rr.run_id
        ORDER BY r.created_at DESC
    """
    rows = conn.execute(query).fetchall()

# Righe 114-115: usare executemany invece di IN clause dinamica
if ids:
    for run_id in ids:
        conn.execute("DELETE FROM run_results WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM runs WHERE id = ?", [run_id])
    # Alternativa efficiente con transazione:
    # conn.executemany("DELETE FROM run_results WHERE run_id = ?", [[i] for i in ids])
    # conn.executemany("DELETE FROM runs WHERE id = ?", [[i] for i in ids])
```

---

### 🟠 A5 — `asyncio.get_event_loop()` Deprecato

**File:** `api/routers/runs.py:319`

**Codice problematico:**
```python
# runs.py:319 (e identico pattern in runs.py:513)
loop = asyncio.get_event_loop()
# ...
result = await loop.run_in_executor(pool, _sync_backtest_pipeline, df, params, push)
```

**Perché è un problema:** `asyncio.get_event_loop()` è deprecato in Python 3.10+ e rimosso in 3.12 in certi contesti. Negli ambienti dove non esiste un loop corrente nel thread, lancia `DeprecationWarning` o, in Python 3.12, `RuntimeError`. L'alternativa corretta all'interno di una coroutine `async def` è `asyncio.get_running_loop()`.

**Codice corretto:**
```python
# runs.py:319
loop = asyncio.get_running_loop()  # safe dentro async def, non deprecato
result = await loop.run_in_executor(pool, _sync_backtest_pipeline, df, params, push)
```

---

### 🟠 A6 — Bootstrap CI: Fallback Silenzioso con Dati Falsi

**File:** `api/routers/runs.py:246-248`

**Codice problematico:**
```python
try:
    # scipy bootstrap...
    sharpe_ci = (float(bs_sharpe.confidence_interval.low), ...)
    cagr_ci   = (float(bs_cagr.confidence_interval.low),   ...)
except Exception:
    # Se il bootstrap fallisce, inventa bounds che sembrano reali
    sharpe_ci = (sharpe_point * 0.7, sharpe_point * 1.3)
    cagr_ci   = (cagr_point * 0.7,   cagr_point * 1.3)
```

**Perché è un problema:** Il fallback produce confidenze sintetiche (±30% arbitrario) che vengono mostrate nel frontend come se fossero calcoli statistici reali. Un utente che basa decisioni di trading su questi dati riceve informazioni false senza alcuna indicazione che il bootstrap ha fallito. In un'applicazione finanziaria, questo è un problema di integrità dei dati.

**Codice corretto:**
```python
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bs_sharpe = sp_bootstrap(...)
        bs_cagr   = sp_bootstrap(...)
    sharpe_ci = (float(bs_sharpe.confidence_interval.low), float(bs_sharpe.confidence_interval.high))
    cagr_ci   = (float(bs_cagr.confidence_interval.low),   float(bs_cagr.confidence_interval.high))
    ci_method = "bootstrap"
except Exception as e:
    # Segnalare il fallimento con bounds null, non con dati inventati
    import logging
    logging.warning(f"Bootstrap CI failed for run {run_id}: {e}")
    sharpe_ci = (None, None)
    cagr_ci   = (None, None)
    ci_method = "unavailable"

return {
    "run_id":    run_id,
    "n_returns": n,
    "ci_method": ci_method,  # il frontend mostra "N/A" se unavailable
    "sharpe": {
        "point":   round(sharpe_point, 3),
        "ci_low":  round(sharpe_ci[0], 3) if sharpe_ci[0] is not None else None,
        "ci_high": round(sharpe_ci[1], 3) if sharpe_ci[1] is not None else None,
    },
    # ... idem per cagr_pct
}
```

---

### 🟡 M1 — `warnings.filterwarnings("ignore")` Globale

**File:** `engine/strategy_core.py:20`

**Codice problematico:**
```python
import warnings
warnings.filterwarnings("ignore")  # ← maschera TUTTI i warning a livello processo
```

**Perché è un problema:** Questa chiamata si propaga all'intero processo Python. Maschera warning critici come `RuntimeWarning: overflow encountered in double_scalars` (valori infiniti in calcoli CAGR), `ConvergenceWarning` dal fit GARCH, e deprecation warning di NumPy/Pandas che segnalano breaking changes futuri.

**Codice corretto:**
```python
# engine/strategy_core.py — filtrare solo ciò che è rumore noto
import warnings

# Sopprimere solo i warning specifici e prevedibili del GARCH fit
warnings.filterwarnings("ignore", message=".*Maximum Likelihood.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*covariance of the parameters.*", category=RuntimeWarning)
```

---

### 🟡 M2 — Memory Leak: `_sse_queues` Senza Cleanup

**File:** `api/routers/runs.py:33-41`

**Codice problematico:**
```python
_sse_queues: dict[str, asyncio.Queue] = {}

@router.get("/{run_id}/stream")
async def stream_run(run_id: str):
    queue = _sse_queues.setdefault(run_id, asyncio.Queue())
    # La queue viene creata ma mai rimossa
    # Ogni run aggiunge una entry permanente al dict
```

**Perché è un problema:** Ogni run crea una `asyncio.Queue` che rimane nel dizionario per tutta la vita del processo. Con utilizzo intensivo (centinaia di run), il dict cresce illimitatamente. Le queue contengono oggetti in-memory e i messaggi non consumati.

**Codice corretto:**
```python
_sse_queues: dict[str, asyncio.Queue] = {}

async def stream_run(run_id: str):
    queue = _sse_queues.setdefault(run_id, asyncio.Queue())
    async def generator():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("phase") in ("done", "error"):
                    break
        finally:
            # Cleanup: rimuovere la queue quando il client si disconnette o il run termina
            _sse_queues.pop(run_id, None)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

---

### 🟡 M3 — Nessun Rate Limiting su Endpoint CPU-Intensivi

**File:** `api/main.py` (mancante)

**Perché è un problema:** Gli endpoint `POST /runs` (backtest completo: GARCH + WFO + sweep + MC), `GET /assets/{ticker}/garch-forecast` (fit GARCH su tutti i dati), `GET /runs/{id}/bootstrap-ci` (500 resamples scipy) richiedono secondi di CPU. Senza rate limiting, un singolo client può paralizzare il server Railway con richieste in loop. Il `ThreadPoolExecutor(max_workers=2)` in vibe.py limita la concorrenza per Vibe ma non per backtest e GARCH.

**Codice corretto:**
```python
# api/main.py — aggiungere slowapi
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# api/routers/runs.py
from api.main import limiter
from fastapi import Request

@router.post("")
@limiter.limit("10/minute")  # max 10 backtest/minuto per IP
async def create_run(request: Request, body: RunCreate):
    ...

# api/routers/assets.py
@router.get("/{ticker}/garch-forecast")
@limiter.limit("20/minute")
def get_garch_forecast(request: Request, ticker: str, ...):
    ...
```

```bash
pip install slowapi
```

---

### 🟡 M4 — `except Exception: pass` in Monte Carlo

**File:** `engine/montecarlo.py:73-74`

**Codice problematico:**
```python
for _ in range(n_sims):
    try:
        # simulazione...
    except Exception:
        pass  # iterazione ignorata silenziosamente
```

**Perché è un problema:** Se tutte le simulazioni falliscono per un bug o edge case (es. array di PnL vuoto), il risultato finale è un DataFrame vuoto. Il chiamante non ha modo di sapere che il 100% delle simulazioni è fallito. Il frontend mostra grafici vuoti senza errori.

**Codice corretto:**
```python
failed = 0
for _ in range(n_sims):
    try:
        # simulazione...
    except Exception as e:
        failed += 1
        if failed == 1:  # log solo il primo errore
            import logging
            logging.warning(f"MC simulation error (sample): {e}")

if failed > n_sims * 0.5:
    raise RuntimeError(f"Monte Carlo failed on {failed}/{n_sims} simulations")
```

---

### 🟡 M5 — CAGR in `/assets/stats` Senza Guardia su `days=0`

**File:** `api/routers/assets.py:149`

**Codice problematico:**
```python
total_ret = closes[-1] / closes[0]
n_hours   = len(closes)
cagr      = (total_ret ** (ann_factor / n_hours) - 1) * 100
# Se n_hours == 1, esponente = ann_factor (es. 8760 per 1h) → overflow
# Se total_ret == 0, potenza di 0 → -100%
# Non ha il clamp ±999% che invece esiste in engine/strategy_core.py
```

**Codice corretto:**
```python
n_hours = max(len(closes), 1)
total_ret = closes[-1] / closes[0] if closes[0] > 0 else 1.0
raw_cagr = (total_ret ** (ann_factor / n_hours) - 1) * 100
cagr = max(min(raw_cagr, 999.0), -99.9)  # consistente con engine/strategy_core.py
```

---

### 🟡 M6 — `mc_bars` Senza Upper Bound → Potenziale OOM

**File:** `api/routers/runs.py:443` e `engine/montecarlo.py`

**Codice problematico:**
```python
n_bars = int(mc_bars_raw) if (mc_bars_raw and int(mc_bars_raw) > 0) else None
# ...
eq_mat = np.zeros((n_sims, n_bars))  # n_sims=1000, n_bars=1_000_000 → 8 GB RAM
```

**Fix:** già gestito da `mc_bars: Optional[int] = Field(None, ge=1, le=100_000)` nel fix A2.

---

### 🟡 M7 — `@app.on_event("startup")` Deprecato

**File:** `api/main.py:17-19`

**Codice problematico:**
```python
@app.on_event("startup")
def startup():
    get_conn()
```

**Codice corretto (FastAPI 0.93+):**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_conn()  # startup
    yield
    # teardown (opzionale: conn.close())

app = FastAPI(title="Pareto API", version="0.2.0", lifespan=lifespan)
```

---

### 🔵 B1 — UUID a 8 Caratteri per Run ID

**File:** `api/routers/runs.py:269`

**Codice problematico:**
```python
run_id = str(uuid.uuid4())[:8]  # solo 8 caratteri hex = 4 miliardi di combinazioni
```

**Probabilità collisione** con 10.000 run: ~1.2% (birthday paradox). Con uso intensivo, le collisioni sono statisticamente possibili e causerebbero sovrascrittura silenziosa dei dati.

**Codice corretto:**
```python
run_id = str(uuid.uuid4()).replace("-", "")[:12]  # 12 caratteri = 281 trilioni di combinazioni
# oppure usare l'UUID completo: run_id = str(uuid.uuid4())
```

---

### 🔵 B2 — Selezione Versione con Stringa Hardcoded

**File:** `api/routers/runs.py:382`

**Codice problematico:**
```python
best_key = "V4 +GARCH+Costi"
if "V_Agent" in versions and "result" in versions.get("V_Agent", {}):
    best_key = "V_Agent"
best = versions.get(best_key, list(versions.values())[0])
```

**Perché è fragile:** Se il nome della versione cambia in `engine/backtest.py`, questo codice smette di trovare la versione corretta e cade nel fallback `list(versions.values())[0]` senza errore. Il nome è duplicato in almeno 2 punti.

**Codice corretto:**
```python
# engine/backtest.py — aggiungere costante esportata
BEST_VERSION_KEY = "V4 +GARCH+Costi"

# api/routers/runs.py
from engine.backtest import BEST_VERSION_KEY

best_key = "V_Agent" if ("V_Agent" in versions and "result" in versions["V_Agent"]) else BEST_VERSION_KEY
best = versions.get(best_key)
if best is None:
    raise ValueError(f"Version key '{best_key}' not found. Available: {list(versions.keys())}")
```

---

### 🔵 B3 — `sys.path.insert` Ripetuto Dentro Funzioni

**File:** `api/routers/runs.py:18-19`, `360`, `497-498`, `526-527`

**Codice problematico:**
```python
def _sync_backtest_pipeline(df, params):
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from engine.strategy_core import ...
```

**Perché è un problema:** `sys.path.insert(0, ...)` viene chiamato ogni volta che la funzione è eseguita, aggiungendo duplicati al path. Modifica il global state del processo in un thread pool worker.

**Codice corretto:**
```python
# api/routers/runs.py — a livello modulo, una sola volta
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from engine.strategy_core import compute_indicators_v2, compute_metrics
from engine.backtest import run_versions, run_wfo, run_optimization, INITIAL_CAPITAL
from engine.montecarlo import run_bootstrap, run_stress
# Tutti gli import a livello modulo → nessun sys.path.insert nelle funzioni
```

---

## Roadmap — Action Plan

### Sprint 1 — Immediato (Entro 24h)

| # | Azione | File | Impatto |
|---|--------|------|---------|
| 1 | **Revocare le chiavi Binance** dal pannello Binance | — | Blocca accesso non autorizzato |
| 2 | Rimuovere credenziali dalla git history con BFG | `crypto_portfolio/portfolio/testapi.py`, `tests.py` | Elimina esposizione permanente |
| 3 | Aggiungere `.env` al `.gitignore`, spostare su env vars | `crypto_portfolio/portfolio/` | Previene re-esposizione |
| 4 | Fix CORS: lista origin esplicita da env var | `api/main.py` | Chiude vettore CSRF |

### Sprint 2 — Alta Priorità (Entro 1 settimana)

| # | Azione | File | Impatto |
|---|--------|------|---------|
| 5 | Fix SQL query in `/quant` (colonna `interval` inesistente) | `api/routers/assets.py` | Ripristina endpoint funzionante |
| 6 | Aggiungere validatori Pydantic (A2) | `api/models.py` | Previene DoS e bad data |
| 7 | Fix `os.environ[]` → `os.getenv()` con error response pulita | `api/routers/vibe.py` | Migliora UX su errori di config |
| 8 | Eliminare f-string SQL, usare query parametrizzate | `api/routers/runs.py` | Hardening strutturale |
| 9 | Fix `asyncio.get_event_loop()` → `get_running_loop()` | `api/routers/runs.py` | Compatibilità Python 3.10+ |
| 10 | Fix Bootstrap CI fallback: restituire `null` invece di bounds finti | `api/routers/runs.py` | Integrità dati finanziari |

### Sprint 3 — Media Priorità (Entro 2 settimane)

| # | Azione | File | Impatto |
|---|--------|------|---------|
| 11 | Aggiungere `slowapi` per rate limiting | `api/main.py`, `api/routers/` | Protezione DoS |
| 12 | Fix `warnings.filterwarnings` a scope limitato | `engine/strategy_core.py` | Debugging numerico |
| 13 | Fix cleanup `_sse_queues` nel finally del generator | `api/routers/runs.py` | Memory stability |
| 14 | Fix `except Exception: pass` in Monte Carlo | `engine/montecarlo.py` | Observability |
| 15 | Aggiungere guardia `days=0` in `/assets/stats` | `api/routers/assets.py` | Numerica stabile |
| 16 | Fix `mc_bars` upper bound in models | `api/models.py` | Previene OOM |
| 17 | Migrare `on_event` → `lifespan` | `api/main.py` | Compat FastAPI moderno |

### Sprint 4 — Bassa Priorità (Backlog)

| # | Azione | File | Impatto |
|---|--------|------|---------|
| 18 | Estendere run ID a 12+ caratteri | `api/routers/runs.py` | Collision safety |
| 19 | Estrarre `BEST_VERSION_KEY` come costante | `engine/backtest.py`, `api/routers/runs.py` | Manutenibilità |
| 20 | Rimuovere `sys.path.insert` dalle funzioni | Tutti i router | Clean imports |

---

*Report generato tramite analisi statica del codebase locale. Nessun dato è stato inviato a servizi esterni.*
