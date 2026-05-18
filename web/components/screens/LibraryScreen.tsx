"use client";
import { useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useLibrary, useStarStrategy } from "@/hooks/useLibrary";
import styles from "./LibraryScreen.module.css";
import type { LibraryEntry } from "@/lib/fixtures";

type StatusFilter = "ALL" | "live" | "research" | "archived";

export function LibraryScreen() {
  const { goto, setToast } = useStore();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");

  const { data: apiLibrary } = useLibrary();
  const starMutation = useStarStrategy();

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
    setToast(`Loaded "${entry.name}" → Setup`);
    goto("setup");
  };

  return (
    <div className={styles.wrapper}>
      <div className={`${styles.panel} ${styles.panelFull}`}>
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
              className={`${styles.trow} ${entry.starred ? styles.trowStarred : ""}`}
              onClick={() => handleLoad({ stopPropagation: () => {} } as React.MouseEvent, entry)}
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

              <span
                className={styles.metricCell}
                style={{ color: "var(--green)" }}
              >
                {entry.metrics.cagr >= 1
                  ? `${(entry.metrics.cagr).toFixed(1)}%`
                  : `${(entry.metrics.cagr * 100).toFixed(1)}%`}
              </span>

              <span
                className={styles.metricCell}
                style={{ color: "var(--coral)" }}
              >
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
              >
                LOAD →
              </button>
            </div>
          ))}
        </div>
      </div>
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
