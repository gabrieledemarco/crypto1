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
  is_return?: number;
  oos_return?: number;
  is_n_trades: number;
  oos_n_trades: number;
  is_max_dd: number;
  oos_max_dd: number;
  efficiency_factor?: number;
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

  const meanISSharpe  = folds.reduce((a, f) => a + f.is_sharpe,  0) / n;
  const meanOOSSharpe = folds.reduce((a, f) => a + f.oos_sharpe, 0) / n;
  const wfe = meanISSharpe !== 0 ? meanOOSSharpe / meanISSharpe : 0;
  const positiveFolds = folds.filter((f) => f.oos_sharpe > 0).length;
  const pctPositive   = (positiveFolds / n) * 100;
  const meanISRet  = folds.reduce((a, f) => a + (f.is_return  ?? f.is_cagr),  0) / n;
  const meanOOSRet = folds.reduce((a, f) => a + (f.oos_return ?? f.oos_cagr), 0) / n;
  const meanOOSCagr   = folds.reduce((a, f) => a + f.oos_cagr,   0) / n;
  const meanOOSMaxDD  = folds.reduce((a, f) => a + f.oos_max_dd, 0) / n;
  const positiveCagr  = folds.filter((f) => f.oos_cagr > 0).length;
  const pctPosCagr    = (positiveCagr / n) * 100;
  const meanOOSTrades = Math.round(folds.reduce((a, f) => a + f.oos_n_trades, 0) / n);

  const wfeColor      = wfe >= 0.7 ? "var(--green)" : wfe >= 0.4 ? "var(--amber)" : "var(--coral)";
  const pctColor      = pctPositive >= 60 ? "var(--green)" : pctPositive >= 40 ? "var(--amber)" : "var(--coral)";
  const shpColor      = meanOOSSharpe > 0 ? "var(--green)" : "var(--coral)";
  const isRetColor    = meanISRet  >= 0 ? "var(--amber)" : "var(--coral)";
  const oosRetColor   = meanOOSRet >= 0 ? "var(--cyan)"  : "var(--coral)";
  const cagrColor     = meanOOSCagr > 0 ? "var(--green)" : "var(--coral)";
  const pctCagrColor  = pctPosCagr >= 60 ? "var(--green)" : pctPosCagr >= 40 ? "var(--amber)" : "var(--coral)";

  return (
    <div className={styles.panel} style={{ gridColumn: "span 12" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>WALK-FORWARD SUMMARY</span>
        <span className={styles.panelSub}>{n} folds</span>
      </div>
      <div className={styles.summaryBar}>
        <SumCell label="WFE" value={fmtN(wfe)} color={wfeColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="% FOLD POSITIVI" value={fmtPct(pctPositive)} color={pctColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="MEAN OOS SHARPE" value={fmtN(meanOOSSharpe)} color={shpColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="REND. IS (media)" value={(meanISRet >= 0 ? "+" : "") + fmtPct(meanISRet)} color={isRetColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="REND. OOS (media)" value={(meanOOSRet >= 0 ? "+" : "") + fmtPct(meanOOSRet)} color={oosRetColor} />
        <div className={styles.summaryDivider} />
        <SumCell label="MEAN OOS MAX DD" value={fmtPct(meanOOSMaxDD)} color="var(--coral)" />
        <div className={styles.summaryDivider} />
        <SumCell label="MEAN OOS TRADES" value={String(meanOOSTrades)} color="var(--dim)" />
        <div className={styles.summaryDivider} />
        <SumCell label="% REND. OOS > 0" value={fmtPct(pctPosCagr)} color={pctCagrColor} />
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
  "28px 72px 72px 72px 72px 64px 64px 64px 64px 64px 64px 64px 48px";

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
            <span>IS SHP</span>
            <span style={{ color: "var(--amber)" }}>IS RET</span>
            <span>IS CAGR</span>
            <span style={{ color: "var(--text)" }}>OOS SHP</span>
            <span style={{ color: "var(--cyan)" }}>OOS RET</span>
            <span style={{ color: "var(--text)" }}>OOS CAGR</span>
            <span style={{ color: "var(--coral)" }}>OOS DD</span>
            <span>TRADES</span>
          </div>
          {folds.map((f, i) => {
            const shpColor   = f.oos_sharpe > 0 ? "var(--green)" : "var(--coral)";
            const cagrColor  = f.oos_cagr > 0   ? "var(--green)" : "var(--coral)";
            const isRetVal   = f.is_return  ?? f.is_cagr;
            const oosRetVal  = f.oos_return ?? f.oos_cagr;
            const isRetColor = isRetVal  >= 0 ? "var(--amber)" : "var(--coral)";
            const oosRetColor = oosRetVal >= 0 ? "var(--cyan)"  : "var(--coral)";
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
                <span className={styles.dim}>{fmtN(f.is_sharpe)}</span>
                <span style={{ color: isRetColor, fontWeight: 600 }}>
                  {isRetVal >= 0 ? "+" : ""}{fmtPct(isRetVal)}
                </span>
                <span className={styles.dim}>{fmtPct(f.is_cagr)}</span>
                <span style={{ color: shpColor, fontWeight: 700 }}>
                  {fmtN(f.oos_sharpe)}
                </span>
                <span style={{ color: oosRetColor, fontWeight: 700 }}>
                  {oosRetVal >= 0 ? "+" : ""}{fmtPct(oosRetVal)}
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

// ── Reusable grouped-bar chart (IS amber vs OOS cyan/coral) ──────────────────

function GroupedBarChart({
  folds,
  isVals,
  oosVals,
  title,
  isLabel,
  oosLabel,
  formatTick,
  W = 540,
  H = 160,
}: {
  folds: WFOFold[];
  isVals: number[];
  oosVals: number[];
  title: string;
  isLabel: string;
  oosLabel: string;
  formatTick: (v: number) => string;
  W?: number;
  H?: number;
}) {
  const PAD = { top: 20, right: 16, bottom: 28, left: 44 };
  const iW = W - PAD.left - PAD.right;
  const iH = H - PAD.top - PAD.bottom;

  const allVals = [...isVals, ...oosVals];
  const minV = Math.min(...allVals, -0.5);
  const maxV = Math.max(...allVals, 0.5);
  const rangeV = maxV - minV || 1;

  const foldW = iW / folds.length;
  const barW  = foldW * 0.32;
  const toX   = (i: number, off: number) => PAD.left + i * foldW + foldW / 2 + off;
  const toY   = (v: number) => PAD.top + iH - ((v - minV) / rangeV) * iH;
  const y0    = toY(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%" }}>
      {/* Title */}
      <text x={PAD.left} y={12} fontSize={9} fill="var(--dim)" fontWeight={600}>
        {title}
      </text>
      {/* y=0 baseline */}
      <line x1={PAD.left} y1={y0} x2={PAD.left + iW} y2={y0}
        stroke="var(--border)" strokeWidth={1} />
      {/* Tick lines */}
      {[minV, 0, maxV].map((v, i) => (
        <g key={i}>
          <line x1={PAD.left} y1={toY(v)} x2={PAD.left + iW} y2={toY(v)}
            stroke="var(--border)" strokeWidth={0.5} strokeDasharray="4 3" />
          <text x={PAD.left - 4} y={toY(v) + 3} textAnchor="end" fontSize={8} fill="var(--faint)">
            {formatTick(v)}
          </text>
        </g>
      ))}
      {/* Bars */}
      {folds.map((_, i) => {
        const isV  = isVals[i]  ?? 0;
        const oosV = oosVals[i] ?? 0;
        const isH  = Math.abs(toY(isV)  - y0);
        const oosH = Math.abs(toY(oosV) - y0);
        const isY  = isV  >= 0 ? toY(isV)  : y0;
        const oosY = oosV >= 0 ? toY(oosV) : y0;
        const cx   = toX(i, 0);
        return (
          <g key={i}>
            <rect x={cx - barW - 1} y={isY} width={barW} height={Math.max(isH, 1)}
              fill="var(--amber)" fillOpacity={0.55}>
              <title>IS {isLabel} fold {i + 1}: {formatTick(isV)}</title>
            </rect>
            <rect x={cx + 1} y={oosY} width={barW} height={Math.max(oosH, 1)}
              fill={oosV >= 0 ? "var(--cyan)" : "var(--coral)"} fillOpacity={0.85}>
              <title>OOS {oosLabel} fold {i + 1}: {formatTick(oosV)}</title>
            </rect>
            <text x={cx} y={PAD.top + iH + 12} textAnchor="middle" fontSize={8} fill="var(--dim)">
              F{i + 1}
            </text>
          </g>
        );
      })}
      {/* Legend */}
      <rect x={W - 100} y={6} width={8} height={8} fill="var(--amber)" fillOpacity={0.55} />
      <text x={W - 88} y={13} fontSize={8} fill="var(--dim)">IS {isLabel}</text>
      <rect x={W - 50} y={6} width={8} height={8} fill="var(--cyan)" fillOpacity={0.85} />
      <text x={W - 38} y={13} fontSize={8} fill="var(--dim)">OOS {oosLabel}</text>
    </svg>
  );
}

// ── IS vs OOS charts + OOS cumulative equity ──────────────────────────────────

function FoldChartsPanel({ folds }: { folds: WFOFold[] }) {
  // ── OOS cumulative equity (uses actual oos_return if present) ──
  const W2 = 1160, H2 = 120;
  const PAD2 = { top: 12, right: 16, bottom: 28, left: 44 };
  const iW2 = W2 - PAD2.left - PAD2.right;
  const iH2 = H2 - PAD2.top - PAD2.bottom;

  const oosEquity: number[] = [1.0];
  for (const f of folds) {
    const foldReturn = f.oos_return !== undefined ? f.oos_return : f.oos_cagr;
    oosEquity.push(oosEquity[oosEquity.length - 1] * (1 + foldReturn / 100));
  }
  const minEq = Math.min(...oosEquity);
  const maxEq = Math.max(...oosEquity);
  const rangeEq = maxEq - minEq || 0.1;
  const toX2 = (i: number) => PAD2.left + (i / (oosEquity.length - 1)) * iW2;
  const toY2 = (v: number) => PAD2.top + iH2 - ((v - minEq) / rangeEq) * iH2;
  const eqPts = oosEquity.map((v, i) => `${toX2(i).toFixed(1)},${toY2(v).toFixed(1)}`).join(" ");
  const eqFill = `${PAD2.left},${toY2(minEq)} ${eqPts} ${toX2(oosEquity.length - 1).toFixed(1)},${toY2(minEq)}`;
  const finalReturn = (oosEquity[oosEquity.length - 1] - 1) * 100;

  const isRetVals  = folds.map((f) => f.is_return  ?? f.is_cagr);
  const oosRetVals = folds.map((f) => f.oos_return ?? f.oos_cagr);

  return (
    <div className={styles.panel} style={{ gridColumn: "span 12" }}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>IS vs OOS — SHARPE &amp; RENDIMENTO per fold</span>
        <span style={{ flex: 1 }} />
        <span className={styles.panelTitle} style={{ marginLeft: 32 }}>OOS EQUITY CUMULATA</span>
        <span className={styles.panelSub} style={{ marginLeft: 8, color: finalReturn >= 0 ? "var(--green)" : "var(--coral)" }}>
          {finalReturn >= 0 ? "+" : ""}{finalReturn.toFixed(1)}%
        </span>
      </div>

      {/* Top row: Sharpe chart | Return chart */}
      <div className={styles.panelBody} style={{ display: "flex", gap: 16, paddingBottom: 0 }}>
        <div style={{ flex: "0 0 50%" }}>
          <GroupedBarChart
            folds={folds}
            isVals={folds.map((f) => f.is_sharpe)}
            oosVals={folds.map((f) => f.oos_sharpe)}
            title="SHARPE RATIO"
            isLabel="Sharpe"
            oosLabel="Sharpe"
            formatTick={(v) => v.toFixed(1)}
          />
        </div>
        <div style={{ flex: "0 0 50%" }}>
          <GroupedBarChart
            folds={folds}
            isVals={isRetVals}
            oosVals={oosRetVals}
            title="RENDIMENTO TOTALE %"
            isLabel="Ret"
            oosLabel="Ret"
            formatTick={(v) => v.toFixed(1) + "%"}
          />
        </div>
      </div>

      {/* Bottom row: OOS cumulative equity full width */}
      <div className={styles.panelBody} style={{ paddingTop: 8 }}>
        <svg viewBox={`0 0 ${W2} ${H2}`} style={{ display: "block", width: "100%" }}>
          {/* Grid */}
          {[minEq, (minEq + maxEq) / 2, maxEq].map((v, i) => (
            <g key={i}>
              <line x1={PAD2.left} y1={toY2(v)} x2={PAD2.left + iW2} y2={toY2(v)}
                stroke="var(--border)" strokeWidth={0.5} strokeDasharray="4 3" />
              <text x={PAD2.left - 4} y={toY2(v) + 3} textAnchor="end" fontSize={8} fill="var(--faint)">
                {((v - 1) * 100).toFixed(0)}%
              </text>
            </g>
          ))}
          {/* Area fill */}
          <polygon points={eqFill} fill="var(--cyan)" fillOpacity={0.15} />
          {/* Line */}
          <polyline points={eqPts} fill="none"
            stroke={finalReturn >= 0 ? "var(--cyan)" : "var(--coral)"} strokeWidth={2} />
          {/* Dots at fold boundaries */}
          {oosEquity.map((v, i) => (
            <circle key={i} cx={toX2(i)} cy={toY2(v)} r={3}
              fill={v >= 1 ? "var(--green)" : "var(--coral)"}
              stroke="var(--bg)" strokeWidth={1} />
          ))}
          {/* X-axis labels */}
          {folds.map((_, i) => (
            <text key={i} x={toX2(i + 1)} y={PAD2.top + iH2 + 12} textAnchor="middle" fontSize={8} fill="var(--dim)">
              F{i + 1}
            </text>
          ))}
          <text x={PAD2.left} y={PAD2.top + iH2 + 12} textAnchor="middle" fontSize={8} fill="var(--faint)">
            start
          </text>
        </svg>
      </div>
    </div>
  );
}

// ── Main screen ───────────────────────────────────────────────────────────────

export function WFOScreen() {
  const { runs, activeRunId } = useStore();
  const wfoQuery = useRunWFO(activeRunId || null);

  // Use API data first; fall back to wfo stored on the run object (e.g. fixture data)
  const run = runs.find((r) => r.id === activeRunId);
  const runWfo = (run as unknown as { wfo?: unknown[] })?.wfo;
  const rawFolds: unknown[] =
    wfoQuery.data && wfoQuery.data.length > 0
      ? wfoQuery.data
      : (runWfo ?? []);

  const folds: WFOFold[] = (rawFolds as unknown[]).filter(
    (r): r is WFOFold =>
      r !== null &&
      typeof r === "object" &&
      "fold" in (r as object) &&
      "oos_sharpe" in (r as object)
  );

  // Show loading indicator while fetching from API
  if (wfoQuery.isLoading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 300,
          fontFamily: "var(--font-mono)",
          color: "var(--faint)",
          fontSize: 11,
        }}
      >
        CARICAMENTO WFO…
      </div>
    );
  }

  if (!folds.length) {
    return (
      <div className={styles.emptyWrap}>
        <div className={styles.emptyTitle}>WFO NON ESEGUITO</div>
        <div className={styles.emptyHint}>
          Abilita WFO in Setup → esegui la strategia
        </div>
      </div>
    );
  }

  return (
    <div className={styles.grid}>
      <SummaryBar folds={folds} />
      <FoldTable folds={folds} />
      <ScatterPanel folds={folds} />
      <FoldChartsPanel folds={folds} />
    </div>
  );
}
