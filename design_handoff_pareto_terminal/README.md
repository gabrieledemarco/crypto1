# Handoff — PARETO · Streamlit → modern quant terminal

## Overview

You are refactoring a Streamlit crypto backtesting app into a **dense, keyboard-driven web terminal** modelled on the Bloomberg/Refinitiv cockpit aesthetic. The bundled HTML files in `design/` are **design references** — pixel-perfect prototypes that demonstrate the target look, feel, density, and interactions. They were built in plain React + inline SVG to be readable, not to be shipped.

Your task is to **recreate these designs in a production stack** (recommended: Next.js + TypeScript + FastAPI), reusing the original Python backtesting engine where possible. The designs are the source of truth for UX. The Streamlit codebase is the source of truth for strategy/backtest logic.

## About the design files

The files in `design/` are HTML/JSX prototypes:

- `Pareto Wireframes.html` — 3 low-fi direction explorations + critique of the original Streamlit app. Useful context.
- `Pareto Terminal.html` + `pareto-data.js` + `pareto-charts.jsx` + `pareto-screens.jsx` + `pareto-screens-extra.jsx` + `pareto-shell.jsx` — the hi-fi prototype to recreate. **This is the target.**

The hi-fi files use a single inline React app loaded via Babel for prototyping. **Do not ship Babel-in-browser** — port to a real React + TypeScript build.

## Fidelity

**High-fidelity.** Pixel-perfect target. Colors, type, spacing, panel density, and shadow/border treatments must match. The aesthetic is non-negotiable — it's the point of the refactor.

If you must deviate (e.g., your chart library renders crosshairs differently), keep the *visual language* (mono numbers, amber/coral/green/cyan palette on dark olive, 1px borders, no rounded corners except where specified).

---

## Recommended target stack

You can change this if you have a reason, but the recommendation is dialled in for this design:

| Layer | Choice | Why |
|---|---|---|
| **Frontend framework** | Next.js 14 (App Router) + React 18 + TypeScript | SSR-able, file-based routing matches the screen list |
| **Styling** | CSS variables + CSS Modules (or Tailwind with a custom config) | The palette is a fixed set of tokens — CSS variables are the cleanest mapping |
| **Charts** | [visx](https://airbnb.io/visx/) (low-level, matches the bespoke look) OR [TradingView lightweight-charts](https://www.tradingview.com/lightweight-charts/) for the candle/equity views | Avoid Plotly / Highcharts — they fight a custom terminal look |
| **State** | Zustand or React Context for run/screen/palette state, TanStack Query for server cache | Light, no Redux |
| **Backend** | FastAPI (Python) — reuse the Streamlit strategy code as library calls | Direct port from Streamlit functions to endpoints |
| **Realtime** | SSE for backtest progress, WebSocket only if you need bi-directional | Streamlit's "rerun everything" pattern is replaced by SSE incremental updates |
| **Data** | DuckDB (single-file, perfect for backtests) or Postgres if you have multi-user | Trades, runs, equity series fit naturally |
| **LLM (Vibe Trading)** | Anthropic SDK via your backend — never call from the browser directly | API key safety |
| **Fonts** | JetBrains Mono (numbers, UI, code), Inter (prose/descriptions only) | Already used in the prototype |

---

## Architecture

```
┌─ Next.js frontend (web/) ──────────────────────────┐
│ • App Router pages per screen                       │
│ • /api/* proxies to FastAPI                         │
│ • TanStack Query for /runs, /assets, etc.           │
│ • Zustand for UI state (active run, screen, palette)│
│ • Inline SVG charts via visx                        │
└─────────────────────────────────────────────────────┘
              ↕  JSON / SSE
┌─ FastAPI backend (api/) ───────────────────────────┐
│ • /assets             GET, POST (fetch ticker)     │
│ • /assets/{ticker}/stats   GET                     │
│ • /strategies (library)    GET, POST, DELETE       │
│ • /runs                    GET, POST (new backtest)│
│ • /runs/{id}/equity        GET                     │
│ • /runs/{id}/trades        GET (paginated)         │
│ • /runs/{id}/sweep         GET                     │
│ • /runs/{id}/mc            GET                     │
│ • /runs/{id}/stream        SSE (backtest progress) │
│ • /vibe/generate           POST (Claude proxy)     │
│ • /providers/yfinance/{t}  GET                     │
│ • /providers/alpaca/{t}    GET                     │
└─────────────────────────────────────────────────────┘
              ↕
┌─ Existing Python engine (engine/) ─────────────────┐
│ • Extract from current Streamlit app:               │
│   - Strategy classes / signal generators            │
│   - Backtest runner                                 │
│   - Metric computation                              │
│   - Monte Carlo                                     │
│   - Parameter sweep                                 │
│ • Convert from `st.*` UI calls to plain Python      │
│ • Expose as functions FastAPI calls                 │
└─────────────────────────────────────────────────────┘
```

---

## Design tokens

Copy these into `design-tokens.css` or your Tailwind config. They map 1:1 to CSS variables already used in the prototype.

### Colors

```css
:root {
  /* Surfaces */
  --bg:        #0c0d0a;  /* main background — near-black olive */
  --panel:     #16170f;  /* panel surface */
  --panel-2:   #1d1f15;  /* panel header, raised */
  --panel-3:   #25271a;  /* hover, sticky */
  --border:    #3a3c28;  /* subdued borders, grid lines */
  --border-l:  #5a5d3a;  /* prominent borders */

  /* Text */
  --text:      #d8dac2;  /* primary */
  --dim:       #a3a78c;  /* secondary */
  --faint:     #7e8163;  /* tertiary / placeholder */

  /* Accents */
  --amber:     #ffb53b;  /* PRIMARY — long, headline numbers */
  --amber-d:   #d18f1f;  /* amber hover/pressed */
  --coral:     #ff7a55;  /* negative / short / drawdown / danger */
  --green:     #6fd17a;  /* profit / win / signal-good */
  --cyan:      #5cc1ff;  /* short side, info, secondary brand */
  --yellow:    #ffd84a;  /* warning, highlights, starred */
  --red:       #ff5a48;  /* destructive only */
}
```

**Usage rules:**

- All positive returns / wins / CAGR → `--green`
- All negative returns / drawdowns → `--coral`
- All headline numbers (when no positivity sign) → `--amber`
- "Short" side in trade context → `--cyan` (intentional — to differentiate from negative)
- Borders are 1px solid `--border-l` for panel chrome, 1px dashed `--border` for internal dividers
- **No rounded corners** anywhere except inside `kbd` (3px) and circular dots

### Typography

```css
--font-mono: "JetBrains Mono", ui-monospace, monospace;
--font-sans: "Inter", system-ui, sans-serif;

/* Use mono for: */
/* - All numbers (always font-feature-settings: "tnum") */
/* - UI labels and column headers */
/* - Code (DSL) */

/* Use sans for: */
/* - Strategy descriptions */
/* - Multi-sentence prose */
/* - Chat messages in Vibe Trading */
```

**Tabular numbers are mandatory.** Without `font-feature-settings: "tnum" 1` columns of P&L don't align.

### Spacing & sizing

- Base unit: 4px
- Panel padding: 8px content, 4px 8px header
- Inter-panel gap: 6px
- Grid system: 12-column CSS grid
- Top bar height: 44px
- Sidebar width: 168px
- Status bar height: 22px
- Sidebar item height: ~36px

### Borders & shadows

- All borders: 1px solid `--border-l` (panel chrome) or 1px solid `--border` (internal)
- Dashed borders (1px dashed `--border`): for "add" placeholders, inactive states, and subtle dividers
- Drop shadows: **avoid them**. Use border emphasis instead. Exception: command palette gets `box-shadow: 0 8px 0 rgba(0,0,0,.5)`.

### Scanline overlay

The body has a subtle scanline texture for the CRT vibe:

```css
body::after {
  content: ""; position: fixed; inset: 0; pointer-events: none;
  background: repeating-linear-gradient(0deg,
    rgba(255,255,255,0.012) 0 1px, transparent 1px 3px);
  z-index: 100;
}
```

Keep it — it's part of the look.

---

## Screens (11 total)

Sidebar groups: **WORKSPACE · DATA · BUILD · ANALYZE**. Each screen has a function-key label (F1–F0) and a `g`+letter hotkey.

### 1 · DASHBOARD `g·d` (F1)

**Purpose:** at-a-glance status of the current active run.

**Layout:** 12-column grid, 2 rows of panels.

- Row 1: Equity chart (cols 1–8) stacked over Drawdown chart, both sharing the same X axis · Metrics block (cols 9–12) showing IS|OOS pairs.
- Row 2: Monthly P&L heatmap (cols 1–4) · Recent trades table (cols 5–8) · Top 3 drawdowns (cols 9–12).

**Components:**

- `EquityChart` — line, ~220px tall. Always renders benchmark dashed underneath. OOS region is filled with `--amber` at 5% opacity. Y-axis is %.
- `DrawdownChart` — filled area in `--coral` at 18% opacity, ~64px tall. **Crosshair MUST be synced with the equity chart above** (hover any X → both highlight).
- Metrics block — 3x3 grid. Each cell shows label + IS value (`--dim`) + OOS value (accent color). Metrics: Sharpe, Sortino, Calmar, CAGR, MaxDD, Ulcer, Win%, PF, Trades.
- Monthly P&L — 12-col heatmap, 22px cells. Green→coral diverging palette. Hover tooltip top-right showing month index + % return.
- Recent trades — last 6 trades, dense table with side (L=amber, S=cyan), R-multiple, P&L%, equity sparkline.
- Top 3 drawdowns — table with #, period (t-index range), depth (coral), len, recovery.

### 2 · ASSETS `g·a` (F2)

**Purpose:** statistical analysis of any asset's historical series.

**Layout:**

- Row 1: Universe panel (full width) — asset cards + "+ ADD ASSET" card with inline fetch form.
- Row 2: Price/Returns chart (cols 1–8, with PRICE/LOG-RET toggle) + Quant Stats panel (cols 9–12).
- Row 3: Distribution histogram (cols 1–5) + QQ plot (cols 6–9) + ACF chart (cols 10–12).
- Row 4: Rolling vol (full width).

**Components:**

- Asset card: ticker (amber, 13px, 700 weight), name (mono dim), CAGR%, σ, mini sparkline.
- "+ ADD ASSET" card: dashed border, amber on hover. Click expands form with:
  - Source pills: yfinance / alpaca / binance
  - Ticker input (uppercased, autoFocus)
  - "▸ FETCH" primary button
  - Quick-pick chips (AAPL, TSLA, SPY, NVDA, GLD, EURUSD, TLT, QQQ, MSTR)
  - On fetch: call backend `/providers/{source}/{ticker}`, persist to localStorage + server, auto-select. Show × on custom assets to remove.
- `PriceChart` — log-scale Y, line in amber, crosshair tooltip with close + day return.
- `ReturnsChart` — vertical bars from 0-baseline, green up / coral down.
- `ReturnHistogram` — 50 bins, green/coral by sign, dashed normal-distribution overlay in amber.
- `QQPlot` — sample vs theoretical quantiles, points >1σ deviation colored coral. y=x diagonal in cyan.
- `ACFChart` — bars from baseline, confidence band ±2/√n in cyan at 8% opacity, bars outside band in amber.
- `RollingVolChart` — line in amber, mean line dashed cyan.
- Quant Stats panel: 3x3 grid. Cells: CAGR (big), Vol (big), Sharpe (big), MaxDD, Skew (with "left-tailed"/"right-tailed" sub-label), Excess Kurtosis (with "fat tails" warning), VaR 95, CVaR 95, Best day.
- If kurtosis > 2, show a `--coral` warn banner: "⚠ kurtosi alta · code grasse · attenzione a leverage e stop ravvicinati".

### 3 · LIBRARY `g·l` (F3)

**Purpose:** browse saved strategies (active runs + archived research + AI-generated).

**Layout:** single panel, auto-fill grid of strategy cards (min 280px wide).

**Card structure:**

- Top row: star toggle (yellow when on) · name (700, ellipsis) · status badge (live=green / research=cyan / archived=faint, all bordered).
- Meta row: strategy type · author · date (all dim mono).
- Description (1–2 lines, sans, dim).
- Tag chips (cyan-tinted): `#momentum`, `#crypto`, etc.
- Metrics grid (5 cols): SHARPE, CAGR, MAXDD, PF, TRADES.
- Equity sparkline (full width, ~28px) — green if profitable, coral if not.
- Hover: border → amber. Click: open associated run in EQUITY.

**Filters/sort bar** in panel header (right side): search input, status pills (all/live/research/archived), sort pills (Sharpe/CAGR/DD/Recent).

### 4 · VIBE TRADING `g·v` (F4)

**Purpose:** AI-assisted strategy creation in natural language + DSL editor.

**Layout:** tabbed at top (VIBE · CODE · TEMPLATES) with save/backtest action buttons on the right.

#### Tab: VIBE
Two-column split:

- **Left — agent chat pane:**
  - Header: "AGENT · vibe-trading" / "claude-haiku-4-5"
  - Empty state: glowing ◊ icon + greeting + 3 example prompts as clickable cards
  - Messages: left-bordered (cyan=user, amber=agent), label "you"/"agent", body in sans
  - Generated strategy JSON renders inline as a compact `StrategyCard`
  - Bottom: textarea + ▸ SEND button (Cmd+Enter shortcut)
  - Typing indicator: 3 amber dots bouncing
  
- **Right — strategy spec pane:**
  - Shows full `StrategyCard` of the most recent generation, OR empty state ("nessuna strategia generata")

#### Tab: CODE
Full-width DSL editor (pareto-lang). Monospace `<textarea>`, 13px, line-height 1.55. Footer with line/char count.

#### Tab: TEMPLATES
Auto-fill grid of template prompt cards. Click → switches to VIBE tab and sends the prompt.

**LLM contract:**

The agent expects JSON only, schema:

```json
{
  "name": "kebab-case",
  "description": "1-2 sentences",
  "strategy_type": "momentum|mean-reversion|trend-following|breakout|stat-arb|carry|vol-target|other",
  "universe": ["BTC", "ETH"],
  "timeframe": "5m|15m|1h|4h|1d",
  "long_when": ["..."],
  "short_when": ["..."],
  "exit_when": ["..."],
  "risk": {"per_trade_pct": 1.0, "stop": "2.5*ATR", "take_profit": "4*ATR", "max_positions": 3},
  "expected_metrics": {"sharpe_est": 1.5, "cagr_est": 20, "max_dd_est": -15}
}
```

Backend should sanitize/validate. Strip markdown fences if present.

### 5 · SETUP `g·s` (F5)

**Purpose:** configure and launch a backtest.

**Layout:** 12-col grid, left form (cols 1–5) + live preview (cols 6–12).

**Form:** sliders for fastMA, slowMA, atrStop, takeProfit, riskPerTrade. Pills for universe (multi-select), timeframe (single-select). Read-only display of fees/slippage/funding. Action row: ▶ RUN (primary, ⌘↵), SAVE, RESET.

**Live preview** (cols 6–12): mini equity chart that recomputes on every slider change (debounced 80ms) — runs a small approximation locally OR pings the backend. Show est Sharpe / trades per year / exposure / data window.

### 6 · EQUITY `g·e` (F6)

**Purpose:** the canonical results view.

**Layout:** single full-width panel.

- Top strip: 8 IS|OOS metric pairs.
- Equity chart (300px) with log/bench toggles (top right).
- Drawdown chart (100px) synced underneath.

### 7 · TRADES `g·t` (F7)

**Purpose:** browse/filter/sort the trade log.

**Layout:** single panel.

- Filter bar: side (all/long/short), pnl (all/win/loss), counters, CSV export.
- Table: #, OPEN, SIDE, ENTRY, EXIT, R, DUR, P&L%, EQUITY sparkline. Sticky header. Sortable columns (click header).
- Hotkeys: `j`/`k` move cursor, `↵` open detail, `f` focus filter.
- Footer: cursor position / total.

### 8 · PARAM SWEEP `g·p` (F8)

**Purpose:** parameter optimization heatmap with neighbor-robustness check.

**Layout:** heatmap (cols 1–8) + selection panel (cols 9–12).

- Heatmap: cells colored on selected metric (Sharpe / CAGR / MaxDD / Calmar — pills in header). Hover shows tooltip with value. Click selects cell (cyan outline).
- Selection panel: fastMA/slowMA values, selected metric (big), delta vs best, 9-neighbor mean/std/stability badge (green=STABILE / amber=MEDIO / coral=FRAGILE).
- "BEST PLATEAU" jump button.
- Warn banner if neighbors are noisy.

### 9 · UNDERWATER `g·u` (F9)

**Purpose:** dedicated drawdown analysis.

**Layout:** underwater chart (full, 200px) + Top 5 DD table (cols 1–7) + DD distribution histogram (cols 8–12).

### 10 · MONTE CARLO `g·m` (F0)

**Purpose:** robustness / significance testing.

**Layout:**

- Fan chart (cols 1–8) showing p5/p25/p50/p75/p95 percentile bands of bootstrapped equity paths.
- Outcomes panel (cols 9–12): P(profit) and P(ruin) big, p5/p50/p95 finals, Sharpe with 95% CI and t-stat.
- Bottom row: Final-return distribution + MaxDD distribution histograms.

### 11 · COMPARE `g·c`

**Purpose:** compare multiple runs side-by-side.

**Layout:** single panel.

- Run chips: click to add/remove from comparison. Each in its own color (amber/cyan/green/coral). Add new run button.
- Multi-line equity chart with all active runs overlaid.
- Metrics comparison table (CAGR, Sharpe, Sortino, MaxDD, PF, Trades).
- Correlation between pairs at the bottom — green when |corr| < 0.4 ("good diversifier"), amber otherwise.

---

## Global UI elements

### Top bar (44px, sticky)

Left to right:
- Brand: `■ PARETO · backtest terminal` (square amber mark + name + tagline)
- Breadcrumb: `RUNS / [active-run selector] / [SCREEN-LABEL in cyan]`
- Ribbon: 5 stats (CAGR/Sharpe/MaxDD/PF/Trades) separated by 1px dividers, on the right
- ⌘K button (palette trigger)

### Sidebar (168px wide)

Grouped items (WORKSPACE / DATA / BUILD / ANALYZE), each:
- F-number badge (mono, bordered)
- LABEL (700)
- `g·letter` hint (faint)

Active item: amber, 2px left-border, gradient highlight, gradient `rgba(amber, 0.12) → transparent`.

Footer: hotkey legend list.

### Status bar (22px)

`user @ local · run <name> · screen <id> · live ● connected · ... · v0.1 <time>`

When `g` prefix is active: show yellow "g · waiting for key…" hint.

### Command palette (⌘K / Ctrl+K)

Centered modal, 540px wide, amber 1px border + tinted glow shadow.

- Top: input with placeholder "cerca azione, schermata, run…"
- Filtered action list: icon (col 1), label (col 2), hint (col 3, dim), key shortcut (col 4, cyan)
- Footer: `↑↓ nav · ↵ select · esc close`
- Categories: go-to-screen, load-run, actions (re-run, export, save snapshot, show hotkeys)

### Toast

Bottom-center, 36px from bottom, amber border, fade-in animation, auto-dismiss 1.8s.

### Help overlay (`?`)

Centered modal with hotkey reference.

---

## Interactions

### Keyboard map (global, when not in input)

| Key | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Toggle command palette |
| `1`–`9`, `0` | Direct screen nav (1=Dashboard, 0=Monte Carlo) |
| `g` then letter | Go to screen by letter (d/a/l/v/s/e/t/p/u/m/c) — 1.2s timeout |
| `[` / `]` | Previous / next run |
| `r` | Re-run current setup |
| `j` / `k` | Down / up in lists (trades) |
| `↵` | Open / activate |
| `?` | Show hotkeys help |
| `esc` | Dismiss overlays |
| `f` | Focus filter (in TRADES) |

When focused on input/textarea, only `esc` works (to blur).

### Live updates

- Setup sliders: debounce 80ms, re-fetch preview (lightweight backend endpoint that runs a downsampled backtest, ~100ms target).
- Run completion: SSE pushes incremental progress events. Show inline progress in the run selector.
- New run: optimistic UI — show in selector immediately, mark as "running", swap when complete.

### Crosshair sync

In DASHBOARD and EQUITY, hovering the equity chart **must** propagate the X position to the drawdown chart below. Implement via a shared `hoverIndex` state.

### Charts

- All charts use inline SVG. **No canvas.** Reason: clean direct-DOM hover handling, no resize issues.
- Use a `ResizeObserver` per chart wrapper to get the container width.
- Tooltip is an absolutely-positioned `<div>` outside the SVG (better antialiasing for text).

---

## State management

Suggested store shape (Zustand):

```ts
type Store = {
  runs: Run[];
  activeRunId: string;
  screen: ScreenId;
  paletteOpen: boolean;
  helpOpen: boolean;
  compareIds: string[];           // for COMPARE screen
  gPrefix: boolean;                // hotkey state
  toast: string | null;
  
  // actions
  setRun: (id: string) => void;
  goto: (screen: ScreenId) => void;
  mutateParams: (patch: Partial<Params>) => void;
  runAll: () => Promise<void>;
  toggleCompare: (id: string) => void;
};
```

Server data via TanStack Query, keyed by `runId`:
- `useRunMetrics(runId)`
- `useRunEquity(runId)`
- `useRunTrades(runId, filters)`
- `useRunSweep(runId)`
- `useRunMC(runId)`
- `useAsset(ticker, source)`
- `useStrategyLibrary()`

---

## Backend implementation notes

### Reusing your Streamlit Python code

For each `st.sidebar.slider(...)` and `st.button(...)` in your original app, **extract the pure-Python function** that does the work. The Streamlit app becomes:

```python
# old (Streamlit)
fast_ma = st.sidebar.slider("Fast MA", 2, 50, 12)
slow_ma = st.sidebar.slider("Slow MA", 5, 200, 48)
# ...
equity, trades = run_backtest(fast_ma, slow_ma, ...)
st.plotly_chart(equity_curve(equity))

# new (FastAPI)
@app.post("/runs")
def create_run(params: RunParams):
    equity, trades = run_backtest(params.fast_ma, params.slow_ma, ...)
    return persist_and_return({equity, trades, metrics: compute_metrics(equity)})
```

The Streamlit `run_backtest`, `compute_metrics`, `monte_carlo`, etc. should be liftable almost verbatim.

### Endpoints (full list)

```
GET    /runs                          → list all runs
POST   /runs                          → create + start backtest
GET    /runs/{id}                     → run metadata + metrics
GET    /runs/{id}/equity              → equity series
GET    /runs/{id}/drawdown            → drawdown series + DD periods
GET    /runs/{id}/trades?...          → paginated trade log
GET    /runs/{id}/sweep               → parameter sweep grid
GET    /runs/{id}/mc                  → Monte Carlo paths + percentiles
GET    /runs/{id}/stream              → SSE backtest progress
DELETE /runs/{id}                     → archive run

GET    /strategies                    → library list
POST   /strategies                    → save new strategy spec
PUT    /strategies/{id}/star          → toggle star
DELETE /strategies/{id}               → archive

GET    /assets/{ticker}               → asset bars + stats
POST   /assets/fetch                  → {source, ticker} → fetch + cache
DELETE /assets/{ticker}               → remove custom asset

POST   /vibe/generate                 → {prompt} → strategy JSON (Claude proxy)

GET    /providers/yfinance/{ticker}   → raw bars
GET    /providers/alpaca/{ticker}     → raw bars
GET    /providers/binance/{ticker}    → raw bars
```

### Mock data generator → real data

The prototype's `pareto-data.js` uses a seeded mulberry32 RNG with Box-Muller for normal noise. Use this **only for tests/fixtures** — replace with the real backtest engine in production. Keep the seeded RNG handy for snapshot tests; deterministic test fixtures are gold.

---

## Migration plan (5 milestones)

1. **Scaffold + tokens (1 day).** Set up Next.js, copy tokens, build the top bar + sidebar + status bar shell. Render an empty Dashboard.

2. **Backend extraction (2–3 days).** Pull strategy/backtest/metrics functions out of Streamlit into a `pareto_engine` package. Wrap with FastAPI. Confirm parity with Streamlit output on a fixed seed.

3. **Dashboard + Equity + Trades (3 days).** Wire the three most-used screens. Get the equity↔drawdown crosshair sync working. Make trade table fast (virtualize if >5000 rows).

4. **Setup + Sweep + MC + Underwater + Compare (3 days).** The "analysis" screens. Use the same chart primitives — the variety comes from data, not from new components.

5. **Assets + Library + Vibe (3 days).** Wire yfinance/alpaca clients. Library is mostly CRUD. Vibe needs the Claude proxy + JSON validation.

Total realistic estimate: **~2 weeks for one focused developer.**

---

## Files in this bundle

```
design_handoff_pareto_terminal/
├── README.md                       (this file)
├── BOOTSTRAP_PROMPT.md             (paste-ready prompt for Claude Code)
└── design/
    ├── Pareto Terminal.html        ★ THE HI-FI TARGET — open this first
    ├── Pareto Wireframes.html      (low-fi exploration + critique — for context)
    ├── pareto-data.js              (mock data + helpers — useful as test fixture)
    ├── pareto-charts.jsx           (chart primitives — useful as visual spec)
    ├── pareto-screens.jsx          (8 core screens — visual spec)
    ├── pareto-screens-extra.jsx    (ASSETS, LIBRARY, VIBE — visual spec)
    └── pareto-shell.jsx            (topbar / sidebar / palette / hotkeys — visual spec)
```

To preview locally: serve the `design/` folder over HTTP (e.g. `python -m http.server` inside it) and open `Pareto Terminal.html`.

---

## Don'ts

- Don't ship Babel-in-browser. Port the JSX to a real build.
- Don't use rounded corners. The aesthetic is hard-edge.
- Don't introduce drop-shadows. Use border emphasis.
- Don't use proportional digits for numbers. **Always** tabular mono.
- Don't add emoji except `▶ ▸ ◊ ★ ●` (the prototype uses these, others break the style).
- Don't use Plotly / Highcharts / Chart.js. Custom SVG via visx is the path.
- Don't centralize colors as `primary/secondary/success/danger` — use semantic names: `amber/coral/green/cyan` since they have specific quant meanings (long/short/profit/info).

## Brand asset & font notes

- Fonts (Google Fonts): JetBrains Mono (weights 400/500/600/700), Inter (400/500/600).
- No logo file ships — the brand mark is a CSS box: `width:16px; height:16px; background:amber; transform:rotate(-4deg); inset shadow forming an inner square.` Reproduce in React or generate an SVG.
