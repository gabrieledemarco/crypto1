"use client";
import { useMemo } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunEquity } from "@/hooks/useRun";
import { Histogram } from "@/components/charts/Histogram";
import { Sparkline } from "@/components/charts/Sparkline";
import styles from "./UnderwaterScreen.module.css";
import type { EquityPoint, DDPeriod } from "@/lib/fixtures";

const DD_THRESHOLD = 0.005;

function computeDdPeriods(equity: EquityPoint[]): DDPeriod[] {
  if (equity.length < 2) return [];
  const periods: DDPeriod[] = [];
  let peak = equity[0].v, peakIdx = 0;
  let troughV = equity[0].v, troughIdx = 0;
  let inDD = false;

  for (let i = 1; i < equity.length; i++) {
    const v = equity[i].v;
    if (!inDD) {
      if (v >= peak) { peak = v; peakIdx = i; troughV = v; troughIdx = i; }
      else if ((peak - v) / peak > DD_THRESHOLD) { inDD = true; troughV = v; troughIdx = i; }
    } else {
      if (v < troughV) { troughV = v; troughIdx = i; }
      if (v >= peak * 0.998) {
        periods.push({
          start: peakIdx, trough: troughIdx, end: i,
          depth: (troughV - peak) / peak,
          length: troughIdx - peakIdx,
          recovery: i - troughIdx,
          ongoing: false,
        });
        inDD = false; peak = v; peakIdx = i; troughV = v; troughIdx = i;
      }
    }
  }
  if (inDD) {
    periods.push({
      start: peakIdx, trough: troughIdx, end: equity.length - 1,
      depth: (troughV - peak) / peak,
      length: troughIdx - peakIdx,
      recovery: 0, ongoing: true,
    });
  }
  return periods.sort((a, b) => a.depth - b.depth);
}

/** Pure SVG drawdown (underwater) chart — reliable for all-negative values */
function UnderwaterSVG({ equity, height }: { equity: EquityPoint[]; height: number }) {
  if (equity.length < 2) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
        NO DATA
      </div>
    );
  }

  const W = 1200;
  const H = height;
  const PAD = { top: 6, right: 8, bottom: 22, left: 44 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const vals = equity.map((e) => e.dd * 100);
  const minVal = Math.min(...vals, -1);
  const range = 0 - minVal || 1;

  const toX = (i: number) => PAD.left + (i / (equity.length - 1)) * innerW;
  const toY = (v: number) => PAD.top + ((0 - v) / range) * innerH;

  const y0 = toY(0);
  const linePts = equity.map((e, i) => `${toX(i).toFixed(1)},${toY(e.dd * 100).toFixed(1)}`).join(" ");
  const areaPts = `${PAD.left},${y0} ${linePts} ${toX(equity.length - 1).toFixed(1)},${y0}`;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => minVal * t);

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      {/* Grid lines + y-axis labels */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} y1={toY(t)} x2={PAD.left + innerW} y2={toY(t)}
            stroke="var(--border)" strokeWidth={0.5} strokeDasharray={t === 0 ? "none" : "4 3"} />
          <text x={PAD.left - 4} y={toY(t) + 3} textAnchor="end" fontSize={9} fill="var(--faint)">
            {t.toFixed(1)}%
          </text>
        </g>
      ))}
      {/* Area fill */}
      <polygon points={areaPts} fill="#ff7a55" fillOpacity={0.22} />
      {/* Line */}
      <polyline points={linePts} fill="none" stroke="#ff7a55" strokeWidth={1.5} />
    </svg>
  );
}

export function UnderwaterScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const equityQuery = useRunEquity(activeRunId || null);

  const usingApiEquity = !!(equityQuery.data && equityQuery.data.length > 0);
  const equity: EquityPoint[] = usingApiEquity
    ? equityQuery.data!.map((e: { i: number; v: number; dd: number; ts?: string }) => ({
        i: e.i, v: e.v, dd: e.dd, ts: e.ts, bench: 1, oos: false,
      }))
    : (run?.equity ?? []);

  const ddPeriods: DDPeriod[] = useMemo(
    () => (usingApiEquity ? computeDdPeriods(equity) : (run?.ddPeriods ?? [])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeRunId, usingApiEquity]
  );

  const ddDepths = ddPeriods.map((d) => d.depth * 100);

  // ── Quant metrics ──────────────────────────────────────────────────────────
  const maxDD   = equity.length > 0 ? Math.min(...equity.map((e) => e.dd)) * 100 : 0;
  const medianDD = ddDepths.length ? ddDepths[Math.floor(ddDepths.length / 2)] : 0;
  const avgDD    = ddDepths.length ? ddDepths.reduce((a, b) => a + b, 0) / ddDepths.length : 0;
  const meanRec  = ddPeriods.length
    ? Math.round(ddPeriods.filter((d) => !d.ongoing).reduce((a, d) => a + d.recovery, 0)
        / (ddPeriods.filter((d) => !d.ongoing).length || 1))
    : 0;
  const longestDD = ddPeriods.length
    ? Math.max(...ddPeriods.map((d) => d.length + d.recovery))
    : 0;
  const timeUnderwater = equity.length > 0
    ? (equity.filter((e) => e.dd < -0.001).length / equity.length * 100)
    : 0;

  // Calmar = CAGR / |MaxDD| — approximate CAGR from equity endpoints
  const totalReturn = equity.length > 1 ? (equity[equity.length - 1].v / equity[0].v - 1) * 100 : 0;
  const BARS_PER_YEAR: Record<string, number> = {
    "5m":  365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "1h":  365 * 24,
    "4h":  365 * 6,
    "1d":  365,
  };
  const tf = run?.params?.timeframe ?? "1h";
  const barsPerYear = BARS_PER_YEAR[tf] ?? 365 * 24;
  const years = equity.length / barsPerYear;
  const cagr  = years > 0 ? ((1 + totalReturn / 100) ** (1 / years) - 1) * 100 : 0;
  const calmar = maxDD !== 0 ? cagr / Math.abs(maxDD) : 0;
  const recoveryFactor = maxDD !== 0 ? totalReturn / Math.abs(maxDD) : 0;

  // Top 10 by depth (most negative first)
  const top10 = [...ddPeriods].slice(0, 10);

  return (
    <div className={styles.grid}>
      {/* Underwater chart — full width */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>UNDERWATER · depth from peak %</span>
          <span className={styles.panelSub}>max: {maxDD.toFixed(1)}% · time underwater: {timeUnderwater.toFixed(0)}%</span>
          {!usingApiEquity && <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--amber)", border: "1px solid var(--amber)", padding: "1px 4px" }}>DEMO</span>}
        </div>
        <div className={styles.panelBody} style={{ padding: "8px 0 0 0" }}>
          <UnderwaterSVG equity={equity} height={180} />
        </div>
      </div>

      {/* Summary stats row — full width */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DRAWDOWN METRICS</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.statsRow}>
            <StatCell label="MAX DD"          value={maxDD.toFixed(1) + "%"}    color="var(--coral)" big />
            <StatCell label="CALMAR"           value={calmar.toFixed(2)}         color={calmar >= 0.5 ? "var(--green)" : calmar >= 0.2 ? "var(--amber)" : "var(--coral)"} big />
            <StatCell label="RECOVERY FACTOR"  value={recoveryFactor.toFixed(2)} color={recoveryFactor >= 2 ? "var(--green)" : "var(--amber)"} big />
            <StatCell label="TIME UNDERWATER"  value={timeUnderwater.toFixed(1) + "%"} color="var(--coral)" big />
            <StatCell label="AVG DD DEPTH"    value={avgDD.toFixed(1) + "%"}    color="var(--coral)" />
            <StatCell label="MEDIAN DD"       value={medianDD.toFixed(1) + "%"} color="var(--coral)" />
            <StatCell label="AVG RECOVERY"    value={meanRec + " bars"}          color="var(--amber)" />
            <StatCell label="LONGEST PERIOD"  value={longestDD + " bars"}        color="var(--amber)" />
            <StatCell label="DD COUNT"        value={String(ddPeriods.length)}   color="var(--dim)" />
          </div>
        </div>
      </div>

      {/* Top 10 DD table — cols 1-7 */}
      <div className={styles.panel} style={{ gridColumn: "span 7" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>TOP DRAWDOWNS</span>
          <span className={styles.panelSub}>{top10.length} shown</span>
        </div>
        <div className={styles.panelBody} style={{ padding: 0 }}>
          <div className={styles.table}>
            <div className={styles.thead}
              style={{ gridTemplateColumns: "22px 72px 64px 60px 64px 64px 100px" }}>
              <span>#</span>
              <span>PERIOD</span>
              <span>DEPTH</span>
              <span>LEN</span>
              <span>RECOV</span>
              <span>DURATION</span>
              <span>SHAPE</span>
            </div>
            {top10.map((dd, i) => {
              const slice = equity.slice(dd.start, dd.end + 1).map((e) => -e.dd);
              return (
                <div key={i} className={styles.trow}
                  style={{ gridTemplateColumns: "22px 72px 64px 60px 64px 64px 100px" }}>
                  <span className={styles.dim}>{i + 1}</span>
                  <span className={styles.dim} style={{ fontSize: 9 }}>t{dd.start}–t{dd.end}</span>
                  <span style={{ color: "var(--coral)", fontWeight: 700 }}>
                    {(dd.depth * 100).toFixed(1)}%
                  </span>
                  <span className={styles.dim}>{dd.length}</span>
                  <span className={styles.dim}>{dd.ongoing ? "⚠ ongoing" : dd.recovery}</span>
                  <span className={styles.dim}>{dd.length + dd.recovery}</span>
                  <Sparkline data={slice} width={90} height={14} color="#ff7a55" />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* DD distribution histogram — cols 8-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 5" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DD DEPTH · DISTRIBUTION</span>
          <span className={styles.panelSub}>{ddDepths.length} periods</span>
        </div>
        <div className={styles.panelBody}>
          <Histogram
            data={ddDepths}
            bins={16}
            height={180}
            color="#ff7a55"
            fmt={(v) => v.toFixed(0) + "%"}
          />
        </div>
      </div>
    </div>
  );
}

function StatCell({ label, value, color, big }: { label: string; value: string; color?: string; big?: boolean }) {
  return (
    <div className={styles.metricCell}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricVal} style={{ color: color ?? "var(--text)", fontSize: big ? 18 : 13 }}>{value}</div>
    </div>
  );
}
