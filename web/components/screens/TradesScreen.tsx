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

// ─── Color helpers (shared with DOW heatmap) ─────────────────────────────────

function lerpRgb(
  t: number,
  lo: [number, number, number],
  hi: [number, number, number]
): string {
  const r = Math.round(lo[0] + (hi[0] - lo[0]) * t);
  const g = Math.round(lo[1] + (hi[1] - lo[1]) * t);
  const b = Math.round(lo[2] + (hi[2] - lo[2]) * t);
  return `rgb(${r},${g},${b})`;
}
const C_CORAL: [number, number, number] = [255, 122, 85];
const C_GREEN: [number, number, number] = [111, 209, 122];
const C_GRAY = "#3a3c28";

function winRateColor(wr: number): string {
  if (wr < 0) return C_GRAY;
  if (wr < 0.5) return lerpRgb(wr / 0.5, C_CORAL, [185, 165, 105]);
  return lerpRgb((wr - 0.5) / 0.5, [185, 165, 105], C_GREEN);
}

// ─── Feature 1: Day-of-Week Win Rate Heatmap ─────────────────────────────────

const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// JS getDay(): 0=Sun,1=Mon,...,6=Sat  — we display Mon-first (index 0→Mon)
const DOW_ORDER = [1, 2, 3, 4, 5, 6, 0]; // Mon … Sun

interface DowCell {
  dow: number;       // 0–6 JS getDay value
  side: "L" | "S" | "ALL";
  total: number;
  wins: number;
  winRate: number;   // -1 = no data
}

function computeDowHeatmap(trades: Trade[]): DowCell[] {
  const sides: ("L" | "S" | "ALL")[] = ["L", "S", "ALL"];
  const cells: DowCell[] = [];
  for (const side of sides) {
    for (const dow of DOW_ORDER) {
      const subset = trades.filter((t) => {
        const d = new Date(t.date).getDay();
        return d === dow && (side === "ALL" || t.side === side);
      });
      const wins = subset.filter((t) => t.pnl > 0).length;
      cells.push({
        dow,
        side,
        total: subset.length,
        wins,
        winRate: subset.length > 0 ? wins / subset.length : -1,
      });
    }
  }
  return cells;
}

function DowHeatmap({ trades }: { trades: Trade[] }) {
  const cells = useMemo(() => computeDowHeatmap(trades), [trades]);
  if (trades.length === 0) {
    return <div className={styles.heatmapEmpty}>no data</div>;
  }

  const cellW = 56;
  const cellH = 22;
  const labelW = 30;
  const headerH = 18;
  const cols = ["LONG", "SHORT", "ALL"];
  const svgW = labelW + cols.length * cellW + 2;
  const svgH = headerH + DOW_ORDER.length * cellH + 2;

  return (
    <div className={styles.heatmapWrap}>
      <svg
        className={styles.heatmapSvg}
        viewBox={`0 0 ${svgW} ${svgH}`}
        style={{ width: svgW, height: svgH }}
      >
        {/* Column headers */}
        {cols.map((col, ci) => (
          <text
            key={col}
            x={labelW + ci * cellW + cellW / 2}
            y={headerH - 4}
            textAnchor="middle"
            fontSize={8}
            fill="#888"
            fontFamily="var(--font-mono)"
          >
            {col}
          </text>
        ))}

        {DOW_ORDER.map((dow, ri) => {
          const dowLabel = DOW_LABELS[ri]; // Mon=0 … Sun=6 in display order
          const y = headerH + ri * cellH;
          return (
            <g key={dow}>
              {/* Row label */}
              <text
                x={labelW - 3}
                y={y + cellH / 2 + 4}
                textAnchor="end"
                fontSize={8}
                fill="#888"
                fontFamily="var(--font-mono)"
              >
                {dowLabel}
              </text>
              {/* Cells */}
              {(["L", "S", "ALL"] as const).map((side, ci) => {
                const cell = cells.find((c) => c.dow === dow && c.side === side)!;
                const bg = winRateColor(cell.winRate);
                const x = labelW + ci * cellW;
                return (
                  <g key={side}>
                    <rect
                      x={x + 1}
                      y={y + 1}
                      width={cellW - 2}
                      height={cellH - 2}
                      fill={bg}
                      rx={2}
                    />
                    {cell.winRate >= 0 ? (
                      <>
                        <text
                          x={x + cellW / 2}
                          y={y + cellH / 2 + 2}
                          textAnchor="middle"
                          fontSize={8}
                          fontWeight={700}
                          fill="#fff"
                          fontFamily="var(--font-mono)"
                        >
                          {Math.round(cell.winRate * 100)}%
                        </text>
                        <text
                          x={x + cellW - 3}
                          y={y + cellH - 3}
                          textAnchor="end"
                          fontSize={6}
                          fill="rgba(255,255,255,0.55)"
                          fontFamily="var(--font-mono)"
                        >
                          {cell.total}
                        </text>
                      </>
                    ) : (
                      <text
                        x={x + cellW / 2}
                        y={y + cellH / 2 + 3}
                        textAnchor="middle"
                        fontSize={7}
                        fill="#555"
                        fontFamily="var(--font-mono)"
                      >
                        —
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ─── Feature 2: Holding Time Histogram ───────────────────────────────────────

const DUR_BINS = ["<1h", "1-4h", "4-8h", "8-24h", "1-3d", ">3d"];
const DUR_EDGES = [0, 1, 4, 8, 24, 72, Infinity];

function binDuration(durH: number): number {
  for (let i = 0; i < DUR_EDGES.length - 1; i++) {
    if (durH >= DUR_EDGES[i] && durH < DUR_EDGES[i + 1]) return i;
  }
  return DUR_EDGES.length - 2;
}

function HoldingHistogram({ trades }: { trades: Trade[] }) {
  const counts = useMemo(() => {
    const arr = new Array(DUR_BINS.length).fill(0);
    for (const t of trades) {
      if (t.durH != null) arr[binDuration(t.durH)]++;
    }
    return arr;
  }, [trades]);

  const total = counts.reduce((s: number, c: number) => s + c, 0);
  if (total === 0) {
    return <div className={styles.heatmapEmpty}>no data</div>;
  }

  const maxCount = Math.max(...counts, 1);
  const barH = 14;
  const gap = 3;
  const labelW = 36;
  const statW = 60;
  const barAreaW = 160;
  const svgW = labelW + barAreaW + statW + 4;
  const svgH = DUR_BINS.length * (barH + gap) + 4;

  return (
    <div className={styles.histWrap}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        style={{ width: svgW, height: svgH, display: "block" }}
      >
        {DUR_BINS.map((label, i) => {
          const count = counts[i] as number;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const barW = (count / maxCount) * barAreaW;
          const y = i * (barH + gap) + 2;
          return (
            <g key={label}>
              {/* Label */}
              <text
                x={labelW - 3}
                y={y + barH / 2 + 3}
                textAnchor="end"
                fontSize={8}
                fill="#888"
                fontFamily="var(--font-mono)"
              >
                {label}
              </text>
              {/* Bar background */}
              <rect
                x={labelW}
                y={y}
                width={barAreaW}
                height={barH}
                fill="rgba(255,255,255,0.04)"
                rx={2}
              />
              {/* Bar fill */}
              {barW > 0 && (
                <rect
                  x={labelW}
                  y={y}
                  width={barW}
                  height={barH}
                  fill="var(--amber)"
                  rx={2}
                  opacity={0.85}
                />
              )}
              {/* Count + % */}
              <text
                x={labelW + barAreaW + 4}
                y={y + barH / 2 + 3}
                fontSize={8}
                fill="#aaa"
                fontFamily="var(--font-mono)"
              >
                {count} · {pct.toFixed(0)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ─── Feature 3: PnL CDF ──────────────────────────────────────────────────────

function PnlCdf({ trades }: { trades: Trade[] }) {
  const points = useMemo(() => {
    if (trades.length === 0) return { pts: "", zeroX: -1, minPnl: 0, maxPnl: 0 };
    const sorted = [...trades].map((t) => t.pnl).sort((a, b) => a - b);
    const n = sorted.length;
    const minPnl = sorted[0];
    const maxPnl = sorted[n - 1];
    return { sorted, n, minPnl, maxPnl };
  }, [trades]);

  if (trades.length === 0) {
    return <div className={styles.heatmapEmpty}>no data</div>;
  }

  const { sorted, n, minPnl, maxPnl } = points as {
    sorted: number[];
    n: number;
    minPnl: number;
    maxPnl: number;
  };

  const W = 280;
  const H = 90;
  const padL = 30;
  const padR = 8;
  const padT = 8;
  const padB = 16;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const pnlRange = maxPnl - minPnl || 1;

  function xOf(pnl: number) {
    return padL + ((pnl - minPnl) / pnlRange) * plotW;
  }
  function yOf(prob: number) {
    return padT + (1 - prob) * plotH;
  }

  const polyline = sorted
    .map((pnl, i) => `${xOf(pnl).toFixed(1)},${yOf((i + 1) / n).toFixed(1)}`)
    .join(" ");

  const zeroX = xOf(0);
  const showZero = minPnl < 0 && maxPnl > 0;

  // Shade area left of zero (losses region)
  const lossPts = sorted
    .filter((p) => p <= 0)
    .map((pnl, i) => `${xOf(pnl).toFixed(1)},${yOf((i + 1) / n).toFixed(1)}`);

  const shadeD =
    lossPts.length > 0
      ? `M ${padL},${yOf(padB / H)} ${lossPts.join(" ")} L ${zeroX},${padT + plotH} L ${padL},${padT + plotH} Z`
      : "";

  const yLabels = [
    { prob: 1.0, label: "100%" },
    { prob: 0.75, label: "75%" },
    { prob: 0.5, label: "50%" },
    { prob: 0.25, label: "25%" },
    { prob: 0.0, label: "0%" },
  ];

  return (
    <div className={styles.cdfWrap}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: W, height: H, display: "block" }}
      >
        {/* Plot area border */}
        <rect
          x={padL}
          y={padT}
          width={plotW}
          height={plotH}
          fill="rgba(255,255,255,0.02)"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={0.5}
        />

        {/* Y-axis gridlines + labels */}
        {yLabels.map(({ prob, label }) => {
          const y = yOf(prob);
          return (
            <g key={label}>
              <line
                x1={padL}
                y1={y}
                x2={padL + plotW}
                y2={y}
                stroke="rgba(255,255,255,0.07)"
                strokeWidth={0.5}
              />
              <text
                x={padL - 3}
                y={y + 3}
                textAnchor="end"
                fontSize={6.5}
                fill="#666"
                fontFamily="var(--font-mono)"
              >
                {label}
              </text>
            </g>
          );
        })}

        {/* Zero PnL dashed line */}
        {showZero && (
          <line
            x1={zeroX}
            y1={padT}
            x2={zeroX}
            y2={padT + plotH}
            stroke="rgba(255,255,255,0.25)"
            strokeWidth={0.8}
            strokeDasharray="3,2"
          />
        )}

        {/* Loss shade */}
        {shadeD && (
          <path d={shadeD} fill="rgba(255,122,85,0.12)" />
        )}

        {/* CDF curve */}
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--cyan)"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />

        {/* X-axis labels: min, 0, max */}
        <text
          x={padL}
          y={H - 2}
          textAnchor="middle"
          fontSize={6.5}
          fill="#555"
          fontFamily="var(--font-mono)"
        >
          {minPnl.toFixed(1)}
        </text>
        {showZero && (
          <text
            x={zeroX}
            y={H - 2}
            textAnchor="middle"
            fontSize={6.5}
            fill="#888"
            fontFamily="var(--font-mono)"
          >
            0
          </text>
        )}
        <text
          x={padL + plotW}
          y={H - 2}
          textAnchor="middle"
          fontSize={6.5}
          fill="#555"
          fontFamily="var(--font-mono)"
        >
          {maxPnl.toFixed(1)}
        </text>
      </svg>
      <div className={styles.cdfCaption}>P(trade PnL ≤ x)</div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

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

  const tradesQuery = useRunTrades(activeRunId || null, { limit: 500 });
  const allTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades as Trade[])
      : run?.trades ?? [];

  const ticker = isReal ? (run?.strategy ?? null) : null;
  const interval = run?.params?.timeframe ?? "1d";
  const { data: bars } = useAssetBars(ticker, interval);

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

      {/* ── Quant visualizations row ── */}
      <div className={styles.quantRow}>

        {/* Day-of-Week Heatmap */}
        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>DAY-OF-WEEK</span>
            <span className={styles.panelSub}>win rate by day · L / S / ALL</span>
          </div>
          <div className={styles.quantBody}>
            <DowHeatmap trades={allTrades} />
          </div>
        </div>

        {/* Holding Time Histogram */}
        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>HOLDING TIME DISTRIBUTION</span>
            <span className={styles.panelSub}>{allTrades.length} trades</span>
          </div>
          <div className={styles.quantBody}>
            <HoldingHistogram trades={allTrades} />
          </div>
        </div>

        {/* PnL CDF */}
        <div className={styles.quantPanel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>PnL CDF</span>
            <span className={styles.panelSub}>cumulative distribution</span>
          </div>
          <div className={styles.quantBody}>
            <PnlCdf trades={allTrades} />
          </div>
        </div>

      </div>

    </div>
  );
}
