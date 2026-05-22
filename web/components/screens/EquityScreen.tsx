"use client";
import { useState, useMemo } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { useRunEquity, useRunBootstrapCI, isRealRunId } from "@/hooks/useRun";
import { ACFPlot } from "@/components/charts/ACFPlot";
import { EquityChart } from "@/components/charts/EquityChart";
import { DrawdownChart } from "@/components/charts/DrawdownChart";
import styles from "./EquityScreen.module.css";
import type { EquityPoint } from "@/lib/fixtures";

// ---------------------------------------------------------------------------
// Rolling Sharpe inline component
// ---------------------------------------------------------------------------
const WINDOW = 60;

function annFactorForTimeframe(tf?: string): number {
  if (!tf) return Math.sqrt(365 * 24); // default: hourly
  const t = tf.toLowerCase();
  if (t.includes("1d") || t === "daily") return Math.sqrt(252);
  if (t.includes("4h")) return Math.sqrt(252 * 6);
  if (t.includes("1h")) return Math.sqrt(365 * 24);
  if (t.includes("15m")) return Math.sqrt(365 * 24 * 4);
  if (t.includes("5m")) return Math.sqrt(365 * 24 * 12);
  if (t.includes("1m")) return Math.sqrt(365 * 24 * 60);
  return Math.sqrt(365 * 24);
}

function computeRollingSharpe(equity: EquityPoint[], annFactor: number): number[] {
  if (equity.length < WINDOW + 1) return [];
  const returns: number[] = [];
  for (let i = 1; i < equity.length; i++) {
    const prev = equity[i - 1].v;
    returns.push(prev === 0 ? 0 : (equity[i].v - prev) / prev);
  }
  const result: number[] = new Array(returns.length).fill(NaN);
  for (let i = WINDOW - 1; i < returns.length; i++) {
    const slice = returns.slice(i - WINDOW + 1, i + 1);
    const mean = slice.reduce((s, x) => s + x, 0) / WINDOW;
    const variance = slice.reduce((s, x) => s + (x - mean) ** 2, 0) / WINDOW;
    const std = Math.sqrt(variance);
    result[i] = std === 0 ? 0 : (mean / std) * annFactor;
  }
  return result;
}

interface RollingSharpeProps {
  equity: EquityPoint[];
  timeframe?: string;
}

function RollingSharpePanel({ equity, timeframe }: RollingSharpeProps) {
  const annFactor = annFactorForTimeframe(timeframe);
  const sharpeValues = useMemo(
    () => computeRollingSharpe(equity, annFactor),
    [equity, annFactor]
  );

  const validValues = sharpeValues.filter((v) => !isNaN(v));
  if (validValues.length === 0) return null;

  const H = 80;
  const W = 600; // SVG viewBox width; scales with container
  const PAD_LEFT = 32;
  const PAD_RIGHT = 4;
  const PAD_TOP = 8;
  const PAD_BOTTOM = 16;

  const mean = validValues.reduce((s, v) => s + v, 0) / validValues.length;
  const stdv = Math.sqrt(
    validValues.reduce((s, v) => s + (v - mean) ** 2, 0) / validValues.length
  );
  const yMin = Math.max(-3, mean - 3 * stdv);
  const yMax = Math.min(3, mean + 3 * stdv);
  const yRange = yMax - yMin || 1;

  const chartH = H - PAD_TOP - PAD_BOTTOM;
  const chartW = W - PAD_LEFT - PAD_RIGHT;

  const toY = (v: number) =>
    PAD_TOP + ((yMax - Math.max(yMin, Math.min(yMax, v))) / yRange) * chartH;
  const zeroY = toY(0);

  // Build path segments: cyan above zero, coral below
  const posPoints: string[] = [];
  const negPoints: string[] = [];

  sharpeValues.forEach((v, idx) => {
    if (isNaN(v)) return;
    const x = PAD_LEFT + (idx / (sharpeValues.length - 1)) * chartW;
    const y = toY(v);
    posPoints.push(`${x},${y}`);
    negPoints.push(`${x},${y}`);
  });

  // Y-axis label values
  const yLabels = [yMax, 0, yMin].map((val) => ({
    val,
    y: toY(val),
    text: val.toFixed(1),
  }));

  return (
    <div className={styles.sharpePanelWrapper}>
      <div className={styles.sharpePanelHeader}>
        <span className={styles.sharpePanelTitle}>ROLLING SHARPE (60)</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className={styles.sharpeSvg}
        style={{ height: H }}
      >
        {/* Y-axis labels */}
        {yLabels.map(({ val, y, text }) => (
          <text
            key={val}
            x={PAD_LEFT - 4}
            y={y + 3}
            textAnchor="end"
            fontSize={7}
            fontFamily="var(--font-mono)"
            fill="var(--faint)"
          >
            {text}
          </text>
        ))}

        {/* Zero dashed line */}
        <line
          x1={PAD_LEFT}
          y1={zeroY}
          x2={W - PAD_RIGHT}
          y2={zeroY}
          stroke="var(--amber)"
          strokeWidth={0.8}
          strokeDasharray="3,3"
          opacity={0.6}
        />

        {/* Positive Sharpe line (cyan) — only segments above zero */}
        <polyline
          points={posPoints.join(" ")}
          fill="none"
          stroke="var(--cyan)"
          strokeWidth={1.2}
          opacity={0.85}
          clipPath="url(#clipAbove)"
        />

        {/* Negative Sharpe line (coral) — only segments below zero */}
        <polyline
          points={negPoints.join(" ")}
          fill="none"
          stroke="#ff7a55"
          strokeWidth={1.2}
          opacity={0.85}
          clipPath="url(#clipBelow)"
        />

        {/* Clip paths for colour split */}
        <defs>
          <clipPath id="clipAbove">
            <rect x={PAD_LEFT} y={PAD_TOP} width={chartW} height={zeroY - PAD_TOP} />
          </clipPath>
          <clipPath id="clipBelow">
            <rect x={PAD_LEFT} y={zeroY} width={chartW} height={H - zeroY - PAD_BOTTOM} />
          </clipPath>
        </defs>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ACF of Equity Returns
// ---------------------------------------------------------------------------
interface ACFEquityProps {
  equity: EquityPoint[];
}

function ACFEquityPanel({ equity }: ACFEquityProps) {
  const returns = useMemo(() => {
    const r: number[] = [];
    for (let i = 1; i < equity.length; i++) {
      const prev = equity[i - 1].v;
      if (prev > 0) r.push((equity[i].v - prev) / prev);
    }
    return r;
  }, [equity]);

  if (returns.length < 30) return null;

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 9,
        color: "var(--faint)", marginBottom: 3, paddingLeft: 2,
        letterSpacing: "0.05em",
      }}>
        EQUITY RETURNS — ACF (lags 1–30)
      </div>
      <ACFPlot data={returns} maxLag={30} height={100} color="#5cc1ff" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bootstrap CI Panel
// ---------------------------------------------------------------------------
interface BootstrapCIData {
  sharpe: { point: number; ci_low: number; ci_high: number };
  cagr_pct: { point: number; ci_low: number; ci_high: number };
  n_returns: number;
}

function BootstrapCIPanel({ data }: { data: BootstrapCIData }) {
  const W = 600, H = 48;
  const PAD = { l: 90, r: 20, t: 8, b: 8 };
  const iW = W - PAD.l - PAD.r;
  const iH = H - PAD.t - PAD.b;

  const rows: Array<{ label: string; point: number; low: number; high: number; color: string; fmt: (v: number) => string }> = [
    { label: "SHARPE 95% CI", point: data.sharpe.point, low: data.sharpe.ci_low, high: data.sharpe.ci_high, color: "var(--amber)", fmt: (v) => v.toFixed(2) },
    { label: "CAGR 95% CI",   point: data.cagr_pct.point, low: data.cagr_pct.ci_low, high: data.cagr_pct.ci_high, color: "var(--green)", fmt: (v) => `${v.toFixed(1)}%` },
  ];

  const rowH = iH / rows.length;

  // Determine x-scale: cover all CI values
  const allVals = rows.flatMap(r => [r.low, r.point, r.high]);
  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const range = maxV - minV || 1;
  const toX = (v: number) => PAD.l + ((v - minV) / range) * iW;

  return (
    <div style={{ marginTop: 4 }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 9,
        color: "var(--faint)", marginBottom: 3, paddingLeft: 2,
        letterSpacing: "0.05em",
      }}>
        BOOTSTRAP CONFIDENCE INTERVALS · n={data.n_returns.toLocaleString()} · 95%
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
        {rows.map((row, ri) => {
          const cy = PAD.t + ri * rowH + rowH / 2;
          const xLow   = toX(row.low);
          const xHigh  = toX(row.high);
          const xPoint = toX(row.point);
          const zero   = toX(0);
          return (
            <g key={row.label}>
              {/* Zero line */}
              {zero >= PAD.l && zero <= PAD.l + iW && (
                <line x1={zero} y1={PAD.t} x2={zero} y2={PAD.t + iH}
                  stroke="var(--border)" strokeWidth={0.8} strokeDasharray="3 3" opacity={0.6} />
              )}
              {/* Label */}
              <text x={PAD.l - 4} y={cy + 3} textAnchor="end" fontSize={8}
                fill="var(--faint)" fontFamily="var(--font-mono)">{row.label}</text>
              {/* CI bar */}
              <rect x={xLow} y={cy - 3} width={Math.max(1, xHigh - xLow)} height={6}
                fill={row.color} opacity={0.2} rx={1} />
              {/* CI whiskers */}
              <line x1={xLow}  y1={cy - 5} x2={xLow}  y2={cy + 5} stroke={row.color} strokeWidth={1.5} />
              <line x1={xHigh} y1={cy - 5} x2={xHigh} y2={cy + 5} stroke={row.color} strokeWidth={1.5} />
              {/* Point estimate */}
              <circle cx={xPoint} cy={cy} r={3} fill={row.color} />
              {/* Labels */}
              <text x={xLow - 2}   y={cy + 10} textAnchor="middle" fontSize={7} fill={row.color} fontFamily="var(--font-mono)">{row.fmt(row.low)}</text>
              <text x={xPoint}     y={cy - 7}  textAnchor="middle" fontSize={7} fill={row.color} fontFamily="var(--font-mono)" fontWeight="bold">{row.fmt(row.point)}</text>
              <text x={xHigh + 2}  y={cy + 10} textAnchor="middle" fontSize={7} fill={row.color} fontFamily="var(--font-mono)">{row.fmt(row.high)}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exit Reason chips
// ---------------------------------------------------------------------------
interface ExitReasonsProps {
  slHits?: number;
  tpHits?: number;
  nTrades?: number;
  label: string;
}

function ExitReasonChips({ slHits, tpHits, nTrades, label }: ExitReasonsProps) {
  if (slHits == null || tpHits == null || !nTrades || nTrades === 0) return null;
  const slPct = ((slHits / nTrades) * 100).toFixed(0);
  const tpPct = ((tpHits / nTrades) * 100).toFixed(0);
  const otherPct = Math.max(
    0,
    (((nTrades - slHits - tpHits) / nTrades) * 100)
  ).toFixed(0);

  return (
    <div className={styles.exitRow}>
      <span className={styles.exitLabel}>{label}</span>
      <span className={styles.exitChipAmber}>SL {slPct}%</span>
      <span className={styles.exitChipCyan}>TP {tpPct}%</span>
      <span className={styles.exitChipDim}>Other {otherPct}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------
export function EquityScreen() {
  const { activeRunId, runs } = useStore();
  const [logScale, setLogScale] = useState(false);
  const [showBench, setShowBench] = useState(true);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const equityQuery = useRunEquity(activeRunId || null);
  const bootstrapCI = useRunBootstrapCI(activeRunId || null);
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

  // Resolve exit reason counts — metrics may carry extra keys not in the base type
  type AnyMetrics = Record<string, unknown>;
  const isAny = IS as unknown as AnyMetrics | undefined;
  const oosAny = OOS as unknown as AnyMetrics | undefined;
  const metricsAny = (run as unknown as { metrics?: AnyMetrics })?.metrics;

  const slHitsIS = isAny?.sl_hits as number | undefined;
  const tpHitsIS = isAny?.tp_hits as number | undefined;
  const slHitsOOS = oosAny?.sl_hits as number | undefined;
  const tpHitsOOS = oosAny?.tp_hits as number | undefined;
  const nTradesIS =
    (isAny?.n_trades as number | undefined) ??
    (metricsAny?.n_trades as number | undefined) ??
    run?.tradesCount;
  const nTradesOOS =
    (oosAny?.n_trades as number | undefined) ??
    (nTradesIS as number | undefined);

  const showExitIS =
    slHitsIS != null && tpHitsIS != null && !!nTradesIS && nTradesIS > 0;
  const showExitOOS =
    slHitsOOS != null && tpHitsOOS != null && !!nTradesOOS && nTradesOOS > 0;

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

        {/* Exit Reason row */}
        {(showExitIS || showExitOOS) && (
          <div className={styles.exitReasonRow}>
            <span className={styles.exitReasonTitle}>EXIT REASONS</span>
            {showExitIS && (
              <ExitReasonChips
                slHits={slHitsIS}
                tpHits={tpHitsIS}
                nTrades={nTradesIS}
                label="IS"
              />
            )}
            {showExitOOS && (
              <ExitReasonChips
                slHits={slHitsOOS}
                tpHits={tpHitsOOS}
                nTrades={nTradesOOS}
                label="OOS"
              />
            )}
          </div>
        )}

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
          <RollingSharpePanel
            equity={equity}
            timeframe={(run as { params?: { timeframe?: string } })?.params?.timeframe}
          />
          <ACFEquityPanel equity={equity} />
          {bootstrapCI.data && !bootstrapCI.isError && (
            <BootstrapCIPanel data={bootstrapCI.data} />
          )}
        </div>
      </div>
    </div>
  );
}
