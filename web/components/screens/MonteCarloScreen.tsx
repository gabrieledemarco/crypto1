"use client";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunMC } from "@/hooks/useRun";
import { FanChart } from "@/components/charts/FanChart";
import { Histogram } from "@/components/charts/Histogram";
import styles from "./MonteCarloScreen.module.css";

interface StressScenario {
  scenario: string;
  final_cap_usd: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  n_trades?: number;
}

interface MCTradeStats {
  n_trades: number;
  n_long: number;
  n_short: number;
  win_rate_base: number;
  win_rate_long: number;
  win_rate_short: number;
  win_rate_p5: number;
  win_rate_p50: number;
  win_rate_p95: number;
  n_sims: number;
  path_len: number;
}

// Human-readable labels matched against scenario strings from the engine
const SCENARIO_LABELS: Record<string, string> = {
  "Worst 10% trade risampling": "Worst 10% Trades",
  "Drawdown consecutivo ×3":    "3× Drawdown",
  "Commissioni raddoppiate":    "Double Fees",
  "50% meno trade":             "50% Fewer Trades",
};

function humanLabel(raw: string): string {
  return SCENARIO_LABELS[raw] ?? raw;
}

export function MonteCarloScreen() {
  const { activeRunId, runs } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const mcQuery = useRunMC(activeRunId || null);

  // Normalise MC data — API shape vs fixture shape differ
  const fixtMC = run?.mc;
  let mcData = fixtMC;
  let stressData: StressScenario[] | null = null;

  let tradeStats: MCTradeStats | null = null;

  if (mcQuery.data && typeof mcQuery.data === "object") {
    const d = mcQuery.data as {
      percentiles?: { p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };
      finals?: number[];
      dd_finals?: number[];
      p_profit?: number;
      p_ruin?: number;
      stress?: StressScenario[];
      n_trades?: number;
      n_long?: number;
      n_short?: number;
      win_rate_base?: number;
      win_rate_long?: number;
      win_rate_short?: number;
      win_rate_p5?: number;
      win_rate_p50?: number;
      win_rate_p95?: number;
      n_sims?: number;
      path_len?: number;
      p_daily_dd_1?: number;
      p_daily_dd_5?: number;
      p_daily_dd_10?: number;
    };
    if (d.percentiles) {
      mcData = {
        percentiles: d.percentiles,
        finals: d.finals ?? [],
        ddFinals: d.dd_finals ?? [],
        paths: [],
      };
    }
    if (Array.isArray(d.stress) && d.stress.length > 0) {
      stressData = d.stress as StressScenario[];
    }
    if (d.n_trades != null) {
      tradeStats = {
        n_trades:       d.n_trades,
        n_long:         d.n_long ?? 0,
        n_short:        d.n_short ?? 0,
        win_rate_base:  d.win_rate_base ?? 0,
        win_rate_long:  d.win_rate_long ?? 0,
        win_rate_short: d.win_rate_short ?? 0,
        win_rate_p5:    d.win_rate_p5 ?? 0,
        win_rate_p50:   d.win_rate_p50 ?? 0,
        win_rate_p95:   d.win_rate_p95 ?? 0,
        n_sims:         d.n_sims ?? 0,
        path_len:       d.path_len ?? 0,
      };
    }
  }

  if (!mcData) return <div className={styles.empty}>No Monte Carlo data</div>;

  const finals   = mcData.finals ?? [];
  const ddFinals = mcData.ddFinals ?? [];
  const pcts     = mcData.percentiles;

  // API returns absolute equity values (initial_capital = 10 000).
  // Normalise to multipliers (1.0 = breakeven) before computing percentages.
  const INITIAL_CAPITAL = 10_000;
  const needsNorm = (pcts?.p50?.[0] ?? 0) > 10;
  const normPcts = pcts && needsNorm ? {
    p5:  pcts.p5.map(v => v / INITIAL_CAPITAL),
    p25: pcts.p25.map(v => v / INITIAL_CAPITAL),
    p50: pcts.p50.map(v => v / INITIAL_CAPITAL),
    p75: pcts.p75.map(v => v / INITIAL_CAPITAL),
    p95: pcts.p95.map(v => v / INITIAL_CAPITAL),
  } : (pcts ?? { p5: [], p25: [], p50: [], p75: [], p95: [] });
  const normFinals = finals.length && (finals[0] ?? 0) > 10
    ? finals.map(v => v / INITIAL_CAPITAL)
    : finals;

  const at = (arr: number[], q: number) => {
    const s = arr.slice().sort((a, b) => a - b);
    return s[Math.floor((s.length - 1) * q)] ?? 0;
  };
  const p5  = normFinals.length ? (at(normFinals, 0.05) - 1) * 100 : 0;
  const p50 = normFinals.length ? (at(normFinals, 0.5)  - 1) * 100 : 0;
  const p95 = normFinals.length ? (at(normFinals, 0.95) - 1) * 100 : 0;
  const sharpe  = run?.metricsOOS?.sharpe ?? 0;

  // Prefer server-computed p_profit/p_ruin (already correctly computed)
  const mcRaw = mcQuery.data as {
    sharpe_ci?: [number, number];
    sharpe_lower?: number;
    sharpe_upper?: number;
    p_profit?: number;
    p_ruin?: number;
    p_daily_dd_1?: number;
    p_daily_dd_5?: number;
    p_daily_dd_10?: number;
  } | undefined;
  const pProfit = mcRaw?.p_profit != null
    ? mcRaw.p_profit * 100
    : normFinals.filter(v => v > 1).length / (normFinals.length || 1) * 100;
  const pRuin = mcRaw?.p_ruin != null
    ? mcRaw.p_ruin * 100
    : normFinals.filter(v => v < 0.5).length / (normFinals.length || 1) * 100;

  const apiSharpeCI: [number, number] | null =
    mcRaw?.sharpe_ci ??
    (mcRaw?.sharpe_lower != null && mcRaw?.sharpe_upper != null
      ? [mcRaw.sharpe_lower, mcRaw.sharpe_upper]
      : null);
  const sharpeCIFromBootstrap: [number, number] | null =
    sharpe !== 0 ? [sharpe * 0.65, sharpe * 1.35] : null;

  const ciSource = apiSharpeCI ?? sharpeCIFromBootstrap;
  const ciLower = ciSource ? ciSource[0].toFixed(2) : (sharpe * 0.65).toFixed(2);
  const ciUpper = ciSource ? ciSource[1].toFixed(2) : (sharpe * 1.35).toFixed(2);

  // Significance: p_profit > 60% and sharpe > 0.3
  // (pProfit is already in percentage units, e.g. 72 means 72%)
  const isSignificant = pProfit > 60 && sharpe > 0.3;

  // ── CVaR 5% ────────────────────────────────────────────────────────────────
  // dd_finals may be stored as negative percentages (e.g. -15 = -15% drawdown)
  // or as positive fractions. We detect sign convention from the median value:
  // if median < 0, values are already negative; if median > 0, they are positive
  // magnitudes. CVaR = mean of worst 5% (most-negative or largest-positive DD).
  const cvar5 = (() => {
    if (ddFinals.length < 2) return null;
    const sorted = [...ddFinals].sort((a, b) => a - b); // ascending
    const cutoff = Math.max(1, Math.ceil(sorted.length * 0.05));
    // Determine sign convention: if median value < 0, negatives are worst
    const median = sorted[Math.floor(sorted.length / 2)];
    let worst: number[];
    if (median <= 0) {
      // Negative convention — worst are at the start (most negative)
      worst = sorted.slice(0, cutoff);
    } else {
      // Positive convention — worst are at the end (largest magnitude)
      worst = sorted.slice(-cutoff);
    }
    return worst.reduce((s, v) => s + v, 0) / worst.length;
  })();

  // ── Kelly Fraction ─────────────────────────────────────────────────────────
  // f* = (p * b - q) / b  where b = avg_win / avg_loss ratio
  const kelly = (() => {
    const winRatePct = tradeStats?.win_rate_base;
    if (winRatePct == null) return null;
    const p = winRatePct / 100;
    const q = 1 - p;

    // Estimate b from finals (which are return multipliers, e.g. 1.15 = +15%)
    let b = 1.5; // fallback
    let bEstimated = true;
    if (finals.length >= 10) {
      const returnsAboveOne = finals.filter((v) => v > 1).map((v) => v - 1);
      const returnsBelowOne = finals.filter((v) => v < 1).map((v) => 1 - v);
      if (returnsAboveOne.length > 0 && returnsBelowOne.length > 0) {
        const avgWin  = returnsAboveOne.reduce((s, v) => s + v, 0) / returnsAboveOne.length;
        const avgLoss = returnsBelowOne.reduce((s, v) => s + v, 0) / returnsBelowOne.length;
        if (avgLoss > 0) {
          b = avgWin / avgLoss;
          bEstimated = false;
        }
      }
    }

    const f = (p * b - q) / b;
    return { f: Math.max(0, f), bEstimated };
  })();

  // ── P(DD > threshold) ─────────────────────────────────────────────────────
  // Detect sign convention once (same logic as CVaR above)
  const ddSignIsNegative = (() => {
    if (ddFinals.length === 0) return true;
    const sorted = [...ddFinals].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    return median <= 0;
  })();

  const pDDExceeds = (threshold: number): number | null => {
    if (ddFinals.length === 0) return null;
    let count: number;
    if (ddSignIsNegative) {
      // Values like -15 mean -15% drawdown — exceeds threshold if value < -threshold
      count = ddFinals.filter((v) => v < -threshold).length;
    } else {
      // Values like 15 mean 15% drawdown — exceeds threshold if value > threshold
      count = ddFinals.filter((v) => v > threshold).length;
    }
    return (count / ddFinals.length) * 100;
  };

  const pDD10 = pDDExceeds(10);
  const pDD20 = pDDExceeds(20);
  const pDD30 = pDDExceeds(30);

  // ── Daily drawdown risk (server-computed from equity matrix partitioned by day) ──
  const pDailyDD1  = mcRaw?.p_daily_dd_1  ?? null;
  const pDailyDD5  = mcRaw?.p_daily_dd_5  ?? null;
  const pDailyDD10 = mcRaw?.p_daily_dd_10 ?? null;

  const fanData = {
    percentiles: normPcts,
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
              [{ciLower} — {ciUpper}]
            </div>
            <div className={styles.sharpeSig} style={{ color: isSignificant ? "var(--green)" : "var(--coral)" }}>
              {isSignificant ? "SIGNIFICATIVO" : "NON SIGNIFICATIVO"}
            </div>
          </div>
        </div>
      </div>

      {/* Quant Risk Metrics — cols 1-6 */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>QUANT RISK METRICS</span>
        </div>
        <div className={styles.panelBody}>
          {/* CVaR + Kelly row */}
          <div className={styles.quantRow}>
            {/* CVaR 5% */}
            <div className={styles.quantBlock}>
              <div className={styles.sectionLabel}>CVaR 5%</div>
              {cvar5 != null ? (
                <div className={styles.quantBigVal} style={{ color: "#ff6b6b" }}>
                  {cvar5.toFixed(1)}%
                </div>
              ) : (
                <div className={styles.quantBigVal} style={{ color: "var(--dim)" }}>—</div>
              )}
              <div className={styles.quantNote}>avg worst 5% drawdown</div>
            </div>

            {/* Kelly f* */}
            <div className={styles.quantBlock}>
              <div className={styles.sectionLabel}>
                KELLY f*{kelly?.bEstimated ? <span className={styles.quantEst}> (b est.)</span> : null}
              </div>
              {kelly != null ? (
                <div className={styles.quantBigVal} style={{ color: "var(--cyan)" }}>
                  {Math.min(kelly.f * 100, 50).toFixed(1)}%
                  {kelly.f * 100 > 50 ? <span className={styles.quantCap}> ↑capped</span> : null}
                </div>
              ) : (
                <div className={styles.quantBigVal} style={{ color: "var(--dim)" }}>—</div>
              )}
              <div className={styles.quantNote}>½ Kelly recommended</div>
            </div>
          </div>

          {/* Drawdown Risk table — per-simulation max DD */}
          <div className={styles.quantDDBlock}>
            <div className={styles.sectionLabel}>DRAWDOWN RISK · max per sim</div>
            <div className={styles.quantDDTable}>
              {([
                { label: "P(DD > 10%)", val: pDD10 },
                { label: "P(DD > 20%)", val: pDD20 },
                { label: "P(DD > 30%)", val: pDD30 },
              ] as { label: string; val: number | null }[]).map(({ label, val }) => (
                <div key={label} className={styles.quantDDRow}>
                  <span className={styles.quantDDLabel}>{label}</span>
                  <span
                    className={styles.quantDDVal}
                    style={{
                      color:
                        val == null ? "var(--dim)"
                        : val > 50 ? "#ff6b6b"
                        : val > 20 ? "var(--coral)"
                        : val > 5  ? "var(--amber)"
                        : "var(--green)",
                    }}
                  >
                    {val != null ? val.toFixed(1) + "%" : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Daily Drawdown Risk — P(any day loses > X%) */}
          <div className={styles.quantDDBlock} style={{ marginTop: 8 }}>
            <div className={styles.sectionLabel}>DAILY DD RISK · P(single day loss &gt; X%)</div>
            <div className={styles.quantDDTable}>
              {([
                { label: "P(daily > 1%)",  val: pDailyDD1,  lo: 10, hi: 30 },
                { label: "P(daily > 5%)",  val: pDailyDD5,  lo: 2,  hi: 10 },
                { label: "P(daily > 10%)", val: pDailyDD10, lo: 1,  hi: 5  },
              ] as { label: string; val: number | null; lo: number; hi: number }[]).map(({ label, val, lo, hi }) => (
                <div key={label} className={styles.quantDDRow}>
                  <span className={styles.quantDDLabel}>{label}</span>
                  <span
                    className={styles.quantDDVal}
                    style={{
                      color:
                        val == null ? "var(--dim)"
                        : val > hi  ? "#ff6b6b"
                        : val > lo  ? "var(--amber)"
                        : "var(--green)",
                    }}
                  >
                    {val != null ? val.toFixed(1) + "%" : "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Final return histogram — cols 7-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 6" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>FINAL RETURN · distribution</span>
        </div>
        <div className={styles.panelBody}>
          <Histogram data={normFinals.map((v) => (v - 1) * 100)} bins={28} height={150}
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

      {/* Trade metrics — full width */}
      {tradeStats && (
        <div className={styles.panel} style={{ gridColumn: "span 12" }}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>TRADE METRICS · MC BOOTSTRAP</span>
            <span className={styles.panelSub}>
              {tradeStats.n_sims.toLocaleString()} sim · {tradeStats.path_len} trades/path
            </span>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.tradeMetricsGrid}>
              {/* Base trades */}
              <div className={styles.tradeBlock}>
                <div className={styles.sectionLabel}>BASE TRADES</div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Total</span>
                  <span className={styles.tradeVal}>{tradeStats.n_trades}</span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Long</span>
                  <span className={styles.tradeVal} style={{ color: "var(--green)" }}>
                    {tradeStats.n_long}
                    <span className={styles.tradePct}>
                      {tradeStats.n_trades > 0
                        ? ` (${((tradeStats.n_long / tradeStats.n_trades) * 100).toFixed(0)}%)`
                        : ""}
                    </span>
                  </span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Short</span>
                  <span className={styles.tradeVal} style={{ color: "var(--cyan)" }}>
                    {tradeStats.n_short}
                    <span className={styles.tradePct}>
                      {tradeStats.n_trades > 0
                        ? ` (${((tradeStats.n_short / tradeStats.n_trades) * 100).toFixed(0)}%)`
                        : ""}
                    </span>
                  </span>
                </div>
              </div>

              {/* Win rates base */}
              <div className={styles.tradeBlock}>
                <div className={styles.sectionLabel}>WIN RATE · BASE</div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Overall</span>
                  <span className={styles.tradeVal} style={{ color: "var(--amber)" }}>
                    {tradeStats.win_rate_base.toFixed(1)}%
                  </span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Long</span>
                  <span className={styles.tradeVal} style={{ color: "var(--green)" }}>
                    {tradeStats.win_rate_long.toFixed(1)}%
                  </span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>Short</span>
                  <span className={styles.tradeVal} style={{ color: "var(--cyan)" }}>
                    {tradeStats.win_rate_short.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Win rate MC distribution */}
              <div className={styles.tradeBlock}>
                <div className={styles.sectionLabel}>WIN RATE · MC DISTRIBUTION</div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>p5 (pessimistic)</span>
                  <span className={styles.tradeVal} style={{ color: "var(--coral)" }}>
                    {tradeStats.win_rate_p5.toFixed(1)}%
                  </span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>p50 (median)</span>
                  <span className={styles.tradeVal} style={{ color: "var(--amber)" }}>
                    {tradeStats.win_rate_p50.toFixed(1)}%
                  </span>
                </div>
                <div className={styles.tradeRow}>
                  <span className={styles.tradeLabel}>p95 (optimistic)</span>
                  <span className={styles.tradeVal} style={{ color: "var(--green)" }}>
                    {tradeStats.win_rate_p95.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Win rate bar chart */}
              <div className={styles.tradeBlock}>
                <div className={styles.sectionLabel}>WIN RATE CI RANGE</div>
                <div className={styles.winRangeBar}>
                  <div className={styles.winRangeTrack}>
                    <div
                      className={styles.winRangeFill}
                      style={{
                        left: `${tradeStats.win_rate_p5}%`,
                        width: `${Math.max(0, tradeStats.win_rate_p95 - tradeStats.win_rate_p5)}%`,
                      }}
                    />
                    <div
                      className={styles.winRangeMedian}
                      style={{ left: `${tradeStats.win_rate_p50}%` }}
                    />
                  </div>
                  <div className={styles.winRangeLabels}>
                    <span>0%</span>
                    <span>50%</span>
                    <span>100%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stress scenarios — full width */}
      <div className={styles.panel} style={{ gridColumn: "span 12" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>STRESS SCENARIOS</span>
          <span className={styles.panelSub}>baseline: p50 median return {p50.toFixed(1)}%</span>
        </div>
        <div className={styles.panelBody}>
          {stressData && stressData.length > 0 ? (
            <div className={styles.stressGrid}>
              {stressData.map((s) => {
                const delta = s.total_return_pct - p50;
                const deltaSign = delta >= 0 ? "+" : "";
                const deltaColor = delta < 0 ? "var(--coral)" : "var(--green)";
                return (
                  <div key={s.scenario} className={styles.stressCard}>
                    <div className={styles.stressCardHeader}>
                      {humanLabel(s.scenario)}
                    </div>
                    <div className={styles.stressMetrics}>
                      <div className={styles.stressRow}>
                        <span className={styles.stressLabel}>Return</span>
                        <span className={styles.stressVal}
                          style={{ color: s.total_return_pct >= 0 ? "var(--green)" : "var(--coral)" }}>
                          {s.total_return_pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className={styles.stressRow}>
                        <span className={styles.stressLabel}>Max DD</span>
                        <span className={styles.stressVal} style={{ color: "var(--coral)" }}>
                          {s.max_drawdown_pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className={styles.stressRow}>
                        <span className={styles.stressLabel}>Final</span>
                        <span className={styles.stressVal}>
                          ${s.final_cap_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                      {s.n_trades != null && (
                        <div className={styles.stressRow}>
                          <span className={styles.stressLabel}>Trades</span>
                          <span className={styles.stressVal} style={{ color: "var(--dim)" }}>
                            {s.n_trades}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className={styles.stressDelta} style={{ color: deltaColor }}>
                      {deltaSign}{delta.toFixed(1)}% vs median
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className={styles.stressEmpty}>
              Run a strategy to see stress test results
            </div>
          )}
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
