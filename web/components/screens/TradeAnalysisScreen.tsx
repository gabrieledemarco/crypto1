"use client";
import { useMemo } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunTrades } from "@/hooks/useRun";
import styles from "./TradeAnalysisScreen.module.css";
import type { Trade } from "@/lib/fixtures";

// ─── helpers ────────────────────────────────────────────────────────────────

function mean(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function fmt1(n: number): string {
  return n.toFixed(1);
}

function fmtPct(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}

// ─── direction stats ─────────────────────────────────────────────────────────

interface DirStats {
  label: string;
  trades: number;
  winPct: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  totalPnl: number;
  avgDurH: number;
}

function computeDirStats(trades: Trade[], label: string): DirStats {
  const total = trades.length;
  if (total === 0) {
    return { label, trades: 0, winPct: 0, avgWin: 0, avgLoss: 0, profitFactor: 0, totalPnl: 0, avgDurH: 0 };
  }
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);
  const grossProfit = wins.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
  return {
    label,
    trades: total,
    winPct: total > 0 ? (wins.length / total) * 100 : 0,
    avgWin: mean(wins.map((t) => t.pnl)),
    avgLoss: mean(losses.map((t) => t.pnl)),
    profitFactor: grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? 99 : 0,
    totalPnl: trades.reduce((a, t) => a + t.pnl, 0),
    avgDurH: mean(trades.map((t) => t.durH)),
  };
}

// ─── streak analysis ─────────────────────────────────────────────────────────

interface StreakData {
  maxWin: number;
  maxLoss: number;
  current: number;
  currentType: "win" | "loss" | "none";
  equitySteps: { win: boolean; val: number }[];
}

function computeStreaks(trades: Trade[]): StreakData {
  if (trades.length === 0) {
    return { maxWin: 0, maxLoss: 0, current: 0, currentType: "none", equitySteps: [] };
  }
  let maxWin = 0, maxLoss = 0;
  let curWin = 0, curLoss = 0;
  const equitySteps: { win: boolean; val: number }[] = [];
  let runningEq = 1;

  for (const t of trades) {
    const win = t.pnl > 0;
    runningEq *= 1 + t.pnl / 100;
    equitySteps.push({ win, val: runningEq });
    if (win) { curWin++; curLoss = 0; }
    else { curLoss++; curWin = 0; }
    if (curWin > maxWin) maxWin = curWin;
    if (curLoss > maxLoss) maxLoss = curLoss;
  }

  // current streak from the end
  const lastWin = trades[trades.length - 1].pnl > 0;
  let current = 1;
  for (let i = trades.length - 2; i >= 0; i--) {
    if ((trades[i].pnl > 0) === lastWin) current++;
    else break;
  }

  return { maxWin, maxLoss, current, currentType: lastWin ? "win" : "loss", equitySteps };
}

// ─── rolling drift ───────────────────────────────────────────────────────────

interface DriftData {
  rolling: number[];
  meanWinRate: number;
  slope: number;
  deteriorating: boolean;
}

function computeDrift(trades: Trade[]): DriftData {
  if (trades.length < 30) {
    const mwr = trades.length > 0 ? trades.filter((t) => t.pnl > 0).length / trades.length : 0;
    return { rolling: [], meanWinRate: mwr, slope: 0, deteriorating: false };
  }
  const wins: number[] = trades.map((t) => (t.pnl > 0 ? 1 : 0));
  const rolling: number[] = [];
  for (let i = 29; i < wins.length; i++) {
    const window = wins.slice(i - 29, i + 1);
    rolling.push(window.reduce((a, b) => a + b, 0) / 30);
  }
  const meanWinRate = wins.reduce((a, b) => a + b, 0) / wins.length;

  // linear regression on rolling win rates
  const n = rolling.length;
  const xs = Array.from({ length: n }, (_, i) => i);
  const xMean = mean(xs);
  const yMean = mean(rolling);
  const num = xs.reduce((a, x, i) => a + (x - xMean) * (rolling[i] - yMean), 0);
  const den = xs.reduce((a, x) => a + (x - xMean) ** 2, 0);
  const slope = den !== 0 ? num / den : 0;

  return { rolling, meanWinRate, slope, deteriorating: slope < -0.003 };
}

// ─── hourly heatmap ──────────────────────────────────────────────────────────

interface HourCell {
  hour: number;
  side: "L" | "S" | "ALL";
  total: number;
  wins: number;
  winRate: number;
}

function computeHeatmap(trades: Trade[]): HourCell[] {
  const sides: ("L" | "S" | "ALL")[] = ["L", "S", "ALL"];
  const cells: HourCell[] = [];
  for (const side of sides) {
    for (let h = 0; h < 24; h++) {
      const subset = trades.filter((t) => {
        const hour = new Date(t.date).getUTCHours();
        return hour === h && (side === "ALL" || t.side === side);
      });
      const wins = subset.filter((t) => t.pnl > 0).length;
      cells.push({
        hour: h,
        side,
        total: subset.length,
        wins,
        winRate: subset.length > 0 ? wins / subset.length : -1,
      });
    }
  }
  return cells;
}

// ─── P&L histogram ───────────────────────────────────────────────────────────

interface HistBin {
  lo: number;
  hi: number;
  count: number;
  negative: boolean;
}

function computePnlHistogram(trades: Trade[], bins = 50): HistBin[] {
  if (trades.length === 0) return [];
  const pnls = trades.map((t) => t.pnl);
  const lo = Math.min(...pnls);
  const hi = Math.max(...pnls);
  if (lo === hi) return [];
  const width = (hi - lo) / bins;
  const result: HistBin[] = Array.from({ length: bins }, (_, i) => ({
    lo: lo + i * width,
    hi: lo + (i + 1) * width,
    count: 0,
    negative: lo + i * width < 0,
  }));
  for (const pnl of pnls) {
    const idx = Math.min(Math.floor((pnl - lo) / width), bins - 1);
    result[idx].count++;
  }
  return result;
}

// ─── SVG helpers ─────────────────────────────────────────────────────────────

function lerpColor(t: number, lo: [number, number, number], hi: [number, number, number]): string {
  const r = Math.round(lo[0] + (hi[0] - lo[0]) * t);
  const g = Math.round(lo[1] + (hi[1] - lo[1]) * t);
  const b = Math.round(lo[2] + (hi[2] - lo[2]) * t);
  return `rgb(${r},${g},${b})`;
}

// Coral: #ff7a55  → rgb(255,122,85)
// Green: #6fd17a → rgb(111,209,122)
// Gray: #3a3c28
const COLOR_CORAL: [number, number, number] = [255, 122, 85];
const COLOR_GREEN: [number, number, number] = [111, 209, 122];
const COLOR_GRAY = "#3a3c28";
const COLOR_PANEL2 = "#1d1f15";

function heatmapCellColor(winRate: number): string {
  if (winRate < 0) return COLOR_GRAY; // no data
  if (winRate < 0.5) {
    // 0 → coral, 0.5 → midpoint
    const t = winRate / 0.5;
    return lerpColor(t, COLOR_CORAL, [185, 165, 105]);
  } else {
    const t = (winRate - 0.5) / 0.5;
    return lerpColor(t, [185, 165, 105], COLOR_GREEN);
  }
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function DirectionTable({ trades }: { trades: Trade[] }) {
  const longs = trades.filter((t) => t.side === "L");
  const shorts = trades.filter((t) => t.side === "S");
  const rows: [string, Trade[], string][] = [
    ["LONG", longs, "var(--amber)"],
    ["SHORT", shorts, "var(--cyan)"],
    ["ALL", trades, "var(--green)"],
  ];

  return (
    <table className={styles.dirTable}>
      <thead>
        <tr className={styles.dirThead}>
          <th>SIDE</th>
          <th>TRADES</th>
          <th>WIN%</th>
          <th>AVG WIN%</th>
          <th>AVG LOSS%</th>
          <th>PROFIT FACTOR</th>
          <th>TOTAL P&L</th>
          <th>AVG DUR</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, subset, color]) => {
          const s = computeDirStats(subset, label);
          return (
            <tr key={label} className={styles.dirRow}>
              <td style={{ color }}>{label}</td>
              <td className={styles.dim}>{s.trades}</td>
              <td style={{ color: s.winPct >= 50 ? "var(--green)" : "var(--coral)" }}>
                {fmt1(s.winPct)}%
              </td>
              <td style={{ color: "var(--green)" }}>
                {s.avgWin > 0 ? "+" + fmt1(s.avgWin) + "%" : "—"}
              </td>
              <td style={{ color: "var(--coral)" }}>
                {s.avgLoss < 0 ? fmt1(s.avgLoss) + "%" : "—"}
              </td>
              <td style={{ color: s.profitFactor >= 1 ? "var(--green)" : "var(--coral)", fontWeight: 700 }}>
                {s.profitFactor === 0 ? "—" : s.profitFactor >= 99 ? "∞" : fmt1(s.profitFactor)}
              </td>
              <td style={{ color: s.totalPnl >= 0 ? "var(--green)" : "var(--coral)", fontWeight: 700 }}>
                {fmtPct(s.totalPnl)}
              </td>
              <td className={styles.dim}>{fmt1(s.avgDurH)}h</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function HourlyHeatmap({ trades }: { trades: Trade[] }) {
  const cells = useMemo(() => computeHeatmap(trades), [trades]);
  const cellW = 52;
  const cellH = 18;
  const labelW = 28;
  const headers = ["LONG", "SHORT", "ALL"];
  const svgW = labelW + cellW * 3 + 4;
  const svgH = cellH * 24 + 20;

  return (
    <div className={styles.heatmapWrap}>
      <svg
        className={styles.heatmapSvg}
        width={svgW}
        height={svgH}
        style={{ fontFamily: "var(--font-mono)" }}
      >
        {/* Column headers */}
        {headers.map((h, col) => (
          <text
            key={h}
            x={labelW + col * cellW + cellW / 2}
            y={12}
            textAnchor="middle"
            fontSize={9}
            fill="#a3a78c"
          >
            {h}
          </text>
        ))}
        {/* Rows = hours */}
        {Array.from({ length: 24 }, (_, hour) => {
          const y = 18 + hour * cellH;
          const showLabel = hour % 4 === 0;
          return (
            <g key={hour}>
              {showLabel && (
                <text
                  x={labelW - 3}
                  y={y + cellH / 2 + 4}
                  textAnchor="end"
                  fontSize={9}
                  fill="#7e8163"
                >
                  {String(hour).padStart(2, "0")}
                </text>
              )}
              {(["L", "S", "ALL"] as const).map((side, col) => {
                const cell = cells.find((c) => c.hour === hour && c.side === side);
                if (!cell) return null;
                const cx = labelW + col * cellW;
                const bg = heatmapCellColor(cell.winRate);
                const textFill = cell.total === 0 ? "#3a3c28" : "#0c0d0a";
                return (
                  <g key={side}>
                    <rect
                      x={cx + 1}
                      y={y + 1}
                      width={cellW - 2}
                      height={cellH - 2}
                      fill={bg}
                      stroke={COLOR_PANEL2}
                      strokeWidth={1}
                    />
                    {cell.total > 0 && (
                      <text
                        x={cx + cellW / 2}
                        y={y + cellH / 2 + 4}
                        textAnchor="middle"
                        fontSize={9}
                        fill={textFill}
                        fontWeight={600}
                      >
                        {Math.round(cell.winRate * 100)}%
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

function PnlHistogram({ trades }: { trades: Trade[] }) {
  const bins = useMemo(() => computePnlHistogram(trades, 50), [trades]);
  const svgW = 200;
  const svgH = 200;
  const padL = 28;
  const padB = 22;
  const plotW = svgW - padL - 4;
  const plotH = svgH - padB - 8;

  if (bins.length === 0) {
    return (
      <svg width={svgW} height={svgH}>
        <text x={svgW / 2} y={svgH / 2} textAnchor="middle" fontSize={10} fill="#7e8163">
          no data
        </text>
      </svg>
    );
  }

  const maxCount = Math.max(...bins.map((b) => b.count), 1);
  const barW = plotW / bins.length;

  return (
    <svg
      width={svgW}
      height={svgH}
      style={{ fontFamily: "var(--font-mono)", display: "block" }}
    >
      {/* Bars */}
      {bins.map((b, i) => {
        const bh = (b.count / maxCount) * plotH;
        const x = padL + i * barW;
        const y = 8 + plotH - bh;
        return (
          <rect
            key={i}
            x={x + 0.5}
            y={y}
            width={Math.max(barW - 0.5, 0.5)}
            height={bh}
            fill={b.negative ? "#ff7a55" : "#6fd17a"}
            opacity={0.85}
          />
        );
      })}
      {/* Axes */}
      <line x1={padL} y1={8} x2={padL} y2={8 + plotH} stroke="#3a3c28" strokeWidth={1} />
      <line x1={padL} y1={8 + plotH} x2={svgW - 4} y2={8 + plotH} stroke="#3a3c28" strokeWidth={1} />
      {/* Zero line */}
      {(() => {
        const lo = bins[0].lo;
        const hi = bins[bins.length - 1].hi;
        const zeroFrac = (0 - lo) / (hi - lo);
        if (zeroFrac > 0 && zeroFrac < 1) {
          const zx = padL + zeroFrac * plotW;
          return (
            <line x1={zx} y1={8} x2={zx} y2={8 + plotH} stroke="#5a5d3a" strokeWidth={1} strokeDasharray="2,2" />
          );
        }
        return null;
      })()}
      {/* X-axis labels */}
      {[bins[0].lo, 0, bins[bins.length - 1].hi].map((v, i) => {
        const lo = bins[0].lo;
        const hi = bins[bins.length - 1].hi;
        const frac = (v - lo) / (hi - lo);
        const x = padL + frac * plotW;
        if (frac < 0 || frac > 1) return null;
        return (
          <text key={i} x={x} y={svgH - 4} textAnchor="middle" fontSize={8} fill="#7e8163">
            {v.toFixed(1)}%
          </text>
        );
      })}
      {/* Y-axis max label */}
      <text x={padL - 3} y={12} textAnchor="end" fontSize={8} fill="#7e8163">
        {maxCount}
      </text>
    </svg>
  );
}

function StreakPanel({ trades }: { trades: Trade[] }) {
  const streaks = useMemo(() => computeStreaks(trades), [trades]);
  const { equitySteps } = streaks;

  const svgW = 200;
  const svgH = 80;
  const padL = 4;
  const padR = 4;
  const padT = 4;
  const padB = 4;

  const plotW = svgW - padL - padR;
  const plotH = svgH - padT - padB;

  const vals = equitySteps.map((s) => s.val);
  const minV = vals.length > 0 ? Math.min(...vals) : 0;
  const maxV = vals.length > 0 ? Math.max(...vals) : 1;
  const range = maxV - minV || 1;

  const toY = (v: number) => padT + plotH - ((v - minV) / range) * plotH;
  const toX = (i: number) => padL + (i / Math.max(equitySteps.length - 1, 1)) * plotW;

  const linePath = equitySteps
    .map((s, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(s.val).toFixed(1)}`)
    .join(" ");

  return (
    <div>
      <div className={styles.metricRow}>
        <div className={styles.metricCell}>
          <div className={styles.metricLabel}>MAX WIN STREAK</div>
          <div className={styles.metricVal} style={{ color: "var(--green)" }}>
            {streaks.maxWin}
          </div>
        </div>
        <div className={styles.metricCell}>
          <div className={styles.metricLabel}>MAX LOSS STREAK</div>
          <div className={styles.metricVal} style={{ color: "var(--coral)" }}>
            {streaks.maxLoss}
          </div>
        </div>
        <div className={styles.metricCell}>
          <div className={styles.metricLabel}>CURRENT STREAK</div>
          <div
            className={styles.metricVal}
            style={{ color: streaks.currentType === "win" ? "var(--green)" : streaks.currentType === "loss" ? "var(--coral)" : "var(--dim)" }}
          >
            {streaks.currentType === "none" ? "—" : `${streaks.currentType === "win" ? "+" : "-"}${streaks.current}`}
          </div>
        </div>
      </div>
      {equitySteps.length > 1 && (
        <svg
          width={svgW}
          height={svgH}
          style={{ display: "block", fontFamily: "var(--font-mono)" }}
        >
          {/* Win/loss bar background */}
          {equitySteps.map((s, i) => {
            const x = toX(i);
            const nextX = toX(Math.min(i + 1, equitySteps.length - 1));
            const bw = nextX - x;
            return (
              <rect
                key={i}
                x={x}
                y={padT}
                width={Math.max(bw, 1)}
                height={plotH}
                fill={s.win ? "rgba(111,209,122,0.06)" : "rgba(255,122,85,0.06)"}
              />
            );
          })}
          {/* Equity line */}
          {equitySteps.length > 1 && (
            <path d={linePath} fill="none" stroke="#ffb53b" strokeWidth={1.5} />
          )}
        </svg>
      )}
    </div>
  );
}

function DriftChart({ trades }: { trades: Trade[] }) {
  const drift = useMemo(() => computeDrift(trades), [trades]);
  const { rolling, meanWinRate, slope, deteriorating } = drift;

  const svgW = 360;
  const svgH = 120;
  const padL = 32;
  const padR = 8;
  const padT = 8;
  const padB = 20;
  const plotW = svgW - padL - padR;
  const plotH = svgH - padT - padB;

  if (rolling.length < 2) {
    return (
      <div>
        <svg width={svgW} height={svgH}>
          <text x={svgW / 2} y={svgH / 2} textAnchor="middle" fontSize={10} fill="#7e8163">
            {trades.length < 30 ? "need ≥30 trades" : "no data"}
          </text>
        </svg>
      </div>
    );
  }

  const minY = Math.min(...rolling, meanWinRate) - 0.05;
  const maxY = Math.max(...rolling, meanWinRate) + 0.05;
  const rangeY = maxY - minY || 0.1;

  const toY = (v: number) => padT + plotH - ((v - minY) / rangeY) * plotH;
  const toX = (i: number) => padL + (i / (rolling.length - 1)) * plotW;

  const linePath = rolling
    .map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
    .join(" ");

  // trend line
  const n = rolling.length;
  const xMean = (n - 1) / 2;
  const trendY0 = meanWinRate + slope * (0 - xMean);
  const trendYn = meanWinRate + slope * (n - 1 - xMean);
  const trendPath = `M${toX(0).toFixed(1)},${toY(trendY0).toFixed(1)} L${toX(n - 1).toFixed(1)},${toY(trendYn).toFixed(1)}`;

  // Y-axis labels
  const yTicks = [0.25, 0.5, 0.75];

  return (
    <div>
      <svg
        width={svgW}
        height={svgH}
        style={{ display: "block", fontFamily: "var(--font-mono)" }}
      >
        {/* Axes */}
        <line x1={padL} y1={padT} x2={padL} y2={padT + plotH} stroke="#3a3c28" strokeWidth={1} />
        <line x1={padL} y1={padT + plotH} x2={svgW - padR} y2={padT + plotH} stroke="#3a3c28" strokeWidth={1} />

        {/* Y ticks */}
        {yTicks.map((v) => {
          if (v < minY || v > maxY) return null;
          const y = toY(v);
          return (
            <g key={v}>
              <line x1={padL - 3} y1={y} x2={padL} y2={y} stroke="#3a3c28" strokeWidth={1} />
              <text x={padL - 5} y={y + 4} textAnchor="end" fontSize={8} fill="#7e8163">
                {Math.round(v * 100)}%
              </text>
            </g>
          );
        })}

        {/* Mean win rate line */}
        <line
          x1={toX(0)}
          y1={toY(meanWinRate)}
          x2={toX(rolling.length - 1)}
          y2={toY(meanWinRate)}
          stroke="#ffb53b"
          strokeWidth={1}
          strokeDasharray="4,3"
        />

        {/* Rolling win rate line */}
        <path d={linePath} fill="none" stroke="#5cc1ff" strokeWidth={1.5} />

        {/* Trend line */}
        <path d={trendPath} fill="none" stroke={deteriorating ? "#ff7a55" : "#6fd17a"} strokeWidth={1} strokeDasharray="3,2" />

        {/* X-axis label */}
        <text x={padL + plotW / 2} y={svgH - 2} textAnchor="middle" fontSize={8} fill="#7e8163">
          trade index (rolling 30)
        </text>
      </svg>
      <div
        className={styles.driftStatus}
        style={{ color: deteriorating ? "var(--coral)" : "var(--green)", borderColor: deteriorating ? "var(--coral)" : "var(--green)" }}
      >
        {deteriorating ? "⚠ EDGE DETERIORATING" : "✓ EDGE STABLE"}
        <span style={{ color: "var(--dim)", fontWeight: 400, marginLeft: 8, fontSize: 10 }}>
          slope: {(slope * 1000).toFixed(2)}‰/trade
        </span>
      </div>
    </div>
  );
}

// ─── Main screen ─────────────────────────────────────────────────────────────

export function TradeAnalysisScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];

  const tradesQuery = useRunTrades(activeRunId || null, { limit: 500 });

  const isUsingFixture = !tradesQuery.data?.trades?.length;

  if (tradesQuery.isLoading) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: 200, fontFamily: "var(--font-mono)", color: "var(--faint)", fontSize: 11,
      }}>
        CARICAMENTO TRADE…
      </div>
    );
  }

  const rawTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades as Trade[])
      : (run?.trades ?? []);

  const trades = useMemo(() => rawTrades.slice(), [rawTrades]);

  if (trades.length === 0) {
    return (
      <div className={styles.grid}>
        <div className={styles.panel} style={{ gridColumn: "span 12" }}>
          <div className={styles.empty}>NO TRADES — run strategy first</div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.grid}>
      {/* Panel 1 — Direction Breakdown (full width) */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DIRECTION BREAKDOWN</span>
          <span className={styles.panelSub}>{trades.length} trades</span>
          {isUsingFixture && (
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 9,
              color: "var(--amber)", border: "1px solid var(--amber)",
              padding: "1px 5px", letterSpacing: "0.04em",
            }}>
              DEMO DATA
            </span>
          )}
        </div>
        <div className={styles.panelBody}>
          <DirectionTable trades={trades} />
        </div>
      </div>

      {/* Panel 2 — Hourly Heatmap (cols 1–8) */}
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>HOURLY WIN-RATE HEATMAP</span>
          <span className={styles.panelSub}>UTC hour × side</span>
        </div>
        <div className={styles.panelBody} style={{ overflowY: "auto" }}>
          <HourlyHeatmap trades={trades} />
        </div>
      </div>

      {/* Panel 3 — P&L Distribution (cols 9–12) */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>P&L DISTRIBUTION</span>
          <span className={styles.panelSub}>50 bins</span>
        </div>
        <div className={styles.panelBody}>
          <PnlHistogram trades={trades} />
        </div>
      </div>

      {/* Panel 4 — Streak Analysis (cols 1–6) */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>STREAK ANALYSIS</span>
        </div>
        <div className={styles.panelBody}>
          <StreakPanel trades={trades} />
        </div>
      </div>

      {/* Panel 5 — Drift Detection (cols 7–12) */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DRIFT DETECTION</span>
          <span className={styles.panelSub}>rolling 30-trade win rate</span>
        </div>
        <div className={styles.panelBody}>
          <DriftChart trades={trades} />
        </div>
      </div>
    </div>
  );
}
