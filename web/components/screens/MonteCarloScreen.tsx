"use client";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunMC } from "@/hooks/useRun";
import { FanChart } from "@/components/charts/FanChart";
import { Histogram } from "@/components/charts/Histogram";
import styles from "./MonteCarloScreen.module.css";

export function MonteCarloScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const mcQuery = useRunMC(activeRunId || null);

  // Normalise MC data — API shape vs fixture shape differ
  const fixtMC = run?.mc;
  let mcData = fixtMC;

  if (mcQuery.data && typeof mcQuery.data === "object") {
    const d = mcQuery.data as {
      percentiles?: { p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };
      finals?: number[];
      dd_finals?: number[];
      p_profit?: number;
      p_ruin?: number;
    };
    if (d.percentiles) {
      mcData = {
        percentiles: d.percentiles,
        finals: d.finals ?? [],
        ddFinals: d.dd_finals ?? [],
        paths: [],
      };
    }
  }

  if (!mcData) return <div className={styles.empty}>No Monte Carlo data</div>;

  const finals   = mcData.finals ?? [];
  const ddFinals = mcData.ddFinals ?? [];
  const pcts     = mcData.percentiles;

  const at = (arr: number[], q: number) => {
    const s = arr.slice().sort((a, b) => a - b);
    return s[Math.floor((s.length - 1) * q)] ?? 0;
  };
  const p5  = finals.length ? (at(finals, 0.05) - 1) * 100 : 0;
  const p50 = finals.length ? (at(finals, 0.5)  - 1) * 100 : 0;
  const p95 = finals.length ? (at(finals, 0.95) - 1) * 100 : 0;
  const pProfit = finals.length ? finals.filter((v) => v > 1).length / finals.length * 100 : 0;
  const pRuin   = finals.length ? finals.filter((v) => v < 0.5).length / finals.length * 100 : 0;
  const sharpe  = run?.metricsOOS?.sharpe ?? 0;

  const fanData = {
    percentiles: pcts ?? { p5: [], p25: [], p50: [], p75: [], p95: [] },
  };

  return (
    <div className={styles.grid}>
      {/* Fan chart — cols 1-8 */}
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>EQUITY FAN · p5/p25/p50/p75/p95</span>
          <span className={styles.panelSub}>bootstrap · {finals.length.toLocaleString()} sim</span>
        </div>
        <div className={styles.panelBody}>
          <FanChart mc={fanData} height={280} color="#ffb53b" />
        </div>
      </div>

      {/* Outcomes — cols 9-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>OUTCOMES</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.bigMetrics}>
            <div className={styles.bigMetric}>
              <div className={styles.bigLabel}>P(profit)</div>
              <div className={styles.bigVal} style={{ color: "var(--green)" }}>{pProfit.toFixed(0)}%</div>
            </div>
            <div className={styles.bigMetric}>
              <div className={styles.bigLabel}>P(ruin)</div>
              <div className={styles.bigVal} style={{ color: pRuin > 1 ? "var(--coral)" : "var(--dim)" }}>
                {pRuin.toFixed(1)}%
              </div>
            </div>
          </div>

          <div className={styles.metricGrid}>
            <MetricCell label="p5 final"  value={p5.toFixed(1) + "%"}  />
            <MetricCell label="p50 final" value={p50.toFixed(1) + "%"} />
            <MetricCell label="p95 final" value={p95.toFixed(1) + "%"} />
          </div>

          <div className={styles.sharpeBlock}>
            <div className={styles.sectionLabel}>SHARPE · 95% CI</div>
            <div className={styles.sharpeBig}>{sharpe}</div>
            <div className={styles.sharpeCi}>
              [{(sharpe * 0.65).toFixed(2)} — {(sharpe * 1.35).toFixed(2)}]
            </div>
            <div className={styles.sharpeSig} style={{ color: sharpe > 0.5 ? "var(--green)" : "var(--coral)" }}>
              {sharpe > 0.5 ? "SIGNIFICATIVO" : "NON SIGNIFICATIVO"}
            </div>
          </div>
        </div>
      </div>

      {/* Final return histogram — cols 1-6 */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>FINAL RETURN · distribution</span>
        </div>
        <div className={styles.panelBody}>
          <Histogram data={finals.map((v) => (v - 1) * 100)} bins={28} height={150}
            color="#ffb53b" fmt={(v) => v.toFixed(0) + "%"} />
        </div>
      </div>

      {/* Max DD histogram — cols 7-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>MAX DD · distribution</span>
        </div>
        <div className={styles.panelBody}>
          <Histogram data={ddFinals.map((v) => v)} bins={24} height={150}
            color="#ff7a55" fmt={(v) => v.toFixed(0) + "%"} />
        </div>
      </div>
    </div>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metricCell}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricVal}>{value}</div>
    </div>
  );
}
