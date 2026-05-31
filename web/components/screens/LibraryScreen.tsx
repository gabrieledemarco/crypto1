"use client";
import { useState, useMemo, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { api } from "@/lib/api";
import { useLibrary, useStarStrategy } from "@/hooks/useLibrary";
import { useRunList, useDeleteRun } from "@/hooks/useRun";
import type { ApiRunListItem } from "@/lib/api-types";
import styles from "./LibraryScreen.module.css";
import type { LibraryEntry, Run, RunMetrics } from "@/lib/fixtures";
import type { RunListItem } from "@/hooks/useRun";
import type { SetupParams } from "@/store";

type StatusFilter = "ALL" | "live" | "research" | "archived";
type GroupBy = "none" | "tf" | "asset" | "method";
type SortCol = "name" | "tf" | "asset" | "method" | "status" | "sharpe" | "cagr" | "maxdd" | "pf" | "trades";
type SortDir = "asc" | "desc";
type EnrichedEntry = LibraryEntry & { _tf: string; _asset: string; _method: string };

function buildRunStub(run: RunListItem): Run {
  const emptyM: RunMetrics = { sharpe: 0, sortino: 0, cagr: 0, maxDD: 0, calmar: 0, finalReturn: 0 };
  const p = run.params as Record<string, unknown>;
  return {
    id: run.id, name: run.name, strategy: run.ticker, color: "var(--amber)",
    equity: [], oosStart: 0, trades: [],
    params: {
      fastMA: 0, slowMA: 0,
      atrStop: (p.sl_mult as number) ?? 2, takeProfit: (p.tp_mult as number) ?? 5,
      riskPerTrade: (p.risk_per_trade as number) ?? 0.01,
      fees: (p.commission as number) ?? 0.0004, slippage: (p.slippage as number) ?? 0.0001,
      funding: false, universe: [run.ticker], timeframe: run.timeframe ?? "1h",
    },
    dates: { isStart: run.start_date ?? "", isEnd: run.end_date ?? "", oosStart: "", oosEnd: "" },
    metricsIS: { ...emptyM, sharpe: run.sharpe ?? 0, cagr: run.cagr ?? 0, maxDD: run.max_dd ?? 0 },
    metricsOOS: emptyM, ddPeriods: [], sweep: [],
    mc: { paths: [], percentiles: { p5: [], p25: [], p50: [], p75: [], p95: [] }, finals: [], ddFinals: [] },
    winRate: run.win_rate ?? 0, profitFactor: run.pf ?? 0, tradesCount: run.n_trades ?? 0,
    avgDur: 0, exposure: 0, monthly: [],
  };
}

const TF_ORDER = ["1m", "5m", "15m", "1h", "4h", "1d"];

function extractTF(entry: LibraryEntry): string {
  const cfg = (entry as unknown as { config?: Record<string, unknown> }).config;
  if (cfg?.timeframe) return String(cfg.timeframe).toLowerCase();
  const m = entry.name.match(/_(\d+[mhd])_?/i);
  if (m) return m[1].toLowerCase();
  return entry.tags.find(t => /^\d+[mhd]$/i.test(t))?.toLowerCase() ?? "—";
}

function extractAsset(entry: LibraryEntry): string {
  const cfg = (entry as unknown as { config?: Record<string, unknown> }).config;
  if (cfg?.ticker) return String(cfg.ticker).split("-")[0];
  const known = ["BTC", "ETH", "SOL", "EUR", "GBP", "XAU"];
  const upper = entry.name.toUpperCase();
  for (const a of known) if (upper.includes(a)) return a;
  return entry.tags.find(t => known.includes(t.toUpperCase()))?.toUpperCase() ?? "—";
}

function extractMethod(strategy: string): string {
  const s = strategy.toLowerCase();
  if (s.includes("order_flow") || s.includes("ofi")) return "OFI";
  if (s.includes("tick")) return "TICK";
  if (s.includes("spread")) return "SPREAD";
  if (s.includes("vwap")) return "VWAP";
  if (s.includes("ema")) return "EMA";
  if (s.includes("rsi")) return "RSI";
  if (s.includes("macd")) return "MACD";
  if (s.includes("bb") || s.includes("bollinger")) return "BB";
  if (s.includes("donchian")) return "DCHAN";
  if (s.includes("momentum")) return "MOM";
  if (s.includes("adaptive")) return "ADAPT";
  if (s.includes("volume")) return "VOL";
  return "OTHER";
}

export function LibraryScreen() {
  const { goto, setToast, setActiveStrategy, loadRunFromHistory, setPendingSetupParams, setPendingVibeParams } = useStore();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [tfFilter, setTfFilter] = useState("ALL");
  const [assetFilter, setAssetFilter] = useState("ALL");
  const [methodFilter, setMethodFilter] = useState("ALL");
  const [groupBy, setGroupBy] = useState<GroupBy>("tf");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);
  const [sortCol, setSortCol] = useState<SortCol>("sharpe");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const queryClient = useQueryClient();
  const { data: apiLibrary } = useLibrary();
  const starMutation = useStarStrategy();
  const deleteMutation = useDeleteRun();

  // Debounce strategy selection to prevent N+1 query bursts when user clicks quickly
  const [debouncedStrategyId, setDebouncedStrategyId] = useState<string | undefined>(selectedEntry?.id);
  useEffect(() => {
    let mounted = true;
    const timer = setTimeout(() => {
      if (mounted) setDebouncedStrategyId(selectedEntry?.id);
    }, 300);
    return () => { mounted = false; clearTimeout(timer); };
  }, [selectedEntry?.id]);

  const { data: runList, isLoading: runsLoading } = useRunList(debouncedStrategyId);
  const displayRuns: RunListItem[] = runList ?? [];

  // Prefetch run list on hover so the panel opens instantly on click
  const prefetchRuns = useCallback(
    (strategyId: string) => {
      queryClient.prefetchQuery({
        queryKey: ["run-list", strategyId],
        queryFn: () =>
          api.get<ApiRunListItem[]>(
            `/runs?strategy_id=${encodeURIComponent(strategyId)}`
          ),
        staleTime: 30_000,
      });
    },
    [queryClient]
  );

  // apiLibrary has the same shape as LibraryEntry (both from useLibrary which is typed LibraryEntryApi[])
  const rawEntries: LibraryEntry[] =
    apiLibrary && apiLibrary.length > 0
      ? (apiLibrary as LibraryEntry[])
      : fixtures.library;

  const enriched = useMemo<EnrichedEntry[]>(
    () => rawEntries.map(e => ({ ...e, _tf: extractTF(e), _asset: extractAsset(e), _method: extractMethod(e.strategy) })),
    [rawEntries],
  );

  const allTFs = useMemo(() => {
    const s = new Set(enriched.map(e => e._tf));
    return TF_ORDER.filter(t => s.has(t)).concat([...s].filter(t => !TF_ORDER.includes(t)));
  }, [enriched]);
  const allAssets = useMemo(() => [...new Set(enriched.map(e => e._asset))].sort(), [enriched]);
  const allMethods = useMemo(() => [...new Set(enriched.map(e => e._method))].sort(), [enriched]);

  const filtered = useMemo(() =>
    enriched
      .filter(e => {
        if (statusFilter !== "ALL" && e.status !== statusFilter) return false;
        if (tfFilter !== "ALL" && e._tf !== tfFilter) return false;
        if (assetFilter !== "ALL" && e._asset !== assetFilter) return false;
        if (methodFilter !== "ALL" && e._method !== methodFilter) return false;
        if (!query) return true;
        const q = query.toLowerCase();
        return e.name.toLowerCase().includes(q) || e.strategy.toLowerCase().includes(q) || e.tags.some(t => t.toLowerCase().includes(q));
      })
      .sort((a, b) => {
        if (a.starred !== b.starred) return a.starred ? -1 : 1;
        const d = sortDir === "asc" ? 1 : -1;
        switch (sortCol) {
          case "name":   return d * a.name.localeCompare(b.name);
          case "tf":     return d * a._tf.localeCompare(b._tf);
          case "asset":  return d * a._asset.localeCompare(b._asset);
          case "method": return d * a._method.localeCompare(b._method);
          case "status": return d * a.status.localeCompare(b.status);
          case "sharpe": return d * ((a.metrics.sharpe ?? 0) - (b.metrics.sharpe ?? 0));
          case "cagr":   return d * ((a.metrics.cagr ?? 0) - (b.metrics.cagr ?? 0));
          case "maxdd":  return d * ((a.metrics.maxDD ?? 0) - (b.metrics.maxDD ?? 0));
          case "pf":     return d * ((a.metrics.pf ?? 0) - (b.metrics.pf ?? 0));
          case "trades": return d * ((a.metrics.trades ?? 0) - (b.metrics.trades ?? 0));
          default:       return 0;
        }
      }),
    [enriched, statusFilter, tfFilter, assetFilter, methodFilter, query, sortCol, sortDir],
  );

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  };

  type GroupRow = { type: "group"; key: string; count: number } | { type: "entry"; entry: EnrichedEntry };

  const rows = useMemo<GroupRow[]>(() => {
    if (groupBy === "none") return filtered.map(e => ({ type: "entry", entry: e }));
    const getKey = (e: EnrichedEntry) => groupBy === "tf" ? e._tf : groupBy === "asset" ? e._asset : e._method;
    const groups = new Map<string, EnrichedEntry[]>();
    for (const e of filtered) {
      const k = getKey(e);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(e);
    }
    const result: GroupRow[] = [];
    for (const [key, entries] of groups) {
      result.push({ type: "group", key, count: entries.length });
      if (!collapsedGroups.has(key)) for (const entry of entries) result.push({ type: "entry", entry });
    }
    return result;
  }, [filtered, groupBy, collapsedGroups]);

  const toggleGroup = (key: string) =>
    setCollapsedGroups(prev => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });

  const handleStar = (e: React.MouseEvent, id: string) => { e.stopPropagation(); starMutation.mutate(id); };
  const handleLoad = (e: React.MouseEvent, entry: LibraryEntry) => {
    e.stopPropagation(); setActiveStrategy(entry.id); setToast(`"${entry.name}" loaded → Setup`); goto("setup");
  };
  const handleSelectEntry = (entry: LibraryEntry) =>
    setSelectedEntry(prev => prev?.id === entry.id ? null : entry);
  const handleDeleteRun = (e: React.MouseEvent, runId: string) => {
    e.stopPropagation();
    deleteMutation.mutate(runId, {
      onSuccess: () => setToast(`Run ${runId} deleted`),
      onError: () => setToast("Delete failed"),
    });
  };
  const handleLoadRun = (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation(); loadRunFromHistory(buildRunStub(run)); setToast(`Run "${run.name}" caricato → Equity`); goto("equity");
  };

  const handleLoadInVibe = async (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation();
    const asset = run.ticker?.includes("-") ? run.ticker : `${run.ticker}-USD`;
    let code: string | null = null;
    let config: Record<string, unknown> | null = null;
    if (run.strategy_id) {
      try {
        const res = await fetch(`/api/strategies/${run.strategy_id}`);
        if (res.ok) { const strat = await res.json(); code = strat.code || null; config = strat.config || null; }
      } catch { /* ignore */ }
    }
    if (!config) {
      const p = run.params as Record<string, unknown>;
      config = { ticker: run.ticker || "BTC-USD", timeframe: run.timeframe || "1h", sl_mult: p.sl_mult, tp_mult: p.tp_mult, active_hours: p.active_hours, risk_per_trade: p.risk_per_trade, direction: p.direction };
    }
    if (!code) {
      const p = run.params as Record<string, unknown>;
      const sl = (p.sl_mult as number) ?? 2.0, tp = (p.tp_mult as number) ?? 5.0;
      const hours = (p.active_hours as [number, number]) ?? [6, 22];
      code = [
        `def agent_fn(df):`, `    """`, `    Loaded from run: ${run.name || run.ticker || "backtest"}`,
        `    Asset: ${run.ticker}  Timeframe: ${run.timeframe ?? "1h"}`, `    """`,
        `    return generate_signals_v2(`, `        df,`, `        atr_mult_sl=${sl},`,
        `        atr_mult_tp=${tp},`, `        active_hours=(${hours[0]}, ${hours[1]}),`,
        `        use_garch_filter=True,`, `    )`,
      ].join("\n");
    }
    setPendingVibeParams({ asset, timeframe: run.timeframe ?? "1h", code, config });
    setToast(`${run.ticker} caricato in Vibe Trading`); goto("vibe");
  };

  const handleReRun = (e: React.MouseEvent, run: RunListItem) => {
    e.stopPropagation();
    const p = run.params as Record<string, unknown>;
    const setupP: SetupParams = {
      ticker: run.ticker || (p.ticker as string) || "BTC-USD",
      timeframe: run.timeframe || (p.timeframe as string) || "1h",
      sl_mult: (p.sl_mult as number) ?? 2, tp_mult: (p.tp_mult as number) ?? 5,
      active_hours: (p.active_hours as [number, number]) ?? [6, 22],
      risk_per_trade: (p.risk_per_trade as number) ?? 0.01,
      commission: (p.commission as number) ?? 0.0004, slippage: (p.slippage as number) ?? 0.0001,
      direction: (p.direction as string) ?? "ALL",
      run_wfo: (p.run_wfo as boolean) ?? true, run_sweep: (p.run_sweep as boolean) ?? true, run_mc: (p.run_mc as boolean) ?? true,
    };
    setPendingSetupParams(setupP); setToast(`Parametri di "${run.name}" caricati → Setup`); goto("setup");
  };

  return (
    <div className={styles.wrapper}>
      <div className={`${styles.panel} ${selectedEntry ? styles.panelSplit : styles.panelFull}`}>

        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>STRATEGY LIBRARY</span>
          <span className={styles.panelSub}>{rawEntries.length} strategies · {filtered.length} shown</span>
        </div>

        {/* Filter row 1: search + status + group */}
        <div className={styles.filterBar}>
          <input className={styles.searchInput} placeholder="search name / strategy / tag…" value={query} onChange={e => setQuery(e.target.value)} />
          <span className={styles.sep}>|</span>
          <span className={styles.filterLabel}>STATUS</span>
          <div className={styles.pillGroup}>
            {(["ALL", "live", "research", "archived"] as StatusFilter[]).map(s => (
              <button key={s} className={`${styles.pill} ${statusFilter === s ? styles.pillActive : ""}`} onClick={() => setStatusFilter(s)}>{s.toUpperCase()}</button>
            ))}
          </div>
          <span className={styles.sep}>|</span>
          <span className={styles.filterLabel}>GROUP</span>
          <div className={styles.pillGroup}>
            {(["none", "tf", "asset", "method"] as GroupBy[]).map(g => (
              <button key={g} className={`${styles.pill} ${groupBy === g ? styles.pillAmber : ""}`} onClick={() => setGroupBy(g)}>{g.toUpperCase()}</button>
            ))}
          </div>
        </div>

        {/* Filter row 2: dimensional filters */}
        <div className={styles.filterBar2}>
          <span className={styles.filterLabel}>TF</span>
          <div className={styles.pillGroup}>
            {["ALL", ...allTFs].map(t => (
              <button key={t} className={`${styles.pill} ${tfFilter === t ? styles.pillCyan : ""}`} onClick={() => setTfFilter(t)}>{t}</button>
            ))}
          </div>
          <span className={styles.sep}>|</span>
          <span className={styles.filterLabel}>ASSET</span>
          <div className={styles.pillGroup}>
            {["ALL", ...allAssets].map(a => (
              <button key={a} className={`${styles.pill} ${assetFilter === a ? styles.pillCyan : ""}`} onClick={() => setAssetFilter(a)}>{a}</button>
            ))}
          </div>
          <span className={styles.sep}>|</span>
          <span className={styles.filterLabel}>METHOD</span>
          <div className={styles.pillGroup}>
            {["ALL", ...allMethods].map(m => (
              <button key={m} className={`${styles.pill} ${methodFilter === m ? styles.pillCyan : ""}`} onClick={() => setMethodFilter(m)}>{m}</button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className={styles.tableWrap}>
          <div className={styles.thead}>
            <span className={styles.th}>★</span>
            {(["name","tf","asset","method","status","sharpe","cagr","maxdd","pf","trades"] as SortCol[]).map(col => (
              <button key={col} className={`${styles.thBtn} ${sortCol === col ? styles.thBtnActive : ""}`} onClick={() => handleSort(col)}>
                {col.toUpperCase()}
                {sortCol === col && <span className={styles.sortInd}>{sortDir === "asc" ? "▲" : "▼"}</span>}
              </button>
            ))}
            <span className={styles.th}>ACTION</span>
          </div>

          {rows.map((row) => {
            if (row.type === "group") {
              const collapsed = collapsedGroups.has(row.key);
              return (
                <div key={`g_${row.key}`} className={styles.groupHeader} onClick={() => toggleGroup(row.key)}>
                  <span className={styles.groupChevron}>{collapsed ? "▶" : "▼"}</span>
                  <span className={styles.groupKey}>{row.key}</span>
                  <span className={styles.groupCount}>{row.count}</span>
                </div>
              );
            }
            const entry = row.entry;
            return (
              <div
                key={entry.id}
                className={`${styles.trow} ${entry.starred ? styles.trowStarred : ""} ${selectedEntry?.id === entry.id ? styles.trowSelected : ""}`}
                onClick={() => handleSelectEntry(entry)}
                onMouseEnter={() => prefetchRuns(entry.id)}
              >
                <button className={`${styles.starBtn} ${entry.starred ? styles.starBtnOn : ""}`} onClick={e => handleStar(e, entry.id)} title={entry.starred ? "Unstar" : "Star"}>
                  {entry.starred ? "★" : "☆"}
                </button>
                <span className={styles.name}>{entry.name}</span>
                <span className={`${styles.tfTag} ${styles.filterCell}`} title={`Filter TF: ${entry._tf}`}
                  onClick={e => { e.stopPropagation(); setTfFilter(f => f === entry._tf ? "ALL" : entry._tf); }}>
                  {entry._tf}
                </span>
                <span className={`${styles.assetTag} ${styles.filterCell}`} title={`Filter asset: ${entry._asset}`}
                  onClick={e => { e.stopPropagation(); setAssetFilter(f => f === entry._asset ? "ALL" : entry._asset); }}>
                  {entry._asset}
                </span>
                <span className={`${styles.methodTag} ${styles.filterCell}`} title={`Filter method: ${entry._method}`}
                  onClick={e => { e.stopPropagation(); setMethodFilter(f => f === entry._method ? "ALL" : entry._method); }}>
                  {entry._method}
                </span>
                <StatusBadge status={entry.status}
                  onClick={e => { e.stopPropagation(); setStatusFilter(f => f === entry.status ? "ALL" : entry.status as StatusFilter); }} />
                <span className={styles.metricCell} style={{ color: entry.metrics.sharpe >= 1 ? "var(--green)" : "var(--amber)" }}>
                  {entry.metrics.sharpe.toFixed(2)}
                </span>
                <span className={styles.metricCell} style={{ color: "var(--green)" }}>
                  {entry.metrics.cagr >= 1 ? `${entry.metrics.cagr.toFixed(1)}%` : `${(entry.metrics.cagr * 100).toFixed(1)}%`}
                </span>
                <span className={styles.metricCell} style={{ color: "var(--coral)" }}>
                  {entry.metrics.maxDD <= -1 ? `${entry.metrics.maxDD.toFixed(1)}%` : `${(entry.metrics.maxDD * 100).toFixed(1)}%`}
                </span>
                <span className={styles.metricCell} style={{ color: "var(--amber)" }}>{entry.metrics.pf.toFixed(2)}</span>
                <span className={styles.metricCell}>{entry.metrics.trades}</span>
                <button className={styles.loadBtn} onClick={e => handleLoad(e, entry)} title="Load in Setup">LOAD →</button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Run history panel */}
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
              <div style={{ padding: "4px 8px" }}>
                {[0.8, 0.6, 0.9, 0.7].map((w, i) => (
                  <div key={i} className={styles.skeletonRow} style={{ width: `${w * 100}%` }} />
                ))}
              </div>
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
                {displayRuns.map(run => (
                  <RunRow
                    key={run.id}
                    run={run}
                    onLoad={e => handleLoadRun(e, run)}
                    onReRun={e => handleReRun(e, run)}
                    onVibe={e => handleLoadInVibe(e, run)}
                    onDelete={e => handleDeleteRun(e, run.id)}
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

function RunRow({ run, onLoad, onReRun, onVibe, onDelete, deleting }: {
  run: RunListItem; onLoad: (e: React.MouseEvent) => void; onReRun: (e: React.MouseEvent) => void;
  onVibe: (e: React.MouseEvent) => void | Promise<void>; onDelete: (e: React.MouseEvent) => void; deleting: boolean;
}) {
  const params = run.params as Record<string, unknown>;
  const paramStr = Object.entries(params)
    .filter(([k]) => !["ticker", "timeframe"].includes(k))
    .map(([k, v]) => Array.isArray(v) ? `${k}=[${v.join(",")}]` : `${k}=${v}`)
    .join("  ");
  return (
    <div className={styles.runRow}>
      <span className={styles.runName}>{run.name}</span>
      <span className={styles.runCell}>{run.ticker || "—"}</span>
      <span className={styles.runCell}>{run.timeframe || "—"}</span>
      <span className={styles.runCell}>{run.start_date ?? "—"}</span>
      <span className={styles.runCell}>{run.end_date ?? "—"}</span>
      <span className={styles.runMetric} style={{ color: (run.sharpe ?? 0) >= 1 ? "var(--green)" : "var(--amber)" }}>{run.sharpe != null ? run.sharpe.toFixed(2) : "—"}</span>
      <span className={styles.runMetric} style={{ color: (run.cagr ?? 0) >= 0 ? "var(--green)" : "var(--coral)" }}>{run.cagr != null ? `${run.cagr.toFixed(1)}%` : "—"}</span>
      <span className={styles.runMetric} style={{ color: "var(--coral)" }}>{run.max_dd != null ? `${run.max_dd.toFixed(1)}%` : "—"}</span>
      <span className={styles.runMetric} style={{ color: "var(--amber)" }}>{run.pf != null ? run.pf.toFixed(2) : "—"}</span>
      <span className={styles.runMetric}>{run.n_trades != null ? run.n_trades : "—"}</span>
      <span className={styles.runMetric} style={{ color: "var(--dim)" }}>{run.win_rate != null ? `${run.win_rate.toFixed(0)}%` : "—"}</span>
      <span className={styles.runParams} title={paramStr}>{paramStr || "—"}</span>
      <button className={styles.actionBtn} onClick={onLoad} title="Carica in Analysis">▶</button>
      <button className={styles.actionBtn} onClick={onReRun} title="Ricarica in Setup" style={{ color: "var(--cyan)" }}>↺</button>
      <button className={styles.actionBtn} onClick={onVibe} title="Apri in Vibe Trading" style={{ color: "var(--amber)" }}>◈</button>
      <button className={styles.delBtn} onClick={onDelete} disabled={deleting} title="Delete run">{deleting ? "…" : "✕"}</button>
    </div>
  );
}

function StatusBadge({ status, onClick }: { status: LibraryEntry["status"]; onClick?: (e: React.MouseEvent) => void }) {
  const cls = status === "live" ? styles.badgeLive : status === "research" ? styles.badgeResearch : styles.badgeArchived;
  return <span className={`${styles.badge} ${cls} ${onClick ? styles.filterCell : ""}`} onClick={onClick}>{status}</span>;
}
