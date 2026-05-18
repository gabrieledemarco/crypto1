"use client";
import { useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunSweep } from "@/hooks/useRun";
import { HeatmapGrid } from "@/components/charts/HeatmapGrid";
import styles from "./SweepScreen.module.css";

const SL_RANGE = [1.0, 1.5, 2.0, 2.5, 3.0];
const TP_RANGE = [2.0, 3.0, 4.0, 5.0, 7.0];

export function SweepScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const sweepQuery = useRunSweep(activeRunId || null);

  // Use API sweep (flat array of {sl_mult, tp_mult, sharpe_ratio…}) or fixture grid
  // Fixture grid is number[][], API returns records — handle both
  const fixtureGrid: number[][] = run?.sweep ?? [];
  let grid: number[][] = fixtureGrid;

  if (sweepQuery.data && Array.isArray(sweepQuery.data) && sweepQuery.data.length > 0) {
    const apiRows = sweepQuery.data as { sl_mult: number; tp_mult: number; sharpe_ratio: number }[];
    // Build 5×5 grid from SL_RANGE × TP_RANGE
    const newGrid: number[][] = SL_RANGE.map((sl) =>
      TP_RANGE.map((tp) => {
        const found = apiRows.find((r) => r.sl_mult === sl && r.tp_mult === tp);
        return found?.sharpe_ratio ?? 0;
      })
    );
    grid = newGrid;
  }

  const [sel, setSel] = useState<[number, number]>([2, 3]);
  const [metric, setMetric] = useState("Sharpe");

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

  const yLabels = SL_RANGE.slice(0, rows).map(String);
  const xLabels = TP_RANGE.slice(0, cols).map(String);

  return (
    <div className={styles.grid}>
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>PARAM SWEEP · {metric} · SL × TP</span>
          <span style={{ flex: 1 }} />
          {["Sharpe", "CAGR", "MaxDD"].map((m) => (
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
            <MetricCell label="SL MULT"  value={String(SL_RANGE[sel[0]] ?? sel[0])} color="var(--cyan)" />
            <MetricCell label="TP MULT"  value={String(TP_RANGE[sel[1]] ?? sel[1])} color="var(--cyan)" />
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
              SL {SL_RANGE[best[0]]} · TP {TP_RANGE[best[1]]} ·{" "}
              <b style={{ color: "var(--amber)" }}>{bestVal.toFixed(2)}</b>
            </div>
            <button className={styles.btn} style={{ marginTop: 8 }} onClick={() => setSel(best)}>JUMP →</button>
          </div>

          {nStd > 0.35 && (
            <div className={styles.warn}>⚠ vicini molto rumorosi · probabile overfit</div>
          )}
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
