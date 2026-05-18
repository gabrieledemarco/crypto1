"use client";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunEquity } from "@/hooks/useRun";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { Histogram } from "@/components/charts/Histogram";
import { Sparkline } from "@/components/charts/Sparkline";
import styles from "./UnderwaterScreen.module.css";
import type { EquityPoint, DDPeriod } from "@/lib/fixtures";

export function UnderwaterScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const equityQuery = useRunEquity(activeRunId || null);

  const equity: EquityPoint[] = (equityQuery.data && equityQuery.data.length > 0)
    ? equityQuery.data.map((e: {i:number;v:number;dd:number;ts?:string}, idx: number) => ({
        i: e.i, v: e.v, dd: e.dd, ts: e.ts, bench: 1, oos: false,
      }))
    : (run?.equity ?? []);

  const ddPeriods: DDPeriod[] = run?.ddPeriods ?? [];
  const ddDepths = ddPeriods.map((d) => d.depth * 100);
  const medianDD = ddDepths.length ? ddDepths[Math.floor(ddDepths.length / 2)] : 0;
  const meanRec  = ddPeriods.length
    ? Math.round(ddPeriods.reduce((a, d) => a + d.recovery, 0) / ddPeriods.length)
    : 0;

  return (
    <div className={styles.grid}>
      {/* Underwater chart — full width */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>UNDERWATER · all-time depth %</span>
        </div>
        <div className={styles.panelBody}>
          <DrawdownChart equity={equity} height={200} color="var(--coral)" />
        </div>
      </div>

      {/* Top 5 DD table — cols 1-7 */}
      <div className={styles.panel} style={{ gridColumn: "span 7" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>TOP 5 DRAWDOWNS</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.table}>
            <div className={styles.thead}
              style={{ gridTemplateColumns: "24px 1fr 72px 64px 64px 100px" }}>
              <span>#</span><span>PERIOD</span><span>DEPTH</span>
              <span>LEN</span><span>RECOV</span><span>SHAPE</span>
            </div>
            {ddPeriods.slice(0, 5).map((dd, i) => {
              const slice = equity.slice(dd.start, dd.end + 1).map((e) => -e.dd);
              return (
                <div key={i} className={styles.trow}
                  style={{ gridTemplateColumns: "24px 1fr 72px 64px 64px 100px" }}>
                  <span className={styles.dim}>{i + 1}</span>
                  <span className={styles.dim}>t{dd.start}→t{dd.end}</span>
                  <span style={{ color: "var(--coral)", fontWeight: 700 }}>
                    {(dd.depth * 100).toFixed(1)}%
                  </span>
                  <span>{dd.length}</span>
                  <span>{dd.ongoing ? "ongoing" : dd.recovery}</span>
                  <Sparkline data={slice} width={90} height={14} color="#ff7a55" />
                </div>
              );
            })}
          </div>

          <div className={styles.metricRow}>
            <MetricCell label="MEDIAN DD"  value={(medianDD).toFixed(1) + "%"}  color="var(--coral)" />
            <MetricCell label="WORST DD"   value={(run?.metricsOOS?.maxDD ?? 0) + "%"} color="var(--coral)" big />
            <MetricCell label="MEAN RECOV" value={meanRec + " bars"}            color="var(--amber)" />
          </div>
        </div>
      </div>

      {/* DD distribution histogram — cols 8-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 5" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DD DISTRIBUTION</span>
          <span className={styles.panelSub}>depths histogram</span>
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

function MetricCell({ label, value, color, big }: { label: string; value: string; color?: string; big?: boolean }) {
  return (
    <div className={styles.metricCell}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricVal} style={{ color: color ?? "var(--text)", fontSize: big ? 20 : 13 }}>{value}</div>
    </div>
  );
}
