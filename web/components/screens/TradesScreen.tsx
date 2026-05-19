"use client";
import { useEffect, useRef, useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunTrades } from "@/hooks/useRun";
import { Sparkline } from "@/components/charts/Sparkline";
import styles from "./TradesScreen.module.css";
import type { Trade } from "@/lib/fixtures";

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

  const tradesQuery = useRunTrades(activeRunId || null, {
    side: filterSide !== "all" ? filterSide.toUpperCase() : undefined,
    pnl: filterPnl !== "all" ? filterPnl : undefined,
    limit: 200,
  });

  // Use API trades if available, else fixture
  const rawTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades as Trade[])
      : run?.trades ?? [];

  // Client-side filter + sort (applied to fixture data; API already filters)
  const trades = [...rawTrades]
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
      const av = a[sortKey],
        bv = b[sortKey];
      if (av == null || bv == null) return 0;
      return (av < bv ? -1 : av > bv ? 1 : 0) * sortDir;
    });

  // j/k navigation — but not when in an input
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "j") {
        setCursor((c) => Math.min(trades.length - 1, c + 1));
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
  }, [trades.length]);

  const equity = run?.equity ?? [];
  const winners = rawTrades.filter((t) => t.pnl > 0).length;
  const losers = rawTrades.length - winners;

  const cols = "32px 72px 44px 88px 88px 52px 52px 72px 88px";

  function SortHeader({ k, label }: { k: keyof Trade; label: string }) {
    return (
      <span
        className={styles.sortable}
        onClick={() => {
          if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1));
          else {
            setSortKey(k);
            setSortDir(1);
          }
        }}
      >
        {label}
        {sortKey === k ? (sortDir > 0 ? " ↑" : " ↓") : ""}
      </span>
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>TRADE LOG</span>
          <span className={styles.panelSub}>
            {trades.length} of {rawTrades.length}
          </span>
          <span style={{ flex: 1 }} />
          <span className={styles.counts}>
            <span style={{ color: "var(--amber)" }}>
              {rawTrades.filter((t) => t.side === "L").length} L
            </span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--cyan)" }}>
              {rawTrades.filter((t) => t.side === "S").length} S
            </span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--green)" }}>{winners} win</span>
            &nbsp;·&nbsp;
            <span style={{ color: "var(--coral)" }}>{losers} loss</span>
          </span>
          <button className={styles.btn}>↓ CSV</button>
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
          <span className={styles.filterLabel} style={{ marginLeft: 12 }}>
            pnl:
          </span>
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
            <span>
              <SortHeader k="n" label="#" />
            </span>
            <span>
              <SortHeader k="date" label="OPEN" />
            </span>
            <span>
              <SortHeader k="side" label="SIDE" />
            </span>
            <span>
              <SortHeader k="entry" label="ENTRY" />
            </span>
            <span>
              <SortHeader k="exit" label="EXIT" />
            </span>
            <span>
              <SortHeader k="r" label="R" />
            </span>
            <span>
              <SortHeader k="durH" label="DUR" />
            </span>
            <span>
              <SortHeader k="pnl" label="P&L%" />
            </span>
            <span>EQUITY</span>
          </div>
          {trades.slice(0, 200).map((t, i) => (
            <div
              key={t.n}
              className={`${styles.trow} ${cursor === i ? styles.selected : ""}`}
              onClick={() => setCursor(i)}
              style={{ gridTemplateColumns: cols }}
            >
              <span className={styles.dim}>{String(t.n).padStart(3, "0")}</span>
              <span className={styles.dim}>t{String(t.idx).padStart(3, "0")}</span>
              <span
                style={{
                  color: t.side === "L" ? "var(--amber)" : "var(--cyan)",
                  fontWeight: 700,
                }}
              >
                {t.side}
              </span>
              <span>{t.entry?.toLocaleString()}</span>
              <span>{t.exit?.toLocaleString()}</span>
              <span
                style={{ color: t.r > 0 ? "var(--green)" : "var(--coral)" }}
              >
                {t.r?.toFixed(1)}
              </span>
              <span>{t.durH}h</span>
              <span
                style={{
                  color: t.pnl > 0 ? "var(--green)" : "var(--coral)",
                  fontWeight: 700,
                }}
              >
                {t.pnl > 0 ? "+" : ""}
                {t.pnl}
              </span>
              <Sparkline
                data={equity
                  .slice(Math.max(0, t.idx - 5), t.idx + 2)
                  .map((e) => e.v)}
                width={80}
                height={12}
                color={t.pnl > 0 ? "#6fd17a" : "#ff7a55"}
              />
            </div>
          ))}
        </div>

        <div className={styles.footer}>
          <span className={styles.dim}>
            <kbd>j</kbd>↓ <kbd>k</kbd>↑ <kbd>↵</kbd> open · <kbd>f</kbd>{" "}
            filter
          </span>
          <span style={{ flex: 1 }} />
          <span className={styles.dim}>
            cursor {cursor + 1}/{trades.length}
          </span>
        </div>
      </div>
    </div>
  );
}
