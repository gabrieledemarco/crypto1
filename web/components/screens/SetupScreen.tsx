"use client";
import { useState, useCallback, useEffect } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import type { Run, RunMetrics } from "@/lib/fixtures";
import { useSSE } from "@/hooks/useSSE";
import { usePreview } from "@/hooks/usePreview";
import { EquityChart } from "@/components/charts/EquityChart";
import styles from "./SetupScreen.module.css";

interface Params {
  ticker: string;
  timeframe: string;
  sl_mult: number;
  tp_mult: number;
  active_hours: [number, number];
  risk_per_trade: number;
  commission: number;
  slippage: number;
  direction: string;
  run_wfo: boolean;
  run_sweep: boolean;
  run_mc: boolean;
}

export function SetupScreen() {
  const { activeRunId, runs, activeStrategyId, setToast } = useStore();
  const run = runs.find((r) => r.id === activeRunId) ?? fixtures.runs[0];
  const p = run?.params;

  const [params, setParams] = useState<Params>({
    ticker:       p?.universe?.[0] ? `${p.universe[0]}-USD` : "BTC-USD",
    timeframe:    p?.timeframe ?? "1h",
    sl_mult:      p?.atrStop ?? 2.0,
    tp_mult:      p?.takeProfit ?? 5.0,
    active_hours: [6, 22],
    risk_per_trade: p?.riskPerTrade ?? 1.0,
    commission:   0.0004,
    slippage:     0.0001,
    direction:    "ALL",
    run_wfo:      true,
    run_sweep:    true,
    run_mc:       true,
  });

  const [runId, setRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ phase: string; pct: number } | null>(null);
  const [running, setRunning] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  // Load saved params from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("pareto_saved_params");
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<Params>;
        setParams((prev) => ({
          ...prev,
          ...(parsed.ticker !== undefined && { ticker: parsed.ticker }),
          ...(parsed.timeframe !== undefined && { timeframe: parsed.timeframe }),
          ...(parsed.sl_mult !== undefined && { sl_mult: parsed.sl_mult }),
          ...(parsed.tp_mult !== undefined && { tp_mult: parsed.tp_mult }),
          ...(parsed.active_hours !== undefined && { active_hours: parsed.active_hours }),
          ...(parsed.risk_per_trade !== undefined && { risk_per_trade: parsed.risk_per_trade }),
          ...(parsed.commission !== undefined && { commission: parsed.commission }),
          ...(parsed.slippage !== undefined && { slippage: parsed.slippage }),
          ...(parsed.direction !== undefined && { direction: parsed.direction }),
          ...(parsed.run_wfo !== undefined && { run_wfo: parsed.run_wfo }),
          ...(parsed.run_sweep !== undefined && { run_sweep: parsed.run_sweep }),
          ...(parsed.run_mc !== undefined && { run_mc: parsed.run_mc }),
        }));
      }
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const update = useCallback(<K extends keyof Params>(k: K, v: Params[K]) => {
    setParams((prev) => ({ ...prev, [k]: v }));
  }, []);

  // Live preview (debounced 80ms)
  const { result: preview, loading: previewLoading } = usePreview(params as unknown as Record<string, unknown>);

  // SSE progress
  useSSE(runId ? `/api/runs/${runId}/stream` : null, (data) => {
    const ev = data as { phase: string; pct: number; msg?: string };
    setProgress(ev);
    if (ev.phase === "done") {
      setRunning(false);
      setToast("Run complete");
      if (runId) {
        // Immediately set activeRunId so React Query hooks fire and DEMO badges clear
        useStore.getState().setRun(runId);
        // Async: fetch run metadata and add a real Run to the store
        fetch(`/api/runs/${runId}`)
          .then((r) => r.json())
          .then((apiRun: Record<string, unknown>) => {
            const versionMetrics = apiRun.metrics as Record<string, Record<string, number>> | undefined;
            const best = versionMetrics ? Object.values(versionMetrics)[0] : undefined;
            const emptyM: RunMetrics = { sharpe: 0, sortino: 0, cagr: 0, maxDD: 0, calmar: 0, finalReturn: 0 };
            const realM: RunMetrics = best ? {
              sharpe: best.sharpe_ratio ?? 0,
              sortino: 0,
              cagr: best.cagr_pct ?? 0,
              maxDD: best.max_drawdown_pct ?? 0,
              calmar: best.calmar_ratio ?? 0,
              finalReturn: best.total_return_pct ?? 0,
              omega: best.omega,
              ulcer: best.ulcer,
              recoveryFactor: best.recovery_factor,
            } : emptyM;
            const newRun: Run = {
              id: runId,
              name: (apiRun.name as string) ?? `${params.ticker} · ${params.timeframe}`,
              strategy: params.ticker,
              color: "#ffb53b",
              equity: [],
              oosStart: 0,
              trades: [],
              params: {
                fastMA: 20, slowMA: 80,
                atrStop: params.sl_mult,
                takeProfit: params.tp_mult,
                riskPerTrade: params.risk_per_trade,
                fees: params.commission,
                slippage: params.slippage,
                funding: false,
                universe: [params.ticker.replace(/-USD$/, "")],
                timeframe: params.timeframe,
              },
              dates: { isStart: "", isEnd: "", oosStart: "", oosEnd: "" },
              metricsIS: realM,
              metricsOOS: realM,
              ddPeriods: [],
              sweep: [],
              mc: { paths: [], percentiles: { p5: [], p25: [], p50: [], p75: [], p95: [] }, finals: [], ddFinals: [] },
              winRate: best?.win_rate_pct ?? 0,
              profitFactor: best?.profit_factor ?? 0,
              tradesCount: best?.n_trades ?? 0,
              avgDur: 0,
              exposure: 0,
              monthly: [],
            };
            const { runs: cur } = useStore.getState();
            useStore.getState().setRuns([...cur, newRun]);
          })
          .catch(() => { /* store update is best-effort */ });
      }
    }
    if (ev.phase === "error") { setRunning(false); setToast(`Error: ${ev.msg}`); }
  });

  const handleRun = async () => {
    setRunning(true);
    setProgress({ phase: "start", pct: 0 });
    try {
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params, strategy_id: activeStrategyId ?? undefined }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setRunId(data.id);
    } catch (e: unknown) {
      setRunning(false);
      const msg = e instanceof Error ? e.message : "unknown error";
      setToast(msg.includes("fetch") || msg.includes("Failed")
        ? "API not reachable — check NEXT_PUBLIC_API_URL"
        : `Run failed: ${msg}`);
    }
  };

  const previewEquity = (preview?.equity && preview.equity.length > 0)
    ? preview.equity.map((v, i) => ({ i, v, dd: 0, bench: 1, oos: false }))
    : [];

  const UNIVERSE_TICKERS = ["BTC", "ETH", "SOL", "ARB", "OP", "MATIC", "AVAX"];
  const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];
  const DIRECTIONS = ["ALL", "LONG", "SHORT"];

  return (
    <div className={styles.grid}>
      {/* Form — cols 1-5 */}
      <div className={styles.panel} style={{ gridColumn: "span 5" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>STRATEGY · {params.ticker}</span>
          <span className={styles.panelSub}>⌘↵ run</span>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.form}>
            <SliderRow label="SL MULT ×"       min={0.5} max={5}   step={0.1} value={params.sl_mult}      onChange={(v) => update("sl_mult", v)} />
            <SliderRow label="TP MULT ×"       min={1}   max={10}  step={0.1} value={params.tp_mult}      onChange={(v) => update("tp_mult", v)} />
            <SliderRow label="RISK / TRADE %"  min={0.1} max={3}   step={0.1} value={params.risk_per_trade} onChange={(v) => update("risk_per_trade", v)} />
            <SliderRow label="HOUR START"      min={0}   max={22}  step={1}   value={params.active_hours[0]} onChange={(v) => update("active_hours", [v, params.active_hours[1]])} />
            <SliderRow label="HOUR END"        min={1}   max={23}  step={1}   value={params.active_hours[1]} onChange={(v) => update("active_hours", [params.active_hours[0], v])} />

            <div className={styles.formRow}>
              <span className={styles.rowLabel}>TICKER</span>
              <div className={styles.pills}>
                {UNIVERSE_TICKERS.map((s) => {
                  const t = `${s}-USD`;
                  return (
                    <button key={s} className={`${styles.pill} ${params.ticker === t ? styles.active : ""}`}
                      onClick={() => update("ticker", t)}>{s}</button>
                  );
                })}
              </div>
            </div>

            <div className={styles.formRow}>
              <span className={styles.rowLabel}>TIMEFRAME</span>
              <div className={styles.pills}>
                {TIMEFRAMES.map((tf) => (
                  <button key={tf} className={`${styles.pill} ${params.timeframe === tf ? styles.active : ""}`}
                    onClick={() => update("timeframe", tf)}>{tf}</button>
                ))}
              </div>
            </div>

            <div className={styles.formRow}>
              <span className={styles.rowLabel}>DIRECTION</span>
              <div className={styles.pills}>
                {DIRECTIONS.map((d) => (
                  <button key={d} className={`${styles.pill} ${params.direction === d ? styles.active : ""}`}
                    onClick={() => update("direction", d)}>{d}</button>
                ))}
              </div>
            </div>

            <div className={styles.formRow}>
              <span className={styles.rowLabel}>OPTIONS</span>
              <div className={styles.pills}>
                {(["WFO", "SWEEP", "MC"] as const).map((opt) => {
                  const key = `run_${opt.toLowerCase()}` as "run_wfo" | "run_sweep" | "run_mc";
                  return (
                    <button key={opt} className={`${styles.pill} ${params[key] ? styles.active : ""}`}
                      onClick={() => update(key, !params[key])}>{opt}</button>
                  );
                })}
              </div>
            </div>

            <div className={styles.formRow} style={{ marginTop: 4 }}>
              <span className={styles.rowLabel}>FEES · SLIP</span>
              <span className={styles.mono}>{(params.commission * 10000).toFixed(0)}bps · {(params.slippage * 10000).toFixed(0)}bps</span>
            </div>

            <div className={styles.actionRow}>
              <button className={`${styles.btnPrimary} ${running ? styles.running : ""}`}
                onClick={handleRun} disabled={running}>
                {running ? "▶ RUNNING…" : "▶ RUN"}
              </button>
              <button
                className={styles.btn}
                onClick={() => {
                  localStorage.setItem("pareto_saved_params", JSON.stringify(params));
                  if (typeof setToast === "function") {
                    setToast("Params saved");
                  } else {
                    setSavedFlash(true);
                    setTimeout(() => setSavedFlash(false), 1500);
                  }
                }}
              >
                {savedFlash ? "SAVED ✓" : "SAVE"}
              </button>
              <button className={styles.btn} onClick={() => setParams({ ...params })}>RESET</button>
            </div>

            {/* SSE progress bar */}
            {progress && (
              <div className={styles.progressWrap}>
                <div className={styles.progressBar} style={{ width: `${progress.pct}%` }} />
                <span className={styles.progressLabel}>{progress.phase} · {progress.pct}%</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live Preview — cols 6-12 */}
      <div className={styles.panel} style={{ gridColumn: "span 7" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>LIVE PREVIEW</span>
          <span className={styles.panelSub}>{params.ticker} · {params.timeframe} · 500 bars</span>
          {previewLoading && <span className={styles.loading}>loading…</span>}
        </div>
        <div className={styles.panelBody}>
          {previewEquity.length > 0 ? (
            <EquityChart
              equity={previewEquity}
              oosStart={null}
              height={240}
              color="var(--cyan)"
              showBench={false}
            />
          ) : (
            <div style={{
              height: 240, display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 11,
              flexDirection: "column", gap: 6,
            }}>
              <div>{previewLoading ? "CALCOLO PREVIEW…" : "PREVIEW"}</div>
              <div style={{ fontSize: 9 }}>
                {previewLoading ? "" : "Modifica i parametri per visualizzare"}
              </div>
            </div>
          )}
          <div className={styles.previewMetrics}>
            <PreviewMetric label="EST SHARPE"   value={preview?.sharpe?.toFixed(2)    ?? "—"} />
            <PreviewMetric label="EST CAGR"     value={preview?.cagr != null ? `${preview.cagr.toFixed(1)}%` : "—"} />
            <PreviewMetric label="MAX DD"       value={preview?.max_dd != null ? `${preview.max_dd.toFixed(1)}%` : "—"} color="var(--coral)" />
            <PreviewMetric label="TRADES"       value={String(preview?.trades ?? "—")} />
            <PreviewMetric label="WIN%"         value={preview?.win_rate != null ? `${preview.win_rate.toFixed(1)}%` : "—"} />
          </div>
          <div className={styles.hint}>preview ricampionato ogni 80ms al cambio parametro</div>
        </div>
      </div>
    </div>
  );
}

function SliderRow({ label, min, max, step, value, onChange }: {
  label: string; min: number; max: number; step: number; value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className={styles.sliderRow}>
      <span className={styles.rowLabel}>{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(+e.target.value)} className={styles.range} />
      <span className={styles.sliderVal}>{Number.isInteger(value) ? value : value.toFixed(1)}</span>
    </div>
  );
}

function PreviewMetric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className={styles.previewMetric}>
      <div className={styles.previewMetricLabel}>{label}</div>
      <div className={styles.previewMetricVal} style={{ color: color ?? "var(--amber)" }}>{value}</div>
    </div>
  );
}
