"use client";
import { useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunEquity, useRunTrades, useValidateActiveRun, isRealRunId } from "@/hooks/useRun";
import { EquityChart } from "@/components/charts/EquityChart";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import { MonthlyHeat } from "@/components/charts/MonthlyHeat";
import { Sparkline } from "@/components/charts/Sparkline";
import styles from "./DashboardScreen.module.css";
import type { EquityPoint, Trade, MonthlyBucket } from "@/lib/fixtures";

export function DashboardScreen() {
  const { activeRunId, runs, goto, setRun } = useStore();
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useValidateActiveRun(activeRunId || null, () => setRun(""));

  // Try real API first; fall back to fixture
  const equityQuery = useRunEquity(activeRunId || null);
  const tradesQuery = useRunTrades(activeRunId || null, { limit: 6, offset: 0 });

  // Active run from store (fixture data)
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];

  // Use API equity if available, else fixture
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

  // Use API trades if available, else fixture
  const recentTrades: Trade[] =
    tradesQuery.data?.trades && tradesQuery.data.trades.length > 0
      ? (tradesQuery.data.trades.slice(-6) as Trade[])
      : (run?.trades?.slice(-6) ?? []).reverse();

  const monthly: MonthlyBucket[] = run?.monthly ?? [];
  const metricsIS = run?.metricsIS;
  const metricsOOS = run?.metricsOOS;

  const hasRealEquity = !!(equityQuery.data && equityQuery.data.length > 0);
  const showMonthlyWarning = !hasRealEquity && monthly.length > 0;
  const showDDWarning = !hasRealEquity && run?.ddPeriods && run.ddPeriods.length > 0;
  const equityError = equityQuery.isError ? (equityQuery.error as Error)?.message ?? "Failed to load equity" : null;

  if (!run) return <div className={styles.empty}>No run selected</div>;

  return (
    <div className={styles.grid}>
      {/* Equity + Drawdown — span 8 */}
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>EQUITY · IS / OOS · vs HODL</span>
          <span className={styles.panelSub}>hover for crosshair sync</span>
          <span style={{ flex: 1 }} />
          <span className={styles.dimMono}>
            {metricsOOS?.finalReturn != null
              ? `+${metricsOOS.finalReturn}% OOS`
              : ""}
          </span>
        </div>
        <div className={styles.panelBody}>
          {equityQuery.isLoading && isRealRunId(activeRunId) ? (
            <div className={styles.skeletonChart} />
          ) : equityError && isRealRunId(activeRunId) ? (
            <div className={styles.apiError}>{equityError}</div>
          ) : (
            <EquityChart
              equity={equity}
              oosStart={run.oosStart}
              height={220}
              color="#ffb53b"
              showBench
              onHoverIndex={setHoverIndex}
            />
          )}
          <DrawdownChart
            equity={equity}
            height={64}
            color="#ff7a55"
            sharedHoverIndex={hoverIndex}
          />
        </div>
      </div>

      {/* IS|OOS metrics — span 4 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>HEADLINE · IS | OOS</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.metricGrid}>
            {(
              [
                ["Sharpe", metricsIS?.sharpe, metricsOOS?.sharpe, null],
                ["Sortino", metricsIS?.sortino, metricsOOS?.sortino, null],
                ["Calmar", metricsIS?.calmar, metricsOOS?.calmar, null],
                [
                  "CAGR",
                  `${metricsIS?.cagr}%`,
                  `${metricsOOS?.cagr}%`,
                  "var(--green)",
                ],
                [
                  "MaxDD",
                  `${metricsIS?.maxDD}%`,
                  `${metricsOOS?.maxDD}%`,
                  "var(--coral)",
                ],
                ["Win%", run.winRate, run.winRate, null],
                ["PF", run.profitFactor, run.profitFactor, null],
                ["Trades", run.tradesCount, run.tradesCount, null],
                [
                  "Omega",
                  metricsIS?.omega != null ? metricsIS.omega.toFixed(2) : "—",
                  metricsOOS?.omega != null ? metricsOOS.omega.toFixed(2) : "—",
                  metricsOOS?.omega != null && metricsOOS.omega > 1
                    ? "var(--green)"
                    : null,
                ],
                [
                  "Ulcer",
                  metricsIS?.ulcer != null ? `${metricsIS.ulcer.toFixed(1)}%` : "—",
                  metricsOOS?.ulcer != null ? `${metricsOOS.ulcer.toFixed(1)}%` : "—",
                  "var(--coral)",
                ],
                [
                  "Recov",
                  metricsIS?.recoveryFactor != null
                    ? metricsIS.recoveryFactor.toFixed(1)
                    : "—",
                  metricsOOS?.recoveryFactor != null
                    ? metricsOOS.recoveryFactor.toFixed(1)
                    : "—",
                  metricsOOS?.recoveryFactor != null && metricsOOS.recoveryFactor > 1
                    ? "var(--green)"
                    : null,
                ],
              ] as [string, unknown, unknown, string | null][]
            ).map(([label, isVal, oosVal, color], i) => (
              <div key={i} className={styles.metricPair}>
                <div className={styles.metricLabel}>{label}</div>
                <div className={styles.metricVals}>
                  <span className={styles.metricIS}>{String(isVal ?? "—")}</span>
                  <span
                    className={styles.metricOOS}
                    style={{ color: color ?? "var(--amber)" }}
                  >
                    {String(oosVal ?? "—")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Monthly P&L — span 4 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>MONTHLY P&L</span>
          <span className={styles.panelSub}>24 months</span>
          {showMonthlyWarning && (
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 9,
              color: "var(--amber)", border: "1px solid currentColor",
              padding: "1px 4px",
            }}>
              DEMO
            </span>
          )}
        </div>
        <div className={styles.panelBody}>
          <MonthlyHeat monthly={monthly} cellSize={22} />
          {monthly.length > 0 && (
            <div className={styles.heatLegend}>
              best{" "}
              <b style={{ color: "var(--green)" }}>
                +{Math.max(...monthly.map((m) => m.pnl)).toFixed(1)}%
              </b>
              &nbsp;&nbsp;worst{" "}
              <b style={{ color: "var(--coral)" }}>
                {Math.min(...monthly.map((m) => m.pnl)).toFixed(1)}%
              </b>
            </div>
          )}
        </div>
      </div>

      {/* Recent trades — span 4 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>RECENT TRADES</span>
          <span className={styles.panelSub}>last 6</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.table}>
            <div
              className={styles.thead}
              style={{ gridTemplateColumns: "32px 44px 56px 64px 1fr" }}
            >
              <span>#</span>
              <span>SIDE</span>
              <span>R</span>
              <span>P&amp;L%</span>
              <span>EQ</span>
            </div>
            {recentTrades.map((t: Trade, i: number) => (
              <div
                key={i}
                className={styles.trow}
                style={{ gridTemplateColumns: "32px 44px 56px 64px 1fr" }}
              >
                <span className={styles.dim}>
                  {String(t.n).padStart(3, "0")}
                </span>
                <span
                  style={{
                    color:
                      t.side === "L" ? "var(--amber)" : "var(--cyan)",
                    fontWeight: 700,
                  }}
                >
                  {t.side}
                </span>
                <span>{t.r?.toFixed(1)}</span>
                <span
                  style={{
                    color: t.pnl > 0 ? "var(--green)" : "var(--coral)",
                    fontWeight: 700,
                  }}
                >
                  {t.pnl > 0 ? "+" : ""}
                  {t.pnl}
                </span>
                <Sparkline
                  data={equity
                    .slice(Math.max(0, t.idx - 4), t.idx + 1)
                    .map((e) => e.v)}
                  width={72}
                  height={12}
                  color={t.pnl > 0 ? "#6fd17a" : "#ff7a55"}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* DD Top 3 — span 4 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>DD TOP 3</span>
          {showDDWarning && (
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: 9,
              color: "var(--amber)", border: "1px solid currentColor",
              padding: "1px 4px",
            }}>
              DEMO
            </span>
          )}
        </div>
        <div className={styles.panelBody}>
          <div className={styles.table}>
            <div
              className={styles.thead}
              style={{ gridTemplateColumns: "24px 1fr 64px 48px 48px" }}
            >
              <span>#</span>
              <span>PERIOD</span>
              <span>DEPTH</span>
              <span>LEN</span>
              <span>REC</span>
            </div>
            {run.ddPeriods.slice(0, 3).map((dd, i) => (
              <div
                key={i}
                className={styles.trow}
                style={{ gridTemplateColumns: "24px 1fr 64px 48px 48px" }}
              >
                <span className={styles.dim}>{i + 1}</span>
                <span className={styles.dim}>
                  t{dd.start}→t{dd.end}
                </span>
                <span style={{ color: "var(--coral)", fontWeight: 700 }}>
                  {(dd.depth * 100).toFixed(1)}%
                </span>
                <span>{dd.length}</span>
                <span>{dd.recovery}</span>
              </div>
            ))}
          </div>
          <button
            className={styles.btn}
            onClick={() => goto("underwater")}
            style={{ marginTop: 10 }}
          >
            VIEW ALL · g+u
          </button>
        </div>
      </div>
    </div>
  );
}
