"use client";
import { useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunEquity, isRealRunId } from "@/hooks/useRun";
import { EquityChart } from "@/components/charts/EquityChart";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import styles from "./EquityScreen.module.css";
import type { EquityPoint } from "@/lib/fixtures";

export function EquityScreen() {
  const { activeRunId, runs } = useStore();
  const [logScale, setLogScale] = useState(false);
  const [showBench, setShowBench] = useState(true);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const equityQuery = useRunEquity(activeRunId || null);
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const isFixtureRun = !isRealRunId(activeRunId);

  const equity: EquityPoint[] =
    equityQuery.data && equityQuery.data.length > 0
      ? equityQuery.data.map(
          (e: { i: number; v: number; dd: number; ts?: string }, idx: number) => ({
            i: e.i,
            v: e.v,
            dd: e.dd,
            ts: e.ts,
            bench: 1,
            oos: idx >= (run?.oosStart ?? 0),
          })
        )
      : run?.equity ?? [];

  const IS = run?.metricsIS;
  const OOS = run?.metricsOOS;

  const metricStrip: [string, unknown, unknown, string | null][] = [
    ["CAGR", `${IS?.cagr}%`, `${OOS?.cagr}%`, "var(--green)"],
    ["SHARPE", IS?.sharpe, OOS?.sharpe, null],
    ["SORTINO", IS?.sortino, OOS?.sortino, null],
    ["CALMAR", IS?.calmar, OOS?.calmar, null],
    ["MAXDD", `${IS?.maxDD}%`, `${OOS?.maxDD}%`, "var(--coral)"],
    ["PF", run?.profitFactor, run?.profitFactor, null],
    ["WIN%", run?.winRate, run?.winRate, null],
    ["TRADES", run?.tradesCount, run?.tradesCount, null],
    [
      "OMEGA",
      IS?.omega != null ? IS.omega.toFixed(2) : "—",
      OOS?.omega != null ? OOS.omega.toFixed(2) : "—",
      OOS?.omega != null && OOS.omega > 1 ? "var(--green)" : null,
    ],
    [
      "ULCER",
      IS?.ulcer != null ? `${IS.ulcer.toFixed(1)}%` : "—",
      OOS?.ulcer != null ? `${OOS.ulcer.toFixed(1)}%` : "—",
      "var(--coral)",
    ],
    [
      "RECOV",
      IS?.recoveryFactor != null ? IS.recoveryFactor.toFixed(1) : "—",
      OOS?.recoveryFactor != null ? OOS.recoveryFactor.toFixed(1) : "—",
      OOS?.recoveryFactor != null && OOS.recoveryFactor > 1
        ? "var(--green)"
        : null,
    ],
  ];

  return (
    <div className={styles.wrapper}>
      <div className={styles.panel}>
        {/* IS|OOS metrics strip */}
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>EQUITY · IS / OOS</span>
          <span style={{ flex: 1 }} />
          {isFixtureRun && (
            <span style={{
              fontFamily:"var(--font-mono)", fontSize:9,
              color:"var(--amber)", border:"1px solid var(--amber)",
              padding:"1px 5px", marginLeft:"auto",
            }}>
              DEMO DATA
            </span>
          )}
          <button
            className={`${styles.pill} ${logScale ? styles.active : ""}`}
            onClick={() => setLogScale(!logScale)}
          >
            LOG
          </button>
          <button
            className={`${styles.pill} ${showBench ? styles.active : ""}`}
            onClick={() => setShowBench(!showBench)}
          >
            BENCH
          </button>
        </div>

        <div className={styles.strip}>
          {metricStrip.map(([label, isVal, oosVal, color], i) => (
            <div key={i} className={styles.stripItem}>
              <div className={styles.stripLabel}>{label as string} · IS|OOS</div>
              <div className={styles.stripVals}>
                <span className={styles.stripIS}>{String(isVal ?? "—")}</span>
                <span
                  className={styles.stripOOS}
                  style={{ color: (color as string) || "var(--amber)" }}
                >
                  {String(oosVal ?? "—")}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className={styles.panelBody}>
          <EquityChart
            equity={equity}
            oosStart={run?.oosStart}
            height={300}
            color="#ffb53b"
            showBench={showBench}
            logScale={logScale}
            onHoverIndex={setHoverIndex}
          />
          <DrawdownChart
            equity={equity}
            height={100}
            color="#ff7a55"
            sharedHoverIndex={hoverIndex}
          />
        </div>
      </div>
    </div>
  );
}
