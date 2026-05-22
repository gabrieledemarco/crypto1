"use client";
import { useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useLibrary, useStarStrategy } from "@/hooks/useLibrary";
import { useRunList, useDeleteRun } from "@/hooks/useRun";
import styles from "./LibraryScreen.module.css";
import type { LibraryEntry, Run, RunMetrics } from "@/lib/fixtures";
import type { RunListItem } from "@/hooks/useRun";
import type { SetupParams } from "@/store";

type StatusFilter = "ALL" | "live" | "research" | "archived";

function buildRunStub(run: RunListItem): Run {
  const emptyM: RunMetrics = { sharpe: 0, sortino: 0, cagr: 0, maxDD: 0, calmar: 0, finalReturn: 0 };
  const p = run.params as Record<string, unknown>;
  return {
    id: run.id,
    name: run.name,
    strategy: run.ticker,
    color: "var(--amber)",
    equity: [],
    oosStart: 0,
    trades: [],
    params: {
      fastMA: 0, slowMA: 0,
      atrStop: (p.sl_mult as number) ?? 2,
      takeProfit: (p.tp_mult as number) ?? 5,
      riskPerTrade: (p.risk_per_trade as number) ?? 0.01,
      fees: (p.commission as number) ?? 0.0004,
      slippage: (p.slippage as number) ?? 0.0001,
      funding: false,
      universe: [run.ticker],
      timeframe: run.timeframe ?? "1h",
    },
    dates: { isStart: run.start_date ?? "", isEnd: run.end_date ?? "", oosStart: "", oosEnd: "" },
    metricsIS: { ...emptyM, sharpe: run.sharpe ?? 0, cagr: run.cagr ?? 0, maxDD: run.max_dd ?? 0 },
    metricsOOS: emptyM,
    ddPeriods: [],
    sweep: [],
    mc: { paths: [], percentiles: { p5: [], p25: [], p50: [], p75: [], p95: [] }, finals: [], ddFinals: [] },
    winRate: run.win_rate ?? 0,
    profitFactor: run.pf ?? 0,
    tradesCount: run.n_trades ?? 0,
    avgDur: 0,
    exposure: 0,
    monthly: [],
  };
}

export function LibraryScreen() {
  const { goto, setToast, setActiveStrategy, loadRunFromHistory, setPendingSetupParams, setPendingVibeParams } = useStore();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);

  const { data: apiLibrary } = useLibrary();
  const starMutation = useStarStrategy();
  const { data: runList, isLoading: runsLoading } = useRunList(selectedEntry?.id);
  const deleteMutation = useDeleteRun();

  const displayRuns: RunListItem[] = runList ?? [];

  const entries: LibraryEntry[] =
    apiLibrary && apiLibrary.length > 0
      ? (apiLibrary as unknown as LibraryEntry[])
      : fixtures.library;

  const filtered = entries
    .filter((e) => {
      if (statusFilter !== "ALL" && e.status !== statusFilter) return false;
      if (!query) return true;
      const q = query.toLowerCase();
      return (
        e.name.toLowerCase().includes(q) ||
        e.strategy.toLowerCase().includes(q) ||
        e.tags.some((t) => t.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      if (a.starred !== b.starred) return a.starred ? -1 : 1;
      return (b.metrics.sharpe ?? 0) - (a.metrics.sharpe ?? 0);
    });

  const handleStar = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    starMutation.mutate(id);
  };

  const handleLoad = (e: React.MouseEvent, entry: LibraryEntry) => {
    e.stopPropagation();
    setActiveStrategy(entry.id);
    setToast(`"${entry.name}" loaded → Setup`);
    goto("setup");
  };

  const handleSelectEntry = (entry: LibraryEntry) => {
    setSelectedEntry((prev) => (prev?.id === entry.id ? null : entry));
  };

  const handleDeleteRun = (e: React.MouseEvent, runId: string) => {
    e.stopPropagation();
    deleteMutation.mutate(runId, {
      onSuccess: () => setToast(`Run ${runId} deleted`),
      onError: () => setToast("Delete failed"),
    });
  };

  const handleLoadRun = (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation();
    loadRunFromHistory(buildRunStub(run));
    setToast(`Run "${run.name}" caricato → Equity`);
    goto("equity");
  };

  const handleLoadInVibe = async (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation();
    const asset = run.ticker?.includes("-") ? run.ticker : `${run.ticker}-USD`;

    let code: string | null = null;
    let config: Record<string, unknown> | null = null;

    if (run.strategy_id) {
      try {
        const res = await fetch("/api/strategies");
        if (res.ok) {
          const list = await res.json();
          const strat = list.find((s: { id: string; code?: string; config?: Record<string, unknown> }) => s.id === run.strategy_id);
          if (strat) {
            code = strat.code || null;
            config = strat.config || null;
          }
        }
      } catch { /* ignore */ }
    }

    // Fallback: build config from run params so the config panel is pre-filled
    if (!config) {
      const p = run.params as Record<string, unknown>;
      config = {
        ticker: run.ticker || "BTC-USD",
        timeframe: run.timeframe || "1h",
        sl_mult: p.sl_mult,
        tp_mult: p.tp_mult,
        active_hours: p.active_hours,
        risk_per_trade: p.risk_per_trade,
        direction: p.direction,
      };
    }

    setPendingVibeParams({ asset, timeframe: run.timeframe ?? "1h", code, config });
    setToast(`${run.ticker} caricato in Vibe Trading`);
    goto("vibe");
  };

  const handleReRun = (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation();
    const p = run.params as Record<string, unknown>;
    const setupP: SetupParams = {
      ticker: run.ticker || (p.ticker as string) || "BTC-USD",
      timeframe: run.timeframe || (p.timeframe as string) || "1h",
      sl_mult: (p.sl_mult as number) ?? 2,
      tp_mult: (p.tp_mult as number) ?? 5,
      active_hours: (p.active_hours as [number, number]) ?? [6, 22],
      risk_per_trade: (p.risk_per_trade as number) ?? 0.01,
      commission: (p.commission as number) ?? 0.0004,
      slippage: (p.slippage as number) ?? 0.0001,
      direction: (p.direction as string) ?? "ALL",
      run_wfo: (p.run_wfo as boolean) ?? true,
      run_sweep: (p.run_sweep as boolean) ?? true,
      run_mc: (p.run_mc as boolean) ?? true,
    };
    setPendingSetupParams(setupP);
    setToast(`Parametri di "${run.name}" caricati → Setup`);
    goto("setup");
  };

  return (
    <div className={styles.wrapper}>
      {/* ── Strategy table ── */}
      <div className={`${styles.panel} ${selectedEntry ? styles.panelSplit : styles.panelFull}`}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>STRATEGY LIBRARY</span>
          <span className={styles.panelSub}>{entries.length} strategies</span>
        </div>

        {/* Filter bar */}
        <div className={styles.filterBar}>
          <input
            className={styles.searchInput}
            placeholder="search name / strategy / tag…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className={styles.statusPills}>
            {(["ALL", "live", "research", "archived"] as StatusFilter[]).map((s) => (
              <button
                key={s}
                className={`${styles.pill} ${statusFilter === s ? styles.pillActive : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
          <span className={styles.filterCount}>{filtered.length} shown</span>
        </div>

        {/* Table */}
        <div className={styles.tableWrap}>
          <div className={styles.thead}>
            <span className={styles.th}>★</span>
            <span className={styles.th}>NAME</span>
            <span className={styles.th}>STRATEGY</span>
            <span className={styles.th}>STATUS</span>
            <span className={styles.th}>SHARPE</span>
            <span className={styles.th}>CAGR</span>
            <span className={styles.th}>MAXDD</span>
            <span className={styles.th}>PF</span>
            <span className={styles.th}>TRADES</span>
            <span className={styles.th}>TAGS</span>
            <span className={styles.th}>ACTION</span>
          </div>

          {filtered.map((entry) => (
            <div
              key={entry.id}
              className={`${styles.trow} ${entry.starred ? styles.trowStarred : ""} ${selectedEntry?.id === entry.id ? styles.trowSelected : ""}`}
              onClick={() => handleSelectEntry(entry)}
            >
              <button
                className={`${styles.starBtn} ${entry.starred ? styles.starBtnOn : ""}`}
                onClick={(e) => handleStar(e, entry.id)}
                title={entry.starred ? "Unstar" : "Star"}
              >
                {entry.starred ? "★" : "☆"}
              </button>

              <span className={styles.name}>{entry.name}</span>
              <span className={styles.strategy}>{entry.strategy}</span>
              <StatusBadge status={entry.status} />

              <span
                className={styles.metricCell}
                style={{ color: entry.metrics.sharpe >= 1 ? "var(--green)" : "var(--amber)" }}
              >
                {entry.metrics.sharpe.toFixed(2)}
              </span>

              <span className={styles.metricCell} style={{ color: "var(--green)" }}>
                {entry.metrics.cagr >= 1
                  ? `${entry.metrics.cagr.toFixed(1)}%`
                  : `${(entry.metrics.cagr * 100).toFixed(1)}%`}
              </span>

              <span className={styles.metricCell} style={{ color: "var(--coral)" }}>
                {entry.metrics.maxDD <= -1
                  ? `${entry.metrics.maxDD.toFixed(1)}%`
                  : `${(entry.metrics.maxDD * 100).toFixed(1)}%`}
              </span>

              <span className={styles.metricCell} style={{ color: "var(--amber)" }}>
                {entry.metrics.pf.toFixed(2)}
              </span>

              <span className={styles.metricCell}>{entry.metrics.trades}</span>
              <span className={styles.tags}>{entry.tags.join(", ")}</span>

              <button
                className={styles.loadBtn}
                onClick={(e) => handleLoad(e, entry)}
                title="Load in Setup and link runs to this strategy"
              >
                LOAD →
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ── Run history panel ── */}
      {selectedEntry && (
        <div className={`${styles.panel} ${styles.runPanel}`}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>RUN HISTORY</span>
            <span className={styles.panelSub}>
              {selectedEntry.name}
              {displayRuns.length > 0 && ` · ${displayRuns.length} run${displayRuns.length !== 1 ? "s" : ""}`}
            </span>
            <span style={{ flex: 1 }} />
            <button className={styles.closeBtn} onClick={() => setSelectedEntry(null)}>✕</button>
          </div>

          <div className={styles.tableWrap}>
            {runsLoading ? (
              <div className={styles.emptyMsg}>Loading…</div>
            ) : displayRuns.length === 0 ? (
              <div className={styles.emptyMsg}>
                Nessun run. Avvia un backtest da Setup dopo aver cliccato <strong>LOAD →</strong> su questa strategia.
              </div>
            ) : (
              <>
                <div className={styles.runThead}>
                  <span className={styles.th}>NAME</span>
                  <span className={styles.th}>ASSET</span>
                  <span className={styles.th}>TF</span>
                  <span className={styles.th}>START</span>
                  <span className={styles.th}>END</span>
                  <span className={styles.th}>SHARPE</span>
                  <span className={styles.th}>CAGR%</span>
                  <span className={styles.th}>MAXDD%</span>
                  <span className={styles.th}>PF</span>
                  <span className={styles.th}>TRADES</span>
                  <span className={styles.th}>WIN%</span>
                  <span className={styles.th}>PARAMS</span>
                  <span className={styles.th}></span>
                  <span className={styles.th}></span>
                  <span className={styles.th}></span>
                  <span className={styles.th}></span>
                </div>
                {displayRuns.map((run) => (
                  <RunRow
                    key={run.id}
                    run={run}
                    onLoad={(e) => handleLoadRun(e, run)}
                    onReRun={(e) => handleReRun(e, run)}
                    onVibe={(e) => handleLoadInVibe(e, run)}
                    onDelete={(e) => handleDeleteRun(e, run.id)}
                    deleting={deleteMutation.isPending && deleteMutation.variables === run.id}
                  />
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RunRow({
  run,
  onLoad,
  onReRun,
  onVibe,
  onDelete,
  deleting,
}: {
  run: RunListItem;
  onLoad: (e: React.MouseEvent) => void;
  onReRun: (e: React.MouseEvent) => void;
  onVibe: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
  deleting: boolean;
}) {
  const params = run.params as Record<string, unknown>;
  const paramStr = Object.entries(params)
    .filter(([k]) => !["ticker", "timeframe"].includes(k))
    .map(([k, v]) => {
      if (Array.isArray(v)) return `${k}=[${v.join(",")}]`;
      return `${k}=${v}`;
    })
    .join("  ");

  return (
    <div className={styles.runRow}>
      <span className={styles.runName}>{run.name}</span>
      <span className={styles.runCell}>{run.ticker || "—"}</span>
      <span className={styles.runCell}>{run.timeframe || "—"}</span>
      <span className={styles.runCell}>{run.start_date ?? "—"}</span>
      <span className={styles.runCell}>{run.end_date ?? "—"}</span>
      <span
        className={styles.runMetric}
        style={{ color: (run.sharpe ?? 0) >= 1 ? "var(--green)" : "var(--amber)" }}
      >
        {run.sharpe != null ? run.sharpe.toFixed(2) : "—"}
      </span>
      <span
        className={styles.runMetric}
        style={{ color: (run.cagr ?? 0) >= 0 ? "var(--green)" : "var(--coral)" }}
      >
        {run.cagr != null ? `${run.cagr.toFixed(1)}%` : "—"}
      </span>
      <span className={styles.runMetric} style={{ color: "var(--coral)" }}>
        {run.max_dd != null ? `${run.max_dd.toFixed(1)}%` : "—"}
      </span>
      <span className={styles.runMetric} style={{ color: "var(--amber)" }}>
        {run.pf != null ? run.pf.toFixed(2) : "—"}
      </span>
      <span className={styles.runMetric}>
        {run.n_trades != null ? run.n_trades : "—"}
      </span>
      <span className={styles.runMetric} style={{ color: "var(--dim)" }}>
        {run.win_rate != null ? `${run.win_rate.toFixed(0)}%` : "—"}
      </span>
      <span className={styles.runParams} title={paramStr}>{paramStr || "—"}</span>
      <button
        className={styles.actionBtn}
        onClick={onLoad}
        title="Carica run nelle schermate Analysis (Equity, Trades, Sweep, Underwater, MC, WFO)"
      >
        ▶
      </button>
      <button
        className={styles.actionBtn}
        onClick={onReRun}
        title="Carica parametri in Setup per rieseguire il backtest"
        style={{ color: "var(--cyan)" }}
      >
        ↺
      </button>
      <button
        className={styles.actionBtn}
        onClick={onVibe}
        title="Apri asset in Vibe Trading per generare una strategia"
        style={{ color: "var(--amber)" }}
      >
        ◈
      </button>
      <button
        className={styles.delBtn}
        onClick={onDelete}
        disabled={deleting}
        title="Delete run"
      >
        {deleting ? "…" : "✕"}
      </button>
    </div>
  );
}

function StatusBadge({ status }: { status: LibraryEntry["status"] }) {
  const cls =
    status === "live"
      ? styles.badgeLive
      : status === "research"
      ? styles.badgeResearch
      : styles.badgeArchived;
  return <span className={`${styles.badge} ${cls}`}>{status}</span>;
}
