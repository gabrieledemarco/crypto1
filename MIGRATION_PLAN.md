# MIGRATION PLAN — Pareto Terminal
## Streamlit → Next.js + FastAPI, hosted on Railway

---

## 0 · Summary

Refactoring the existing Streamlit crypto backtesting app into a dense, keyboard-driven
web terminal matching the `design_handoff_pareto_terminal/` spec.

- **Frontend**: Next.js 14 (App Router) + TypeScript + Zustand + TanStack Query + visx
- **Backend**: FastAPI (Python) reusing existing engine code verbatim
- **DB**: DuckDB single-file for runs/trades/assets
- **Realtime**: SSE for backtest progress
- **LLM**: Anthropic SDK proxied through backend
- **Hosting**: Railway — two services (api + web) from the same repo

---

## 1 · Monorepo layout

```
crypto1/
├── api/                          ← FastAPI backend
│   ├── main.py                   ← app entry, router mount
│   ├── routers/
│   │   ├── runs.py               ← /runs CRUD + SSE stream
│   │   ├── assets.py             ← /assets fetch + stats
│   │   ├── strategies.py         ← /strategies library
│   │   └── vibe.py               ← /vibe/generate (Claude proxy)
│   ├── db.py                     ← DuckDB connection + schema init
│   ├── models.py                 ← Pydantic schemas
│   └── requirements.txt
│
├── engine/                       ← Python engine (extracted from btc_analysis/)
│   ├── __init__.py
│   ├── strategy_core.py          ← moved verbatim (backtest_v2, compute_metrics…)
│   ├── backtest.py               ← run_versions, run_wfo, run_optimization, _apply_cfg_overrides
│   ├── montecarlo.py             ← run_bootstrap, run_stress
│   ├── validation.py             ← sharpe_ci_bootstrap, permutation_test…
│   ├── trade_analysis.py         ← direction_stats, hourly_stats, streak_stats…
│   ├── agent_strategy.py         ← _call_anthropic, _call_openrouter, run_agent…
│   ├── agent_vibe.py             ← run_vibe_agent, _quick_backtest…
│   └── providers/
│       ├── yfinance_client.py    ← Provider(fetch) using yfinance
│       └── alpaca_client.py      ← Provider(fetch) using alpaca-trade-api
│
├── web/                          ← Next.js 14 frontend
│   ├── app/
│   │   ├── layout.tsx            ← shell: topbar + sidebar + statusbar + hotkeys
│   │   ├── page.tsx              ← redirect → /dashboard
│   │   ├── dashboard/page.tsx
│   │   ├── assets/page.tsx
│   │   ├── library/page.tsx
│   │   ├── vibe/page.tsx
│   │   ├── setup/page.tsx
│   │   ├── equity/page.tsx
│   │   ├── trades/page.tsx
│   │   ├── sweep/page.tsx
│   │   ├── underwater/page.tsx
│   │   ├── mc/page.tsx
│   │   └── compare/page.tsx
│   ├── components/
│   │   ├── shell/                ← TopBar, Sidebar, StatusBar, Palette, HelpToast, Toast
│   │   ├── charts/               ← EquityChart, DrawdownChart, MCFanChart, SweepHeatmap…
│   │   └── screens/              ← one folder per screen
│   ├── store/
│   │   └── index.ts              ← Zustand store (runs, screen, paletteOpen, compareIds…)
│   ├── hooks/
│   │   ├── useRun.ts             ← TanStack Query wrappers
│   │   ├── useHotkeys.ts         ← global keyboard map
│   │   └── useSSE.ts             ← SSE subscription for backtest progress
│   ├── lib/
│   │   ├── api.ts                ← typed fetch helpers → /api proxy → FastAPI
│   │   ├── tokens.css            ← design tokens verbatim from spec
│   │   └── fixtures.ts           ← pareto-data.js ported to TypeScript (for tests)
│   ├── next.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── btc_analysis/                 ← KEPT as-is (current Streamlit app, not deleted yet)
│   └── app.py                    ← will be retired after milestone 3 parity check
│
├── design_handoff_pareto_terminal/   ← read-only reference
│
├── railway.toml                  ← Railway multi-service config
├── Dockerfile.api                ← FastAPI container
├── Dockerfile.web                ← Next.js container
└── MIGRATION_PLAN.md             ← this file
```

---

## 2 · Streamlit → Screen mapping

| Streamlit section | Target screen | Notes |
|---|---|---|
| Tab 1 Price & Returns (candlestick, log-returns, histogram, rolling vol) | **ASSETS** `g·a` | All quant charts move here; asset selector becomes universe grid |
| Sidebar asset selector + download buttons | **ASSETS** `g·a` | "+ ADD ASSET" card with source pill (yfinance/alpaca) |
| Tab 2 Strategy V5 (equity curve, drawdown, trades table) | **EQUITY** `g·e` + **TRADES** `g·t` | Equity/drawdown split into dedicated screens; crosshair sync required |
| Tab 3 Walk-Forward | **EQUITY** `g·e` (IS/OOS metrics strip) | WFO fold results shown as IS|OOS metric pairs, no separate screen |
| Tab 4 Monte Carlo | **MONTE CARLO** `g·m` | Fan chart + percentile outcomes + final/DD histograms |
| Tab 5 Multi-Asset | **COMPARE** `g·c` | Multi-run overlay; correlation at bottom |
| Tab 6 Agent Strategy + strategy catalog | **LIBRARY** `g·l` + **VIBE TRADING** `g·v` | Vibe = generation; Library = saved strategies |
| Tab 7 Trade Analysis (direction/hourly/regime/streak stats) | **TRADES** `g·t` | Filter bar + sortable table; regime/hourly breakdown as sub-panels |
| Tab 8 Parametri Strategia (SL/TP/hours editor) | **SETUP** `g·s` | Sliders for fastMA/atrStop/takeProfit etc.; live preview debounced 80ms |
| Sidebar WFO + MC controls | **SETUP** `g·s` | Form left-column |
| Sidebar leverage / sizing mode | **SETUP** `g·s` | Risk management section of form |
| Dashboard header KPIs | **DASHBOARD** `g·d` ribbon | Carried verbatim into TopBar ribbon (CAGR/Sharpe/MaxDD/PF/Trades) |
| (new) first-glance summary | **DASHBOARD** `g·d` | Equity+DD charts, monthly P&L heatmap, recent trades, top-3 DD |
| (new) param sweep heatmap | **PARAM SWEEP** `g·p` | run_optimization() grid → visx HeatMap, neighbor stability badge |
| (new) dedicated DD analysis | **UNDERWATER** `g·u` | dd_periods from compute_metrics → underwater chart + top-5 DD table |

---

## 3 · Python function → FastAPI endpoint mapping

### `/runs`
| Function | Endpoint | Method |
|---|---|---|
| `run_versions()` + `run_wfo()` + `run_optimization()` + `run_bootstrap()` | `POST /runs` | Creates run, triggers async backtest pipeline |
| `compute_metrics()` | `GET /runs/{id}` | Returns metrics + summary in run object |
| `backtest_v2()` equity series | `GET /runs/{id}/equity` | Equity + drawdown arrays |
| `run_wfo()` fold results | `GET /runs/{id}/wfo` | IS/OOS per fold |
| trade log from `backtest_v2()` | `GET /runs/{id}/trades` | Paginated + filterable by side/pnl |
| `run_optimization()` grid | `GET /runs/{id}/sweep` | Grid values + best cell |
| `run_bootstrap()` + `run_stress()` | `GET /runs/{id}/mc` | Fan paths + percentiles + stress |
| SSE progress events | `GET /runs/{id}/stream` | SSE: `{"phase":"wfo","pct":45}` |

### `/assets`
| Function | Endpoint | Method |
|---|---|---|
| `load_hourly()` + yfinance_client | `POST /assets/fetch` | `{source, ticker}` → fetch + persist to DuckDB |
| `compute_indicators_v2()` + all quant stats | `GET /assets/{ticker}/stats` | CAGR, vol, Sharpe, ACF, QQ, rolling vol |
| Asset bars | `GET /assets/{ticker}/bars` | OHLCV array |

### `/strategies`
| Function | Endpoint | Method |
|---|---|---|
| Library CRUD | `GET/POST/DELETE /strategies` | Save/list/delete strategy specs |
| Star toggle | `PUT /strategies/{id}/star` | Toggle starred |

### `/vibe`
| Function | Endpoint | Method |
|---|---|---|
| `run_vibe_agent()` / `run_agent()` | `POST /vibe/generate` | `{prompt, asset, n_candidates}` → strategy JSON |
| `build_improvement_prompt()` + `run_agent()` | `POST /vibe/improve` | `{run_id}` → improved strategy spec |

### Preview endpoint (SETUP live preview)
| Function | Endpoint | Method |
|---|---|---|
| `backtest_v2()` on last 500 bars | `POST /runs/preview` | `{params}` → lightweight metrics in ~100ms |

---

## 4 · Five milestones

### M1 · Scaffold + Design shell (2 days)
- Create `web/` with Next.js 14 + TypeScript
- Copy `design-tokens.css` from spec (colors, fonts, spacing)
- Build `TopBar`, `Sidebar`, `StatusBar`, `Palette`, `HelpToast`, `Toast` from `pareto-shell.jsx`
- Wire all hotkeys (`⌘K`, `g+letter`, `1–9`, `[/]`, `r`, `j/k`, `?`, `esc`)
- Render empty Dashboard with hardcoded fixtures from `pareto-data.js` (ported to TypeScript)
- **No backend wiring yet**
- Configure `railway.toml` with two services (`api`, `web`)
- Deploy to Railway to verify infra

### M2 · Backend extraction + parity check (2–3 days)
- Create `engine/` package: copy `strategy_core.py`, `backtest.py`, `montecarlo.py`, `validation.py`, `trade_analysis.py` verbatim, remove all `st.*` calls
- Create `api/` with FastAPI: scaffold all endpoints (return empty/fixture responses initially)
- Implement `POST /runs` → async backtest pipeline (`run_versions` → `run_wfo` → `run_bootstrap`) with SSE progress
- Implement `GET /runs/{id}/equity`, `/trades`, `/wfo`, `/sweep`, `/mc`
- Implement `POST /assets/fetch` (yfinance + DuckDB cache)
- **Parity check**: run fixed-seed backtest on both Streamlit and FastAPI engine, assert identical metrics
- Deploy `api` service to Railway

### M3 · Dashboard + Equity + Trades (3 days)
- Wire **Dashboard** to real backend: `useRunEquity`, `useRunTrades`, monthly P&L
- Build `EquityChart` + `DrawdownChart` (visx) with **shared crosshair sync**
- Build monthly P&L heatmap (22px cells, green→coral, hover tooltip)
- Build recent trades table (last 6, sparkline per row)
- Wire **Equity** screen (IS/OOS metrics strip, full equity+DD charts with log/bench toggles)
- Wire **Trades** screen (paginated table, side/pnl filters, `j/k` cursor, `f` focus filter)
- Retire Streamlit as primary UI (keep `btc_analysis/` for reference only)

### M4 · Setup + Sweep + MC + Underwater + Compare (3 days)
- Wire **Setup** screen: form → `POST /runs`, live preview via `POST /runs/preview` (debounced 80ms), SSE progress via `useSSE`
- Wire **Param Sweep**: `GET /runs/{id}/sweep` → visx HeatMap, click → neighbor stability badge
- Wire **Monte Carlo**: fan chart with p5/p25/p50/p75/p95 bands, P(profit)/P(ruin), final/DD histograms
- Wire **Underwater**: underwater filled chart + top-5 DD table + DD distribution histogram
- Wire **Compare**: multi-run equity overlay, metrics table, pair correlations

### M5 · Assets + Library + Vibe (3 days)
- Wire **Assets**: universe grid, `+ ADD ASSET` card (inline fetch form with source pills), all quant charts (price, returns, histogram, QQ, ACF, rolling vol), quant stats panel, kurtosis warning banner
- Wire **Library**: strategy card grid, star toggle, filters (status pills, sort), click → open run
- Wire **Vibe Trading**: chat pane (SSE streaming agent messages), generated strategy JSON inline card, CODE tab (DSL textarea), TEMPLATES tab, `POST /vibe/generate` proxy
- Full end-to-end: generate strategy → save to library → run backtest → view in Dashboard

---

## 5 · Railway deployment

### railway.toml

```toml
[build]
  builder = "dockerfile"

[[services]]
  name = "api"
  source = "."
  dockerfile = "Dockerfile.api"
  [services.deploy]
    startCommand = "uvicorn api.main:app --host 0.0.0.0 --port $PORT"
  [services.variables]
    PORT = "8000"

[[services]]
  name = "web"
  source = "."
  dockerfile = "Dockerfile.web"
  [services.deploy]
    startCommand = "node web/.next/standalone/server.js"
  [services.variables]
    PORT = "3000"
    NEXT_PUBLIC_API_URL = "${{api.RAILWAY_PUBLIC_DOMAIN}}"
```

### Environment variables to set in Railway dashboard

| Variable | Service | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | api | Never exposed to browser |
| `OPENROUTER_API_KEY` | api | Optional fallback |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | api | Optional data source |
| `DUCKDB_PATH` | api | e.g. `/data/pareto.db` (mount a volume) |
| `NEXT_PUBLIC_API_URL` | web | Points to api service public URL |

### Volume
Mount a Railway volume at `/data` for the `api` service so DuckDB and CSV data survive deploys.

---

## 6 · Risks & unknowns — need input

| # | Risk | Question for you |
|---|---|---|
| 1 | **DuckDB vs file persistence** | Railway volumes are ephemeral on hobby plan. Should we use Postgres instead for the run/trade store, keeping DuckDB only for in-process analytics? |
| 2 | **Backtest duration** | `run_wfo` on 2y hourly BTC takes ~8–15s. Railway free tier has 60s request timeout. Should I use a background job queue (Redis + arq) or is it acceptable to stream via SSE (no timeout for streaming)? |
| 3 | **yfinance in production** | yfinance is known to break on Yahoo changes. Should I add Alpaca as primary and yfinance as fallback, or the opposite? |
| 4 | **Multi-user** | Is this single-user (your Railway deployment) or should runs/strategies be per-user with auth? |
| 5 | **Streamlit decommission** | After M3 parity check, do I delete `btc_analysis/app.py` or keep it running on a separate Railway service temporarily? |
| 6 | **visx vs lightweight-charts** | The spec recommends visx for all charts, but TradingView lightweight-charts handles candles + zoom/pan much better. Can I use lightweight-charts for price/equity charts and visx for heatmaps/histograms? |

---

## 7 · What I will NOT start until you approve

- Writing any `api/`, `web/`, or `engine/` code
- Modifying `btc_analysis/` beyond the current PRs
- Creating Railway services or pushing to any branch other than a feature branch

**Next step:** review this plan, answer the questions in §6, then say "go" — I'll branch and start M1 immediately.
