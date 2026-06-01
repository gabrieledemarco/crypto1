"use client";
import { useState, useMemo, useId } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunSweep, isRealRunId } from "@/hooks/useRun";
import { HeatmapGrid } from "@/components/charts/HeatmapGrid";
import styles from "./SweepScreen.module.css";

const FALLBACK_SL_RANGE = [1.0, 1.5, 2.0, 2.5, 3.0];
const FALLBACK_TP_RANGE = [2.0, 3.0, 4.0, 5.0, 7.0];

type SweepRecord = { sl_mult: number; tp_mult: number; sharpe_ratio?: number; cagr_pct?: number; max_drawdown_pct?: number; profit_factor?: number };

export function SweepScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const sweepQuery = useRunSweep(activeRunId || null);

  const [sel, setSel] = useState<[number, number]>([2, 3]);
  const [metric, setMetric] = useState("Sharpe");

  // Determine if we have API flat-array data or fixture grid data
  const apiRecords = useMemo<SweepRecord[] | null>(() => {
    if (sweepQuery.data && Array.isArray(sweepQuery.data) && sweepQuery.data.length > 0) {
      const first = sweepQuery.data[0];
      if (first && typeof first === "object" && "sl_mult" in (first as object)) {
        return sweepQuery.data as SweepRecord[];
      }
    }
    return null;
  }, [sweepQuery.data]);

  // Derive unique sorted SL/TP ranges from API data; fall back to hardcoded constants
  const SL_RANGE = useMemo<number[]>(() => {
    if (!apiRecords) return FALLBACK_SL_RANGE;
    const vals = [...new Set(apiRecords.map((p) => p.sl_mult))].sort((a, b) => a - b);
    return vals.length > 0 ? vals : FALLBACK_SL_RANGE;
  }, [apiRecords]);

  const TP_RANGE = useMemo<number[]>(() => {
    if (!apiRecords) return FALLBACK_TP_RANGE;
    const vals = [...new Set(apiRecords.map((p) => p.tp_mult))].sort((a, b) => a - b);
    return vals.length > 0 ? vals : FALLBACK_TP_RANGE;
  }, [apiRecords]);

  // Build the grid — API path uses dynamic ranges; fixture path uses raw number[][]
  const grid = useMemo<number[][]>(() => {
    if (apiRecords) {
      const r1 = (n: number) => Math.round(n * 10) / 10;
      return SL_RANGE.map((sl) =>
        TP_RANGE.map((tp) => {
          const found = apiRecords.find((p) => r1(p.sl_mult) === r1(sl) && r1(p.tp_mult) === r1(tp));
          if (!found) return 0;
          if (metric === "Sharpe") return found.sharpe_ratio ?? 0;
          if (metric === "CAGR")   return found.cagr_pct ?? 0;
          if (metric === "MaxDD")  return found.max_drawdown_pct ?? 0;
          return found.profit_factor ?? 0;
        })
      );
    }
    return (run?.sweep ?? []) as number[][];
  }, [apiRecords, SL_RANGE, TP_RANGE, metric, run?.sweep]);

  if (sweepQuery.isLoading) return <div className={styles.empty}>Loading sweep data…</div>;
  if (sweepQuery.isError) return <div className={styles.empty}>Failed to load sweep data</div>;
  if (!isRealRunId(activeRunId) && !apiRecords) return <div className={styles.empty}>Run a backtest to see parameter sweep results</div>;
  if (!grid.length) return <div className={styles.empty}>No sweep data</div>;

  const rows = grid.length;
  const cols = grid[0].length;
  const selVal = grid[sel[0]]?.[sel[1]] ?? 0;

  // Neighbor stats (3×3 window around selected cell)
  const neighbors: number[] = [];
  for (let dr = -1; dr <= 1; dr++) {
    for (let dc = -1; dc <= 1; dc++) {
      const r = sel[0] + dr, c = sel[1] + dc;
      if (r >= 0 && r < rows && c >= 0 && c < cols) neighbors.push(grid[r][c]);
    }
  }
  const nMean = neighbors.reduce((a, b) => a + b, 0) / neighbors.length;
  const nStd = Math.sqrt(neighbors.reduce((a, b) => a + (b - nMean) ** 2, 0) / neighbors.length);
  const robust = nStd < 0.15 ? "STABILE" : nStd < 0.35 ? "MEDIO" : "FRAGILE";
  const robustColor = nStd < 0.15 ? "var(--green)" : nStd < 0.35 ? "var(--amber)" : "var(--coral)";

  // Best cell
  let best: [number, number] = [0, 0];
  let bestVal = -Infinity;
  grid.forEach((row, r) => row.forEach((v, c) => { if (v > bestVal) { bestVal = v; best = [r, c]; } }));

  // Axis labels: use derived ranges for API data, fallback ranges sliced for fixture grids
  const yLabels = (apiRecords ? SL_RANGE : FALLBACK_SL_RANGE.slice(0, rows)).map((v) => v.toFixed(1));
  const xLabels = (apiRecords ? TP_RANGE : FALLBACK_TP_RANGE.slice(0, cols)).map((v) => v.toFixed(1));

  return (
    <div className={styles.grid}>
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>PARAM SWEEP · {metric} · SL × TP</span>
          <span style={{ flex: 1 }} />
          {["Sharpe", "CAGR", "MaxDD", "PF"].map((m) => (
            <button key={m} className={`${styles.pill} ${metric === m ? styles.active : ""}`}
              onClick={() => setMetric(m)}>{m}</button>
          ))}
        </div>
        <div className={styles.panelBody}>
          <div className={styles.heatmapWrap}>
            <div className={styles.axisLabel} style={{ marginBottom: 4 }}>TP →</div>
            <HeatmapGrid
              grid={grid}
              cellSize={42}
              selected={sel}
              onClick={setSel}
              xLabels={xLabels}
              yLabels={yLabels}
            />
            <div className={styles.axisLabel} style={{ marginTop: 6 }}>SL ↓</div>
          </div>
          <div className={styles.legend}>
            <span style={{ color: "var(--coral)" }}>▌ low</span>
            <span style={{ flex: 1, borderTop: "1px solid var(--border)", margin: "0 8px", alignSelf: "center" }} />
            <span style={{ color: "var(--green)" }}>▌ high</span>
          </div>
        </div>
      </div>

      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>SELECTION</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.metricGrid}>
            <MetricCell label="SL MULT"  value={SL_RANGE[sel[0]] != null ? SL_RANGE[sel[0]].toFixed(1) : String(sel[0])} color="var(--cyan)" />
            <MetricCell label="TP MULT"  value={TP_RANGE[sel[1]] != null ? TP_RANGE[sel[1]].toFixed(1) : String(sel[1])} color="var(--cyan)" />
            <MetricCell label={metric}   value={selVal.toFixed(2)} color="var(--amber)" big />
            <MetricCell label="vs BEST"  value={(selVal - bestVal).toFixed(2)}
              color={selVal >= bestVal ? "var(--green)" : "var(--coral)"} />
          </div>

          <div className={styles.section}>
            <div className={styles.sectionLabel}>ROBUSTEZZA · 9 vicini</div>
            <div className={styles.metricGrid} style={{ marginTop: 6 }}>
              <MetricCell label="MEAN"  value={nMean.toFixed(2)} />
              <MetricCell label="STD"   value={nStd.toFixed(2)} />
              <MetricCell label="STATO" value={robust} color={robustColor} />
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionLabel}>BEST PLATEAU</div>
            <div className={styles.mono} style={{ marginTop: 4 }}>
              SL {SL_RANGE[best[0]] != null ? SL_RANGE[best[0]].toFixed(1) : best[0]} · TP {TP_RANGE[best[1]] != null ? TP_RANGE[best[1]].toFixed(1) : best[1]} ·{" "}
              <b style={{ color: "var(--amber)" }}>{bestVal.toFixed(2)}</b>
            </div>
            <button className={styles.btn} style={{ marginTop: 8 }} onClick={() => setSel(best)}>JUMP →</button>
          </div>

          {nStd > 0.35 && (
            <div className={styles.warn}>⚠ vicini molto rumorosi · probabile overfit</div>
          )}
        </div>
      </div>

      {/* Parameter Sensitivity panel — full width below heatmap + selection */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>PARAMETER SENSITIVITY · {metric}</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.sensitivityRow}>
            <SensitivityChart
              label="SL SENSITIVITY"
              xValues={SL_RANGE}
              yValues={SL_RANGE.map((_, i) => grid[i]?.[best[1]] ?? 0)}
              optimalIdx={best[0]}
              xAxisLabel="sl_mult"
            />
            <SensitivityChart
              label="TP SENSITIVITY"
              xValues={TP_RANGE}
              yValues={TP_RANGE.map((_, j) => grid[best[0]]?.[j] ?? 0)}
              optimalIdx={best[1]}
              xAxisLabel="tp_mult"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCell({ label, value, color, big }: { label: string; value: string; color?: string; big?: boolean }) {
  return (
    <div className={styles.metricCell}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricVal} style={{ color: color ?? "var(--text)", fontSize: big ? 20 : 14 }}>{value}</div>
    </div>
  );
}

// ─── SensitivityChart ────────────────────────────────────────────────────────

interface SensitivityChartProps {
  label: string;
  xValues: number[];   // axis tick values (sl or tp range)
  yValues: number[];   // metric values for each tick
  optimalIdx: number;  // index of the best point
  xAxisLabel: string;
}

function SensitivityChart({ label, xValues, yValues, optimalIdx, xAxisLabel }: SensitivityChartProps) {
  const clipId = useId();

  if (xValues.length === 0 || yValues.length === 0) {
    return (
      <div className={styles.sensitivityChart}>
        <div className={styles.chartLabel}>{label}</div>
        <div className={styles.chartEmpty}>no data</div>
      </div>
    );
  }

  // Layout constants
  const W = 380;
  const H = 100;
  const PAD_LEFT = 36;
  const PAD_RIGHT = 12;
  const PAD_TOP = 10;
  const PAD_BOTTOM = 22;
  const innerW = W - PAD_LEFT - PAD_RIGHT;
  const innerH = H - PAD_TOP - PAD_BOTTOM;

  const n = xValues.length;
  const yMin = Math.min(...yValues);
  const yMax = Math.max(...yValues);
  const ySpan = yMax - yMin || 1;

  // Map index → pixel coords
  const toX = (i: number) => PAD_LEFT + (i / Math.max(n - 1, 1)) * innerW;
  const toY = (v: number) => PAD_TOP + innerH - ((v - yMin) / ySpan) * innerH;

  // Reference lines
  const refZeroY = yMin <= 0 && yMax >= 0 ? toY(0) : null;
  const peakThreshold = yMax * 0.8;
  const refPeakY = toY(peakThreshold);

  // Polyline points string
  const polyPoints = yValues.map((v, i) => `${toX(i)},${toY(v)}`).join(" ");

  // Optimal dot
  const optX = toX(optimalIdx);
  const optY = toY(yValues[optimalIdx] ?? yMin);

  // Y-axis ticks (3 ticks: min, mid, max)
  const yTicks = [yMin, (yMin + yMax) / 2, yMax];

  return (
    <div className={styles.sensitivityChart}>
      <div className={styles.chartLabel}>{label}</div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className={styles.chartSvg}
        aria-label={label}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD_LEFT} y={PAD_TOP} width={innerW} height={innerH} />
          </clipPath>
        </defs>

        {/* Y-axis ticks + labels */}
        {yTicks.map((v, i) => {
          const y = toY(v);
          return (
            <g key={i}>
              <line
                x1={PAD_LEFT - 3} y1={y} x2={PAD_LEFT} y2={y}
                stroke="var(--border)" strokeWidth={1}
              />
              <text
                x={PAD_LEFT - 5} y={y + 3}
                textAnchor="end"
                fontSize={7}
                fontFamily="var(--font-mono)"
                fill="var(--faint)"
              >
                {v.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* Y-axis line */}
        <line
          x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={PAD_TOP + innerH}
          stroke="var(--border)" strokeWidth={1}
        />

        {/* X-axis line */}
        <line
          x1={PAD_LEFT} y1={PAD_TOP + innerH} x2={PAD_LEFT + innerW} y2={PAD_TOP + innerH}
          stroke="var(--border)" strokeWidth={1}
        />

        {/* Reference: zero line */}
        {refZeroY !== null && (
          <line
            x1={PAD_LEFT} y1={refZeroY} x2={PAD_LEFT + innerW} y2={refZeroY}
            stroke="var(--border)" strokeWidth={1} strokeDasharray="3 3"
            clipPath={`url(#${clipId})`}
          />
        )}

        {/* Reference: 80%-of-peak threshold */}
        <line
          x1={PAD_LEFT} y1={refPeakY} x2={PAD_LEFT + innerW} y2={refPeakY}
          stroke="var(--border)" strokeWidth={1} strokeDasharray="4 2"
          clipPath={`url(#${clipId})`}
        />
        <text
          x={PAD_LEFT + innerW - 2} y={refPeakY - 2}
          textAnchor="end"
          fontSize={6}
          fontFamily="var(--font-mono)"
          fill="var(--faint)"
        >
          80%
        </text>

        {/* Metric line */}
        <polyline
          points={polyPoints}
          fill="none"
          stroke="var(--amber)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          clipPath={`url(#${clipId})`}
        />

        {/* Optimal dot */}
        <circle
          cx={optX} cy={optY} r={4}
          fill="var(--cyan)"
          stroke="var(--panel)"
          strokeWidth={1.5}
        />

        {/* X-axis tick labels */}
        {xValues.map((v, i) => (
          <text
            key={i}
            x={toX(i)} y={PAD_TOP + innerH + 12}
            textAnchor="middle"
            fontSize={7}
            fontFamily="var(--font-mono)"
            fill="var(--faint)"
          >
            {v.toFixed(1)}
          </text>
        ))}

        {/* X-axis param name */}
        <text
          x={PAD_LEFT + innerW / 2} y={H - 1}
          textAnchor="middle"
          fontSize={6}
          fontFamily="var(--font-mono)"
          fill="var(--dim)"
        >
          {xAxisLabel}
        </text>
      </svg>
    </div>
  );
}
