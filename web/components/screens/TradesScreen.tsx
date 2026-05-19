"use client";
import { useEffect, useRef, useState, useMemo } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunTrades, isRealRunId } from "@/hooks/useRun";
import { useAssetBars } from "@/hooks/useAssets";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import type { TradeMarker } from "@/components/charts/CandlestickChart";
import { Sparkline } from "@/components/charts/Sparkline";
import { TradeAnalysisPanels } from "./TradeAnalysisScreen";
import styles from "./TradesScreen.module.css";
import type { Trade } from "@/lib/fixtures";

const MAX_CHART_BARS = 300;

export function TradesScreen() {
  const { activeRunId, runs } = useStore();
  const [filterSide, setFilterSide] = useState("all");
  const [filterPnl, setFilterPnl] = useState("all");
  const [filterText, setFilterText] = useState("");
  const [sortKey, setSortKey] = useState<keyof Trade>("n");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [cursor, setCursor] = useState(0);
  const filterRef = useRef<HTMLInputElement>(null);

  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const isReal = isRealRunId(activeRunId);

  // Fetch all trades (unfiltered — we filter client-side for the table)
  const tradesQuery = useRunTrades(activeRunId || null, { limit: 500 });
  const allTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades as Trade[])
      : run?.trades ?? [];

  // Price bars: only for real runs (run.strategy = ticker like "BTC-USD")
  const ticker = isReal ? (run?.strategy ?? null) : null;
  const interval = run?.params?.timeframe ?? "1d";
  const { data: bars } = useAssetBars(ticker, interval);

  // Trade markers aligned to visible bars
  const tradeMarkers = useMemo((): TradeMarker[] => {
    if (!bars?.length || !allTrades.length) return [];
    const visible = bars.slice(-MAX_CHART_BARS);
    const firstTs = visible[0]?.ts ? new Date(visible[0].ts).getTime() : 0;
    const lastTs = visible[visible.length - 1]?.ts
      ? new Date(visible[visible.length - 1].ts!).getTime()
      : Infinity;
    return allTrades
      .filter((t) => t.date >= firstTs && t.date <= lastTs)
      .map((t) => ({
        entryTs: t.date,
        entryPrice: t.entry,
        exitTs: t.date + t.durH * 3600 * 1000,
        exitPrice: t.exit,
        side: t.side,
        win: t.pnl > 0,
      }));
  }, [allTrades, bars]);

  // Client-side filter + sort for the trade log table
  const filteredTrades = useMemo(
    () =>
      [...allTrades]
        .filter((t) => {
          if (filterSide === "long" && t.side !== "L") return false;
          if (filterSide === "short" && t.side !== "S") return false;
          if (filterPnl === "win" && t.pnl <= 0) return false;
          if (filterPnl === "loss" && t.pnl > 0) return false;
          if (filterText) {
            const q = filterText.toLowerCase();
            return (
              String(t.n).includes(q) ||
              (t.side === "L" ? "long" : "short").includes(q) ||
              String(t.entry).includes(q) ||
              String(t.pnl).includes(q)
            );
          }
          return true;
        })
        .sort((a, b) => {
          const av = a[sortKey], bv = b[sortKey];
          if (av == null || bv == null) return 0;
          return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
        }),
    [allTrades, filterSide, filterPnl, filterText, sortKey, sortDir]
  );

  // j/k keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j") {
        setCursor((c) => Math.min(filteredTrades.length - 1, c + 1));
        e.preventDefault();
      } else if (e.key === "k") {
        setCursor((c) => Math.max(0, c - 1));
        e.preventDefault();
      } else if (e.key === "f") {
        filterRef.current?.focus();
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filteredTrades.length]);

  const equity = run?.equity ?? [];
  const winners = allTrades.filter((t) => t.pnl > 0).length;
  const cols = "32px 72px 44px 88px 88px 52px 52px 72px 88px";

  function SortHeader({ k, label }: { k: keyof Trade; label: string }) {
    return (
      <span
        className={styles.sortable}
        onClick={() => {
          if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1));
          else { setSortKey(k); setSortDir(1); }
        }}
      >
        {label}{sortKey === k ? (sortDir > 0 ? " ↑" : " ↓") : ""}
      </span>
    );
  }

  return (
    <div className={styles.page}>

      {/* ── Price chart with trade markers ── */}
      {bars && bars.length > 0 && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>
              PRICE · {ticker} · {interval.toUpperCase()}
            </span>
            <span className={styles.panelSub}>
              {tradeMarkers.length} trades ·{" "}
              <span style={{ color: "#ffb53b" }}>▲</span> entry ·{" "}
              <span style={{ color: "var(--green)" }}>◆</span> exit win ·{" "}
              <span style={{ color: "var(--coral)" }}>◆</span> exit loss
            </span>
          </div>
          <CandlestickChart
            bars={bars}
            height={240}
            maxBars={MAX_CHART_BARS}
            markers={tradeMarkers}
            showEMA20
          />
        </div>
      )}

      {/* ── Trade log ── */}
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>TRADE LOG</span>
          <span className={styles.panelSub}>
            {filteredTrades.length} of {allTrades.length}
          </span>
          <span style={{ flex: 1 }} />
          <span className={styles.counts}>
            <span style={{ color: "var(--amber)" }}>
              {allTrades.filter((t) => t.side === "L").length} L
            </span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--cyan)" }}>
              {allTrades.filter((t) => t.side === "S").length} S
            </span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--green)" }}>{winners} win</span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--coral)" }}>{allTrades.length - winners} loss</span>
          </span>
          <button
            className={styles.btn}
            onClick={() => {
              const header = "#,OPEN,SIDE,ENTRY,EXIT,R,DUR(h),P&L%";
              const rows = filteredTrades.map((t, i) =>
                [
                  i + 1,
                  new Date(t.date).toISOString().slice(0, 16),
                  t.side === "L" ? "L" : "S",
                  t.entry?.toFixed(2) ?? "",
                  t.exit?.toFixed(2) ?? "",
                  t.r?.toFixed(2) ?? "",
                  t.durH ?? "",
                  t.pnl ?? "",
                ].join(",")
              );
              const csv = [header, ...rows].join("\n");
              const blob = new Blob([csv], { type: "text/csv" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `trades_${Date.now()}.csv`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            ↓ CSV
          </button>
        </div>

        {/* Filter bar */}
        <div className={styles.filterBar}>
          <span className={styles.filterLabel}>side:</span>
          {["all", "long", "short"].map((s) => (
            <button
              key={s}
              className={`${styles.pill} ${filterSide === s ? styles.active : ""}`}
              onClick={() => setFilterSide(s)}
            >
              {s}
            </button>
          ))}
          <span className={styles.filterLabel} style={{ marginLeft: 12 }}>pnl:</span>
          {["all", "win", "loss"].map((s) => (
            <button
              key={s}
              className={`${styles.pill} ${filterPnl === s ? styles.active : ""}`}
              onClick={() => setFilterPnl(s)}
            >
              {s}
            </button>
          ))}
          <input
            ref={filterRef}
            className={styles.filterInput}
            placeholder="filter…"
            style={{ marginLeft: "auto" }}
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
        </div>

        {/* Table */}
        <div className={styles.tableWrap}>
          <div className={styles.thead} style={{ gridTemplateColumns: cols }}>
            <span><SortHeader k="n" label="#" /></span>
            <span><SortHeader k="date" label="OPEN" /></span>
            <span><SortHeader k="side" label="SIDE" /></span>
            <span><SortHeader k="entry" label="ENTRY" /></span>
            <span><SortHeader k="exit" label="EXIT" /></span>
            <span><SortHeader k="r" label="R" /></span>
            <span><SortHeader k="durH" label="DUR" /></span>
            <span><SortHeader k="pnl" label="P&L%" /></span>
            <span>EQUITY</span>
          </div>
          {filteredTrades.slice(0, 200).map((t, i) => (
            <div
              key={t.n}
              className={`${styles.trow} ${cursor === i ? styles.selected : ""}`}
              onClick={() => setCursor(i)}
              style={{ gridTemplateColumns: cols }}
            >
              <span className={styles.dim}>{String(t.n).padStart(3, "0")}</span>
              <span className={styles.dim}>t{String(t.idx).padStart(3, "0")}</span>
              <span style={{ color: t.side === "L" ? "var(--amber)" : "var(--cyan)", fontWeight: 700 }}>
                {t.side}
              </span>
              <span>{t.entry?.toLocaleString()}</span>
              <span>{t.exit?.toLocaleString()}</span>
              <span style={{ color: t.r > 0 ? "var(--green)" : "var(--coral)" }}>
                {t.r?.toFixed(1)}
              </span>
              <span>{t.durH}h</span>
              <span style={{ color: t.pnl > 0 ? "var(--green)" : "var(--coral)", fontWeight: 700 }}>
                {t.pnl > 0 ? "+" : ""}{t.pnl}
              </span>
              <Sparkline
                data={equity.slice(Math.max(0, t.idx - 5), t.idx + 2).map((e) => e.v)}
                width={80}
                height={12}
                color={t.pnl > 0 ? "#6fd17a" : "#ff7a55"}
              />
            </div>
          ))}
        </div>

        <div className={styles.footer}>
          <span className={styles.dim}>
            <kbd>j</kbd>↓ <kbd>k</kbd>↑ · <kbd>f</kbd> filter
          </span>
          <span style={{ flex: 1 }} />
          <span className={styles.dim}>cursor {cursor + 1}/{filteredTrades.length}</span>
        </div>
      </div>

      {/* ── Analysis panels ── */}
      <TradeAnalysisPanels trades={allTrades} />

    </div>
  );
}
