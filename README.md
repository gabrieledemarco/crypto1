# Pareto Terminal

A quantitative backtesting platform for systematic crypto and equity strategies. Combines a FastAPI computation engine with a Next.js dashboard to run strategy backtests, walk-forward optimization, Monte Carlo simulation, and parameter sweeps — all from a single UI.

---

## Architecture

```
Browser (Next.js 14)
    │
    └─ /app/api/[...path]/route.ts  ← runtime proxy
           │
           ▼
    FastAPI (Python 3.11)
           │
           ├─ DuckDB        — metadata, run results, strategy library
           ├─ Parquet store — M1 OHLCV bars (Snappy, monthly files)
           └─ engine/       — pure computation (backtest, WFO, MC)
```

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React, TypeScript, Zustand, React Query |
| API | FastAPI 0.111, Uvicorn, Pydantic v2 |
| Computation | NumPy, Pandas, arch (GARCH), hmmlearn (HMM regimes), vectorbt |
| Storage | DuckDB 0.10, Apache Parquet, PyArrow |
| Data | yfinance, ccxt, alpaca-py |
| Deploy | Docker Compose (local) · Railway (production) |

---

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **Docker** + Docker Compose (for the one-command setup)

---

## Quick Start — Docker Compose

The fastest way to run the full stack locally.

```bash
git clone https://github.com/gabrieledemarco/crypto1.git
cd crypto1

# Optional: set your Anthropic API key for the Vibe screen
export ANTHROPIC_API_KEY=sk-ant-...

docker compose up --build
```

| Service | URL |
|---|---|
| Web dashboard | http://localhost:3000 |
| API (FastAPI) | http://localhost:8099 |
| API docs (Swagger) | http://localhost:8099/docs |

Data is persisted in a Docker volume (`pareto_data`) mounted at `/data`.

---

## Manual Setup

### 1. API (FastAPI)

```bash
cd crypto1

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r api/requirements.txt

# Start the API
uvicorn api.main:app --host 0.0.0.0 --port 8099 --reload
```

The API will be available at `http://localhost:8099`.  
Interactive docs: `http://localhost:8099/docs`.

### 2. Web (Next.js)

```bash
cd web
npm install

# Tell the frontend where the API is
echo "API_URL=http://localhost:8099" > .env.local

npm run dev
```

The dashboard will be available at `http://localhost:3000`.

---

## Environment Variables

### API

| Variable | Default | Description |
|---|---|---|
| `DUCKDB_PATH` | `/tmp/pareto.db` | Path to the DuckDB metadata database |
| `M1_DATA_DIR` | `/data/m1_history` | Root directory for Parquet OHLCV files |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins (comma-separated) |
| `ANTHROPIC_API_KEY` | — | Required for the Vibe (AI strategy) screen |
| `USE_NAUTILUS_ENGINE` | `0` | Set to `1` to enable NautilusTrader high-fidelity engine |
| `NAUTILUS_TIMEOUT` | `10` | Seconds before NautilusTrader is force-killed if it hangs |
| `DISABLE_VBT` | `0` | Set to `1` to disable vectorbt and always use the Python loop |
| `PREWARM_TICKERS` | — | Comma-separated tickers to pre-warm the data cache on startup |

### Web

| Variable | Default | Description |
|---|---|---|
| `API_URL` | — | Internal API URL (server-side proxy, e.g. `http://api:8099`) |
| `NEXT_PUBLIC_API_URL` | — | Public API URL fallback (client-side) |

---

## Usage

### 1. Download historical data

Before running a backtest, you need OHLCV data for your ticker. Open the **Setup** screen and expand the **BACKFILL** panel:

1. Select a **ticker** (e.g. `BNB-USD`) and **timeframe** (e.g. `1h`)
2. Set the date range
3. Click **▶ AVVIA BACKFILL**

The progress log shows the download status in real time. Data is stored as monthly Parquet files.

Alternatively, use the API directly:

```bash
curl -X POST http://localhost:8099/assets/backfill \
  -H "Content-Type: application/json" \
  -d '{"ticker": "BTC-USD", "interval": "1h", "start_date": "2022-01-01", "end_date": "2024-12-31"}'
```

### 2. Run a backtest

In the **Setup** screen:

1. Configure strategy parameters (SL/TP multipliers, risk per trade, active hours, etc.)
2. Toggle **WFO**, **SWEEP**, **MC** options as needed
3. Click **▶ RUN**

The **Pipeline Log** box shows each phase in real time (indicators, versions, walk-forward, sweep, Monte Carlo). Results are automatically available in the other screens once the run completes.

### 3. Explore results

| Screen | Description |
|---|---|
| **Dashboard** | Summary metrics and equity curve for the active run |
| **Equity** | Full equity curve with drawdown overlay |
| **Trades** | Paginated trade log with filters |
| **WFO** | Walk-forward fold results (IS vs OOS Sharpe, efficiency factor) |
| **Sweep** | Parameter grid heatmap (SL × TP × hours) |
| **Monte Carlo** | Bootstrap equity paths, VaR/CVaR, daily drawdown probabilities |
| **Underwater** | Drawdown duration and recovery analysis |
| **Assets** | Available data inventory |
| **Library** | Saved strategies and past runs |
| **Vibe** | AI-assisted strategy generation via Claude |

---

## Running Tests

```bash
# From the repo root
pip install pytest pytest-asyncio
pytest tests/ -v
```

The engine tests (`tests/test_engine_backtest.py`) run without any external services and cover the backtest loop, walk-forward splitter, and metric calculations.

---

## Deployment — Railway

The repository ships with a `railway.toml` that deploys two services:

| Service | Description |
|---|---|
| `api` | FastAPI + computation engine |
| `web` | Next.js frontend |

Required Railway environment variables:

```
# API service
DUCKDB_PATH=/data/pareto.db
M1_DATA_DIR=/data/m1_history
ALLOWED_ORIGINS=https://your-web-domain.railway.app
ANTHROPIC_API_KEY=sk-ant-...

# Web service
API_URL=https://your-api-domain.railway.app
```

Attach a Railway **Volume** to the API service at `/data` to persist the database and Parquet files across deploys.

---

## Project Structure

```
crypto1/
├── api/                    # FastAPI application
│   ├── main.py             # App setup, CORS, router mounts
│   ├── db.py               # DuckDB connection (thread-local)
│   ├── models.py           # Pydantic request/response schemas
│   └── routers/
│       ├── runs.py         # Backtest execution + SSE progress stream
│       ├── assets.py       # Data management, backfill
│       ├── strategies.py   # Strategy library CRUD
│       ├── analysis.py     # Statistical analysis endpoints
│       ├── pipeline.py     # Multi-strategy pipelines
│       └── vibe.py         # Claude AI strategy proxy
│
├── engine/                 # Pure computation — no IO, no FastAPI
│   ├── strategy_core.py    # GARCH, HMM regimes, indicators, backtest loop
│   ├── backtest.py         # run_versions, run_wfo, run_optimization
│   ├── backtest_vbt.py     # vectorbt fast path (~20-50× sweep speedup)
│   ├── montecarlo.py       # Bootstrap MC, stress scenarios
│   ├── indicators.py       # Technical indicator dispatcher
│   ├── quant_stats.py      # Hurst, stationarity, VaR/CVaR
│   ├── nautilus_engine.py  # NautilusTrader wrapper (optional)
│   ├── safe_exec.py        # AST-based strategy code sandbox
│   └── storage/
│       ├── parquet_store.py  # M1 Parquet persistence
│       └── fast_loader.py    # DuckDB + warm LRU cache
│
├── web/                    # Next.js 14 frontend
│   ├── app/                # App Router pages
│   ├── components/screens/ # One component per screen
│   ├── hooks/              # useRun, useSSE, useAssets, usePreview
│   ├── store/              # Zustand global state
│   └── lib/                # API client, fixtures, types
│
├── tests/                  # pytest test suite
├── scripts/                # CLI utilities (seed, migrate, pipeline)
├── Dockerfile.api
├── Dockerfile.web
├── docker-compose.yml
└── railway.toml
```

---

## License

MIT
