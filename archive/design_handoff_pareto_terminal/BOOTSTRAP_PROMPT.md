# Bootstrap prompt for Claude Code

Copy-paste the block below into Claude Code as your first message. It primes the agent with the right context and gets it to plan before coding.

---

## 📋 Paste this into Claude Code

````
I'm refactoring my existing Streamlit crypto backtesting app into a production-grade web terminal. The current Streamlit code is in this repo. I have a high-fidelity design reference bundle attached (folder `design_handoff_pareto_terminal/`).

Please follow this process:

**1. Read the spec.**
Read `design_handoff_pareto_terminal/README.md` end-to-end. It defines target stack, design tokens, all 11 screens, the API surface, and a migration plan. Treat it as the source of truth for UX.

**2. Read the design reference files.**
Open `design_handoff_pareto_terminal/design/Pareto Terminal.html` and the four `.jsx` files. They are pixel-perfect prototypes — your job is to recreate this in production code, not to copy the prototype's structure verbatim. They're built with Babel-in-browser; the production app must use a real build.

**3. Inventory the existing Streamlit app.**
Walk the current repo. List:
- Every `streamlit.*` UI call (these become endpoints/components)
- Every pure-Python function (strategy logic, backtest runner, metric calculators, MC, sweep) — these are reused as-is on the backend
- Data fetching code (yfinance/alpaca/binance) — these become provider clients
- Any persistence (file-based, SQLite, etc.) — flag for migration

**4. Plan in writing before coding.**
Output a `MIGRATION_PLAN.md` at the repo root with:
- Proposed monorepo layout (`api/`, `web/`, `engine/`)
- Mapping from each Streamlit page/section to a target screen (Dashboard, Setup, Equity, Trades, Sweep, Underwater, MC, Compare, Assets, Library, Vibe Trading)
- Mapping from each Python function to its FastAPI endpoint
- Order of work — recommend 5 milestones per the README's migration plan
- Risks/unknowns and what you need from me

Don't start coding until I've reviewed the plan.

**5. Build milestone 1 only.**
Once I approve the plan, scaffold Next.js + FastAPI, copy design tokens, build the shell (topbar + sidebar + statusbar + palette + hotkeys + theme) and render an empty Dashboard. No backend wiring yet — use hardcoded fixtures from `design/pareto-data.js`. We'll iterate from there.

**Non-negotiables** (from the design spec):
- All numbers in mono with tabular figures
- No rounded corners, no drop shadows, no rgba blur effects beyond what the spec defines
- Color palette is fixed — use semantic names (`amber/coral/green/cyan`)
- Keyboard-first: `⌘K`, `g+letter`, `1-9+0`, `j/k`, `[]`, `r`, `?` all work everywhere
- Inline SVG charts (visx), not Plotly/Chart.js
- Crosshair on equity must propagate to drawdown chart sharing the same X axis

**Stack** (preferred unless you have a reason to deviate, in which case argue it in the plan):
- Frontend: Next.js 14 (App Router) + React 18 + TypeScript + Zustand + TanStack Query + visx
- Backend: FastAPI + reuse existing Python engine
- Realtime: SSE for backtest progress
- LLM: Anthropic SDK, proxied through backend, never exposed to the browser
- Storage: DuckDB single-file
- Fonts: JetBrains Mono + Inter (Google Fonts)

Go.
````

---

## 🪜 If Claude Code asks follow-up questions

Likely ones and recommended answers:

| Question | Answer |
|---|---|
| "Where should I put the existing Streamlit code?" | Move it under `engine/` as a library. Delete `streamlit_app.py`-style entrypoints, keep pure functions. |
| "Do you want server-rendered or client-rendered?" | App Router with mostly client components for the interactive screens. SSR only the shell + initial run list. |
| "Should I keep yfinance / switch to a provider abstraction?" | Provider abstraction: `class Provider { fetch(ticker) }`, with yfinance/alpaca/binance implementations. The frontend's source pill maps to which class instance the backend uses. |
| "Database migrations?" | Use [Alembic](https://alembic.sqlalchemy.org/) if you want versioning, or plain `CREATE TABLE IF NOT EXISTS` for DuckDB single-file. Either is fine for this size. |
| "Where do I cache asset bars?" | DuckDB table `asset_bars(ticker, t, o, h, l, c, v)` with `UNIQUE(ticker, t)`. TTL = 1 day for daily bars. |
| "How aggressive should typing be?" | Strict mode TypeScript in `web/`, mypy strict in `api/`. The spec is small enough that types pay off. |
| "Anthropic API key?" | Set `ANTHROPIC_API_KEY` env var on the backend. The frontend never sees it. |

---

## 🎯 Definition of done for the refactor

- [ ] All 11 screens render with real data from the backend
- [ ] Keyboard map fully wired
- [ ] Vibe Trading agent produces valid JSON specs that save to the library
- [ ] `+ ADD ASSET` actually fetches from yfinance/alpaca/binance
- [ ] Backtests are idempotent (same params + seed = same result)
- [ ] Sub-200ms perceived latency on all chart hovers
- [ ] Dark theme only (the design is dark by intent — no light mode this milestone)
- [ ] Visual diff against the prototype shows ≤5px deviation on any element

---

## 🧱 If you don't use Claude Code

The same handoff works with any developer. Hand them the folder and point them at `README.md`. The prototype HTML can be opened directly in any browser — `cd design_handoff_pareto_terminal/design && python -m http.server` then visit `http://localhost:8000/Pareto%20Terminal.html`.
