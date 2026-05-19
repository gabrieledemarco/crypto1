"use client";
import { useStore } from "@/store";
import { useRunWFO } from "@/hooks/useRun";
import styles from "./WFOScreen.module.css";

// WFO fold record from /runs/{id}/wfo
interface WFOFold {
  window_config: string;
  fold: number;
  is_sharpe: number;
  oos_sharpe: number;
  is_cagr: number;
  oos_cagr: number;
  is_n_trades: number;
  oos_n_trades: number;
  is_max_dd: number;
  oos_max_dd: number;
}

const FOLD_COLORS = [
  "#5cc1ff",
  "#6fd17a",
  "#ffb53b",
  "#ff7a55",
  "#c084fc",
  "#f472b6",
];

function fmtN(v: number, dec = 2): string {
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(dec);
}

function fmtPct(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(1) + "%";
}

// ── Summary bar ───────────────────────────────────────────────────────────────

function SummaryBar({ folds }: { folds: WFOFold[] }) {
  const n = folds.length;
  if (n === 0) return null;

  const meanISSharpe = folds.reduce((a, f) => a + f.is_sharpe, 0) / n;
  const meanOOSSharpe = folds.reduce((a, f) => a + f.oos_sharpe, 0) / n;
  const wfe = meanISSharpe !== 0 ? meanOOSSharpe / meanISSharpe : 0;
  const positiveFolds = folds.filter((f) => f.oos_sharpe > 0).length;
  const pctPositive = (positiveFolds / n) * 100;
  const meanOOSCagr = folds.reduce((a, f) => a + f.oos_cagr, 0) / n;

  const wfeColor =
    wfe >= 0.7 ? "var(--green)" : wfe >= 0.4 ? "var(--amber)" : "var(--coral)";
  const pctColor = pctPositive >= 60 ? "var(--green)" : pctPositive >= 40 ? "var(--amber)" : "var(--coral)";
  const shpColor = meanOOSSharpe > 0 ? "var(--green)" : "var(--coral)";
  const cagrColor = meanOOSCagr > 0 ? "var(--green)" : "var(--coral)";

  return (
    <div className={styles.panel} style={{ gridColumn: "span 12" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>WALK-FORWARD SUMMARY</span>
        <span className={styles.panelSub}>{n} folds</span>
      </div>
      <div className={styles.summaryBar}>
        <SumCell label="WFE" value={fmtN(wfe)} color={wfeColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="% POSITIVE FOLDS" value={fmtPct(pctPositive)} color={pctColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="MEAN OOS SHARPE" value={fmtN(meanOOSSharpe)} color={shpColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="MEAN OOS CAGR" value={fmtPct(meanOOSCagr)} color={cagrColor} />
      </div>
    </div>
  );
}

function SumCell({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className={styles.sumCell}>
      <div className={styles.sumLabel}>{label}</div>
      <div className={styles.sumVal} style={{ color: color ?? "var(--text)" }}>
        {value}
      </div>
    </div>
  );
}

// ── Per-fold table ────────────────────────────────────────────────────────────

const COL_TEMPLATE =
  "28px 72px 72px 72px 72px 56px 56px 64px 64px 64px 64px 64px 48px";

function FoldTable({ folds }: { folds: WFOFold[] }) {
  return (
    <div className={styles.panel} style={{ gridColumn: "span 8" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>PER-FOLD RESULTS</span>
      </div>
      <div className={styles.panelBody} style={{ padding: 0, overflow: "auto" }}>
        <div className={styles.table}>
          <div
            className={styles.thead}
            style={{ gridTemplateColumns: COL_TEMPLATE }}
          >
            <span>FOLD</span>
            <span>IS START</span>
            <span>IS END</span>
            <span>OOS START</span>
            <span>OOS END</span>
            <span>SL×</span>
            <span>TP×</span>
            <span>IS SHP</span>
            <span>IS CAGR</span>
            <span style={{ color: "var(--text)" }}>OOS SHP</span>
            <span style={{ color: "var(--text)" }}>OOS CAGR</span>
            <span style={{ color: "var(--coral)" }}>OOS DD</span>
            <span>TRADES</span>
          </div>
          {folds.map((f, i) => {
            const shpColor = f.oos_sharpe > 0 ? "var(--green)" : "var(--coral)";
            const cagrColor = f.oos_cagr > 0 ? "var(--green)" : "var(--coral)";
            return (
              <div
                key={i}
                className={styles.trow}
                style={{ gridTemplateColumns: COL_TEMPLATE }}
              >
                <span className={styles.dim}>{i + 1}</span>
                {/* Dates: not available in fold record — show window label */}
                <span className={styles.dim} style={{ fontSize: 9 }} title={f.window_config}>
                  {f.window_config.split(" ")[0]}
                </span>
                <span className={styles.dim} style={{ fontSize: 9 }}>
                  {f.window_config.split(" ")[1] ?? "—"}
                </span>
                <span className={styles.dim} style={{ fontSize: 9 }}>
                  {f.window_config.split(" ")[2] ?? "—"}
                </span>
                <span className={styles.dim} style={{ fontSize: 9 }}>
                  {f.window_config.split(" ")[3] ?? "—"}
                </span>
                <span className={styles.dim}>—</span>
                <span className={styles.dim}>—</span>
                <span className={styles.dim}>{fmtN(f.is_sharpe)}</span>
                <span className={styles.dim}>{fmtPct(f.is_cagr)}</span>
                <span style={{ color: shpColor, fontWeight: 700 }}>
                  {fmtN(f.oos_sharpe)}
                </span>
                <span style={{ color: cagrColor, fontWeight: 700 }}>
                  {fmtPct(f.oos_cagr)}
                </span>
                <span style={{ color: "var(--coral)", fontWeight: 700 }}>
                  {fmtPct(f.oos_max_dd)}
                </span>
                <span className={styles.dim}>{f.oos_n_trades}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── IS vs OOS scatter ─────────────────────────────────────────────────────────

function ScatterPanel({ folds }: { folds: WFOFold[] }) {
  const W = 280;
  const H = 200;
  const PAD = { top: 12, right: 12, bottom: 32, left: 36 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const xs = folds.map((f) => f.is_sharpe);
  const ys = folds.map((f) => f.oos_sharpe);
  const allVals = [...xs, ...ys];
  const minV = Math.min(...allVals, -0.5);
  const maxV = Math.max(...allVals, 0.5);
  const range = maxV - minV || 1;

  const toX = (v: number) => PAD.left + ((v - minV) / range) * innerW;
  const toY = (v: number) => PAD.top + innerH - ((v - minV) / range) * innerH;

  // Horizontal y=0 line
  const y0 = toY(0);
  // Diagonal y=x line
  const diagX1 = toX(minV);
  const diagY1 = toY(minV);
  const diagX2 = toX(maxV);
  const diagY2 = toY(maxV);

  // Axis ticks
  const tickCount = 4;
  const tickStep = range / tickCount;

  return (
    <div className={styles.panel} style={{ gridColumn: "span 4" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>IS vs OOS SHARPE</span>
      </div>
      <div className={styles.panelBody}>
        <svg
          width="100%"
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: "block" }}
        >
          {/* Grid lines */}
          {Array.from({ length: tickCount + 1 }, (_, i) => {
            const v = minV + i * tickStep;
            const yp = toY(v);
            const xp = toX(v);
            return (
              <g key={i}>
                <line
                  x1={PAD.left}
                  y1={yp}
                  x2={PAD.left + innerW}
                  y2={yp}
                  stroke="var(--border)"
                  strokeWidth={0.5}
                />
                <line
                  x1={xp}
                  y1={PAD.top}
                  x2={xp}
                  y2={PAD.top + innerH}
                  stroke="var(--border)"
                  strokeWidth={0.5}
                />
                <text
                  x={PAD.left - 4}
                  y={yp + 3}
                  textAnchor="end"
                  fontSize={8}
                  fill="var(--faint)"
                >
                  {v.toFixed(1)}
                </text>
                <text
                  x={xp}
                  y={PAD.top + innerH + 14}
                  textAnchor="middle"
                  fontSize={8}
                  fill="var(--faint)"
                >
                  {v.toFixed(1)}
                </text>
              </g>
            );
          })}

          {/* y=0 reference line (coral dashed) */}
          {y0 >= PAD.top && y0 <= PAD.top + innerH && (
            <line
              x1={PAD.left}
              y1={y0}
              x2={PAD.left + innerW}
              y2={y0}
              stroke="var(--coral)"
              strokeWidth={1}
              strokeDasharray="4 3"
            />
          )}

          {/* y=x diagonal (amber dashed) */}
          <line
            x1={diagX1}
            y1={diagY1}
            x2={diagX2}
            y2={diagY2}
            stroke="var(--amber)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />

          {/* Dots */}
          {folds.map((f, i) => {
            const cx = toX(f.is_sharpe);
            const cy = toY(f.oos_sharpe);
            const col =
              i < FOLD_COLORS.length
                ? FOLD_COLORS[i]
                : f.oos_sharpe > 0
                ? "#6fd17a"
                : "#ff7a55";
            return (
              <circle
                key={i}
                cx={cx}
                cy={cy}
                r={4}
                fill={col}
                fillOpacity={0.85}
                stroke="var(--bg)"
                strokeWidth={1}
              >
                <title>
                  Fold {i + 1} · IS {fmtN(f.is_sharpe)} / OOS {fmtN(f.oos_sharpe)}
                </title>
              </circle>
            );
          })}

          {/* Axis labels */}
          <text
            x={PAD.left + innerW / 2}
            y={H - 2}
            textAnchor="middle"
            fontSize={9}
            fill="var(--dim)"
          >
            IS Sharpe
          </text>
          <text
            x={10}
            y={PAD.top + innerH / 2}
            textAnchor="middle"
            fontSize={9}
            fill="var(--dim)"
            transform={`rotate(-90, 10, ${PAD.top + innerH / 2})`}
          >
            OOS Sharpe
          </text>
        </svg>
      </div>
    </div>
  );
}

// ── OOS equity overlay ────────────────────────────────────────────────────────

function OOSEquityPanel({ folds }: { folds: WFOFold[] }) {
  // The fold records don't include per-bar equity series — show informational message
  const hasEquityData = false as boolean;

  if (!hasEquityData) {
    return (
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>OOS EQUITY OVERLAY</span>
        </div>
        <div className={styles.equityUnavail}>OOS equity not available</div>
      </div>
    );
  }

  // Unreachable branch — kept for type safety if equity data is added later
  const W = 800;
  const H = 160;
  const PAD = { top: 8, right: 12, bottom: 28, left: 40 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  return (
    <div className={styles.panel} style={{ gridColumn: "span 12" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>OOS EQUITY OVERLAY</span>
      </div>
      <div className={styles.panelBody}>
        <svg
          width="100%"
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: "block" }}
        >
          <rect
            x={PAD.left}
            y={PAD.top}
            width={innerW}
            height={innerH}
            fill="none"
            stroke="var(--border)"
          />
        </svg>
      </div>
    </div>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function WFOScreen() {
  const { activeRunId } = useStore();
  const wfoQuery = useRunWFO(activeRunId || null);

  const rawFolds = wfoQuery.data ?? [];
  const folds: WFOFold[] = (rawFolds as unknown[]).filter(
    (r): r is WFOFold =>
      r !== null &&
      typeof r === "object" &&
      "fold" in (r as object) &&
      "oos_sharpe" in (r as object)
  );

  if (!folds.length) {
    return (
      <div className={styles.emptyWrap}>
        <div className={styles.emptyTitle}>WFO NOT RUN</div>
        <div className={styles.emptyHint}>
          Enable WFO in Setup → run strategy
        </div>
      </div>
    );
  }

  return (
    <div className={styles.grid}>
      <SummaryBar folds={folds} />
      <FoldTable folds={folds} />
      <ScatterPanel folds={folds} />
      <OOSEquityPanel folds={folds} />
    </div>
  );
}
