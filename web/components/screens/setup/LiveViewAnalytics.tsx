"use client";
import { useEffect, useMemo, useState } from "react";
import { useRunList, useAllRuns } from "@/hooks/useRun";
import { useStrategy } from "@/hooks/useLibrary";
import { extractLogicName } from "@/components/screens/LibraryScreen";
import { EquityChart } from "@/components/charts/EquityChart";
import { Histogram } from "@/components/charts/Histogram";
import { DonutChart } from "@/components/charts/DonutChart";
import { MultiEquityChart } from "@/components/charts/MultiEquityChart";
import type { ApiRunListItem } from "@/lib/api-types";
import type { Run } from "@/lib/fixtures";
import styles from "./LiveViewAnalytics.module.css";

interface PreviewResult {
  sharpe?: number;
  cagr?: number;
  max_dd?: number;
  trades?: number;
  win_rate?: number;
  equity?: number[];
}

interface PreviewEquityPoint {
  i: number;
  v: number;
  dd: number;
  bench: number;
  oos: boolean;
}

interface Props {
  activeStrategyId: string | null;
  activeLogicName?: string | null;
  ticker: string;
  timeframe: string;
  preview: PreviewResult | null;
  previewEquity: PreviewEquityPoint[];
  previewLoading: boolean;
  previewError: string | null;
  fallbackRuns?: Run[];
}

type SortKey = "created_at" | "ticker" | "timeframe" | "status" | "sharpe" | "cagr" | "max_dd" | "pf" | "n_trades" | "win_rate";
type Outcome = "Ottimo profitto" | "Break-even" | "Loss controllato" | "Max Loss colpito";

const colors = ["#ffb53b", "#75d7ff", "#6fd17a", "#ff6b6b", "#b08cff", "#f4d35e", "#8bd3dd", "#f582ae"];

function num(v: unknown, fallback = 0) {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function avg(values: Array<number | null | undefined>) {
  const xs = values.map((v) => num(v, NaN)).filter((v) => Number.isFinite(v));
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

function fmt(v: number | null | undefined, digits = 2, suffix = "") {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function shortDate(raw?: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw.slice(0, 10);
  return d.toISOString().slice(0, 10);
}

function runReturn(run: ApiRunListItem) {
  return num(run.cagr, 0);
}

function classify(run: ApiRunListItem): Outcome {
  const ret = runReturn(run);
  const dd = Math.abs(num(run.max_dd, 0));
  const pf = num(run.pf, 0);
  if (dd >= 25 || ret <= -10) return "Max Loss colpito";
  if (ret >= 8 && pf >= 1.3 && dd <= 15) return "Ottimo profitto";
  if (ret >= -2 && ret < 8) return "Break-even";
  return "Loss controllato";
}

function outcomeColor(label: Outcome) {
  switch (label) {
    case "Ottimo profitto": return "#6fd17a";
    case "Break-even": return "#75d7ff";
    case "Loss controllato": return "#ffb53b";
    case "Max Loss colpito": return "#ff6b6b";
  }
}

function configValue(config: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = config[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function buildDescription(strategy: Record<string, unknown> | undefined, ticker: string, timeframe: string) {
  const config = (strategy?.config && typeof strategy.config === "object" ? strategy.config : {}) as Record<string, unknown>;
  const direct = configValue(config, ["description", "desc", "edge_hypothesis", "entry_logic", "rationale"]);
  if (direct) return direct;
  const type = String(strategy?.strategy ?? strategy?.strategy_type ?? "setup");
  return `Strategia ${type} configurata per ${ticker} su timeframe ${timeframe}. La vista aggrega i run associati, confronta metriche risk-adjusted e visualizza la dispersione dei risultati storici.`;
}


function fixtureRunToListItem(run: Run): ApiRunListItem {
  return {
    id: run.id,
    name: run.name,
    ticker: run.params.universe?.[0] ? `${run.params.universe[0]}-USD`.replace(/-USD-USD$/, "-USD") : run.strategy,
    timeframe: run.params.timeframe,
    status: "fixture",
    strategy_id: null,
    params: run.params as unknown as Record<string, unknown>,
    created_at: run.dates.oosEnd || run.dates.isEnd || new Date().toISOString(),
    start_date: run.dates.isStart || null,
    end_date: run.dates.oosEnd || run.dates.isEnd || null,
    sharpe: run.metricsOOS.sharpe,
    cagr: run.metricsOOS.cagr * 100,
    max_dd: run.metricsOOS.maxDD * 100,
    pf: run.profitFactor,
    n_trades: run.tradesCount,
    win_rate: run.winRate,
  };
}

export function LiveViewAnalytics({ activeStrategyId, activeLogicName, ticker, timeframe, preview, previewEquity, previewLoading, previewError, fallbackRuns = [] }: Props) {
  const { data: strategy, isLoading: strategyLoading } = useStrategy(activeStrategyId);
  const { data: runList, isLoading: runsLoading, error: runsError } = useRunList(activeStrategyId);
  const { data: allRunsData, isLoading: allRunsLoading } = useAllRuns();

  const fallbackRunMap = useMemo(() => new Map(fallbackRuns.map((run) => [run.id, run])), [fallbackRuns]);
  const fallbackRunList = useMemo(() => fallbackRuns.map(fixtureRunToListItem), [fallbackRuns]);

  // When a logic is selected in Library, use all runs filtered by that logic name
  const logicRuns = useMemo(() => {
    if (!activeLogicName || !allRunsData) return null;
    return allRunsData.filter((r) => extractLogicName(r.name) === activeLogicName);
  }, [activeLogicName, allRunsData]);

  const runs = useMemo(() => {
    if (logicRuns) return logicRuns;
    if (runList && runList.length > 0) return runList;
    return fallbackRunList;
  }, [logicRuns, runList, fallbackRunList]);

  const dataSource = logicRuns
    ? `LOGIC:${activeLogicName}`
    : runList && runList.length > 0 ? "API" : fallbackRunList.length > 0 ? "LOCAL" : "EMPTY";

  const isLoading = activeLogicName ? allRunsLoading : runsLoading;

  const [query, setQuery] = useState("");
  const [assetFilter, setAssetFilter] = useState("ALL");
  const [tfFilter, setTfFilter] = useState("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const assets = useMemo(() => [...new Set(runs.map((r) => r.ticker).filter(Boolean))].sort(), [runs]);
  const timeframes = useMemo(() => [...new Set(runs.map((r) => r.timeframe).filter(Boolean))].sort(), [runs]);

  const filteredRuns = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = runs.filter((run) => {
      if (assetFilter !== "ALL" && run.ticker !== assetFilter) return false;
      if (tfFilter !== "ALL" && run.timeframe !== tfFilter) return false;
      if (outcomeFilter !== "ALL" && classify(run) !== outcomeFilter) return false;
      if (!q) return true;
      return [run.name, run.id, run.ticker, run.timeframe, run.status].some((v) => String(v ?? "").toLowerCase().includes(q));
    });
    const dir = sortDir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      if (sortKey === "created_at") return dir * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
      if (sortKey === "ticker" || sortKey === "timeframe" || sortKey === "status") return dir * String(a[sortKey] ?? "").localeCompare(String(b[sortKey] ?? ""));
      return dir * (num(a[sortKey]) - num(b[sortKey]));
    });
  }, [runs, query, assetFilter, tfFilter, outcomeFilter, sortKey, sortDir]);

  useEffect(() => {
    if (filteredRuns.length === 0) {
      if (selectedIds.length > 0) setSelectedIds([]);
      return;
    }
    const visibleIds = new Set(filteredRuns.map((r) => r.id));
    const stillVisible = selectedIds.filter((id) => visibleIds.has(id));
    if (stillVisible.length !== selectedIds.length) {
      setSelectedIds(stillVisible);
      return;
    }
    if (selectedIds.length === 0) setSelectedIds(filteredRuns.slice(0, 4).map((r) => r.id));
  }, [filteredRuns, selectedIds]);

  const selectedRuns = useMemo(() => {
    const set = new Set(selectedIds);
    return runs.filter((r) => set.has(r.id));
  }, [runs, selectedIds]);

  const kpis = useMemo(() => {
    const basis = selectedRuns.length ? selectedRuns : filteredRuns;
    const sharpe = avg(basis.map((r) => r.sharpe));
    const pf = avg(basis.map((r) => r.pf));
    const maxDd = avg(basis.map((r) => Math.abs(num(r.max_dd, NaN))));
    const expectancyProxy = avg(basis.map((r) => {
      const trades = num(r.n_trades, 0);
      return trades > 0 ? num(r.cagr, 0) / trades : null;
    }));
    const ddDurationProxy = avg(basis.map((r) => {
      const start = r.start_date ? new Date(r.start_date).getTime() : NaN;
      const end = r.end_date ? new Date(r.end_date).getTime() : NaN;
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
      return Math.round((end - start) / 86_400_000 * Math.min(Math.abs(num(r.max_dd, 0)) / 100, 1));
    }));
    return { sharpe, pf, maxDd, expectancyProxy, ddDurationProxy, sample: basis.length };
  }, [selectedRuns, filteredRuns]);

  const donutData = useMemo(() => {
    const counts = new Map<Outcome, number>();
    (["Ottimo profitto", "Break-even", "Loss controllato", "Max Loss colpito"] as Outcome[]).forEach((o) => counts.set(o, 0));
    filteredRuns.forEach((run) => counts.set(classify(run), (counts.get(classify(run)) ?? 0) + 1));
    return [...counts.entries()].map(([label, value]) => ({ label, value, color: outcomeColor(label) }));
  }, [filteredRuns]);

  const returns = useMemo(() => filteredRuns.map(runReturn).filter((v) => Number.isFinite(v)), [filteredRuns]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-8));
  };

  const strategyName = activeLogicName
    ? activeLogicName.replace(/_/g, " ").toUpperCase()
    : String(strategy?.name ?? (activeStrategyId ? `Strategy ${activeStrategyId}` : "Setup sandbox"));
  const strategyType = activeLogicName ? "logic" : String(strategy?.strategy ?? "setup");
  const strategyStatus = activeLogicName ? "library" : String(strategy?.status ?? "research");
  const description = activeLogicName
    ? `Logica "${activeLogicName}" — aggregazione di tutti i run su tutti gli asset e timeframe. Confronto metriche risk-adjusted e dispersione storica dei risultati.`
    : buildDescription(strategy, ticker, timeframe);
  const loadingText = strategyLoading || (isLoading && dataSource === "EMPTY") ? "loading…" : runsError && dataSource === "EMPTY" ? "runs API unavailable" : `${filteredRuns.length}/${runs.length} runs · ${dataSource}`;

  return (
    <div className={styles.liveView}>
      <div className={styles.strategyCard}>
        <div className={styles.strategyTop}>
          <div>
            <div className={styles.eyebrow}>Strategy details</div>
            <div className={styles.strategyName}>{strategyName}</div>
          </div>
          <div className={styles.badges}>
            <span className={styles.badge}>ID {activeStrategyId ?? "local"}</span>
            <span className={styles.badge}>{strategyType}</span>
            <span className={styles.badge}>{strategyStatus}</span>
            <span className={styles.badge}>{ticker} · {timeframe}</span>
            <span className={styles.badge}>ANALYTICS ON</span>
          </div>
        </div>
        <div className={styles.desc}>{description}</div>
      </div>

      <div className={styles.kpiGrid}>
        <Kpi label="Sharpe medio" value={fmt(kpis.sharpe, 2)} hint={`${kpis.sample} run`} />
        <Kpi label="Profit factor" value={fmt(kpis.pf, 2)} hint="media run" />
        <Kpi label="Expectancy" value={fmt(kpis.expectancyProxy, 3, "%/trade")} hint="proxy CAGR/trade" />
        <Kpi label="Max DD medio" value={fmt(kpis.maxDd, 1, "%")} hint="assoluto" tone="risk" />
        <Kpi label="DD duration" value={fmt(kpis.ddDurationProxy, 0, "d")} hint="proxy recupero" tone="risk" />
      </div>

      <div className={styles.twoCol}>
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>Run history</span>
            <span className={styles.sectionSub}>{loadingText}</span>
          </div>
          <div className={styles.filters}>
            <input className={styles.input} placeholder="filter id / name / asset…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <select className={styles.select} value={assetFilter} onChange={(e) => setAssetFilter(e.target.value)}>
              <option value="ALL">ALL ASSETS</option>
              {assets.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select className={styles.select} value={tfFilter} onChange={(e) => setTfFilter(e.target.value)}>
              <option value="ALL">ALL TF</option>
              {timeframes.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
            </select>
            <select className={styles.select} value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)}>
              <option value="ALL">ALL OUTCOMES</option>
              {donutData.map((d) => <option key={d.label} value={d.label}>{d.label}</option>)}
            </select>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.checkCell}>✓</th>
                  <Th label="Run" k="created_at" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="Asset" k="ticker" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="TF" k="timeframe" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="Sharpe" k="sharpe" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="CAGR" k="cagr" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="DD" k="max_dd" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="PF" k="pf" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="Trades" k="n_trades" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                  <Th label="Win" k="win_rate" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map((run, idx) => (
                  <tr key={run.id}>
                    <td className={styles.checkCell}><input type="checkbox" checked={selectedIds.includes(run.id)} onChange={() => toggleSelected(run.id)} /></td>
                    <td title={run.id}><span style={{ color: colors[idx % colors.length] }}>●</span> {shortDate(run.created_at)}</td>
                    <td>{run.ticker || "—"}</td>
                    <td>{run.timeframe || "—"}</td>
                    <td className={num(run.sharpe) >= 1 ? styles.positive : undefined}>{fmt(run.sharpe, 2)}</td>
                    <td className={num(run.cagr) >= 0 ? styles.positive : styles.negative}>{fmt(run.cagr, 1, "%")}</td>
                    <td className={styles.negative}>{fmt(Math.abs(num(run.max_dd, NaN)), 1, "%")}</td>
                    <td className={num(run.pf) >= 1.2 ? styles.positive : undefined}>{fmt(run.pf, 2)}</td>
                    <td>{run.n_trades ?? "—"}</td>
                    <td>{fmt(run.win_rate, 1, "%")}</td>
                  </tr>
                ))}
                {filteredRuns.length === 0 && (
                  <tr><td colSpan={10}>No historical runs match the current filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>Win rate condizionato</span>
            <span className={styles.sectionSub}>outcome buckets</span>
          </div>
          <DonutChart data={donutData} />
        </div>
      </div>

      <div className={styles.chartGrid}>
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>Distribuzione rendimenti</span>
            <span className={styles.sectionSub}>CAGR/run · skew visuale</span>
          </div>
          {returns.length ? <Histogram data={returns} bins={18} height={180} fmt={(v) => `${v.toFixed(1)}%`} /> : <div className={styles.empty}>NO RETURN DATA</div>}
        </div>
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>Equity multistrato</span>
            <span className={styles.sectionSub}>{selectedRuns.length} selected · max 8</span>
          </div>
          <MultiEquityChart runs={selectedRuns.map((r, idx) => ({
            id: r.id,
            name: `${r.ticker} ${r.timeframe}`,
            color: colors[idx % colors.length],
            localEquity: fallbackRunMap.get(r.id)?.equity.map((p) => ({ i: p.i, v: p.v, dd: p.dd })),
          }))} height={220} />
        </div>
      </div>

      <div className={styles.previewCard}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>Current live preview</span>
          <span className={styles.sectionSub}>{ticker} · {timeframe} · 500 bars {previewLoading ? "· loading…" : ""}</span>
        </div>
        {previewError && <div className={styles.empty}>{previewError}</div>}
        {!previewError && previewEquity.length > 0 ? (
          <EquityChart equity={previewEquity} oosStart={null} height={210} color="var(--cyan)" showBench={false} />
        ) : !previewError ? (
          <div className={styles.empty}>{previewLoading ? "CALCOLO PREVIEW…" : "MODIFICA I PARAMETRI PER VISUALIZZARE"}</div>
        ) : null}
        <div className={styles.previewMetrics}>
          <MiniMetric label="EST SHARPE" value={fmt(preview?.sharpe, 2)} />
          <MiniMetric label="EST CAGR" value={fmt(preview?.cagr, 1, "%")} />
          <MiniMetric label="MAX DD" value={fmt(preview?.max_dd, 1, "%")} />
          <MiniMetric label="TRADES" value={preview?.trades != null ? String(preview.trades) : "—"} />
          <MiniMetric label="WIN" value={fmt(preview?.win_rate, 1, "%")} />
        </div>
      </div>
    </div>
  );
}

function Th({ label, k, sortKey, sortDir, onSort }: { label: string; k: SortKey; sortKey: SortKey; sortDir: "asc" | "desc"; onSort: (k: SortKey) => void }) {
  const active = sortKey === k;
  return <th onClick={() => onSort(k)}>{label}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}</th>;
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "risk" }) {
  return (
    <div className={styles.kpiCard}>
      <div className={styles.kpiLabel}>{label}</div>
      <div className={styles.kpiValue} style={{ color: tone === "risk" ? "var(--coral)" : "var(--amber)" }}>{value}</div>
      <div className={styles.kpiHint}>{hint}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return <div className={styles.metricMini}><span>{label}</span><span>{value}</span></div>;
}
