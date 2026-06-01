"use client";
import { useState, useRef, useEffect, useMemo } from "react";
import { useStore } from "@/store";
import { useAssets } from "@/hooks/useAssets";
import { StrategyBrief, StrategyEvaluation, VibeV2Progress } from "@/lib/api-types";
import { EvaluationCard } from "./EvaluationCard";
import { AgentWorkflow } from "./AgentWorkflow";
import { AgentDetailLog, DetailEntry } from "./AgentDetailLog";
import styles from "./VibeScreen.module.css";

const FALLBACK_ASSETS = ["BTC-USD", "ETH-USD", "SOL-USD", "ARB-USD", "OP-USD", "AVAX-USD"];

interface StrategyConfig {
  ticker?: string;
  timeframe?: string;
  sl_mult?: number;
  tp_mult?: number;
  active_hours?: number[];
  risk_per_trade?: number;
  direction?: string;
}

interface SavedStrategy {
  id: string;
  name: string;
  config: StrategyConfig;
  has_code?: boolean;
}

const CONFIG_LABELS: Record<string, string> = {
  ticker: "TICKER",
  timeframe: "TIMEFRAME",
  sl_mult: "SL MULT ×",
  tp_mult: "TP MULT ×",
  active_hours: "ACTIVE HOURS",
  risk_per_trade: "RISK / TRADE %",
  direction: "DIRECTION",
};

export function VibeScreen() {
  const { goto, setToast, pendingVibeParams, setPendingVibeParams } = useStore();
  const { data: assetsData } = useAssets();

  const assetOptions = useMemo(() => {
    if (!assetsData || assetsData.length === 0) return FALLBACK_ASSETS;
    const tickers = [...new Set(assetsData.map((a) => a.ticker))].sort();
    return tickers.map((t) => (t.includes("-") ? t : `${t}-USD`));
  }, [assetsData]);

  const [asset, setAsset] = useState("BTC-USD");
  const [timeframe, setTimeframe] = useState("1h");
  const [prompt, setPrompt] = useState("");

  const availableTimeframes = useMemo(() => {
    if (!assetsData || assetsData.length === 0) return [];
    const base = asset.replace(/-USD$/, "");
    return assetsData.filter((a) => a.ticker === base).map((a) => a.interval);
  }, [assetsData, asset]);

  useEffect(() => {
    if (availableTimeframes.length > 0 && !availableTimeframes.includes(timeframe)) {
      setTimeframe(availableTimeframes[0]);
    }
  }, [availableTimeframes, timeframe]);

  useEffect(() => {
    if (pendingVibeParams) {
      setAsset(pendingVibeParams.asset);
      setTimeframe(pendingVibeParams.timeframe);
      if (pendingVibeParams.config !== undefined) {
        setConfig(pendingVibeParams.config as StrategyConfig | null);
      }
      if (pendingVibeParams.code !== undefined) {
        setCode(pendingVibeParams.code ?? null);
        if (pendingVibeParams.code) setOutputTab("code");
      }
      setPendingVibeParams(null);
    }
  }, [pendingVibeParams, setPendingVibeParams]);

  const [generating, setGenerating] = useState(false);
  const [status, setStatus] = useState("");
  const [text, setText] = useState("");
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [outputTab, setOutputTab] = useState<"explanation" | "code">("explanation");
  const streamRef = useRef<HTMLDivElement>(null);

  // v2 Enhanced Mode state
  const [useV2, setUseV2] = useState(false);
  const [v2Phase, setV2Phase] = useState<string>('');
  const [v2RawPhase, setV2RawPhase] = useState<string>('');
  const [v2Pct, setV2Pct] = useState(0);
  const [v2Attempt, setV2Attempt] = useState(1);
  const [v2Brief, setV2Brief] = useState<StrategyBrief | null>(null);
  const [v2Evaluation, setV2Evaluation] = useState<StrategyEvaluation | null>(null);
  const [v2Verdict, setV2Verdict] = useState<string>('');

  // Agent detail log state
  const [detailLog, setDetailLog] = useState<DetailEntry[]>([]);
  const detailIdRef = useRef(0);
  const orchestratorCardId = useRef(-1);
  const generatorCardId = useRef(-1);
  const briefAccum = useRef("");
  const codeAccum = useRef("");

  const patchDetail = (id: number, updates: Partial<DetailEntry>) =>
    setDetailLog(prev => prev.map(e => e.id === id ? { ...e, ...updates } : e));

  // Saved strategies for "load previous"
  const [strategies, setStrategies] = useState<SavedStrategy[]>([]);
  const [selectedStratId, setSelectedStratId] = useState("");

  // Second brain sync
  const [brainSyncing, setBrainSyncing] = useState(false);
  const [brainStatus, setBrainStatus] = useState<{ synced: number; errors: number } | null>(null);

  const handleBrainSync = async () => {
    setBrainSyncing(true);
    try {
      const res = await fetch("/api/brain/sync", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setBrainStatus({ synced: data.synced, errors: data.errors });
      setToast(`Brain synced: ${data.synced} chapters loaded`);
    } catch (e) {
      setToast(`Brain sync failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setBrainSyncing(false);
    }
  };

  // Save flow
  const [showSaveInput, setShowSaveInput] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);

  const fetchStrategies = () => {
    fetch("/api/strategies")
      .then((r) => r.json())
      .then((data: SavedStrategy[]) => setStrategies(data.filter((s) => s.has_code)))
      .catch(() => {});
  };

  useEffect(() => { fetchStrategies(); }, []);

  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [text]);

  const handleV2Message = (data: unknown) => {
    const d = data as VibeV2Progress;

    if (d.phase) setV2RawPhase(d.phase);
    if (d.pct !== undefined) setV2Pct(d.pct);

    if (d.phase === 'orchestrating') {
      setV2Phase('Orchestrating...');
      const id = ++detailIdRef.current;
      orchestratorCardId.current = id;
      briefAccum.current = "";
      setDetailLog(prev => [...prev, {
        id,
        ts: Date.now(),
        agent: "ORCHESTRATOR",
        model: "claude-opus-4-8",
        status: "streaming",
        inputSummary: `${asset} ${timeframe}`,
      }]);
    }
    if (d.phase === 'brief_chunk') {
      setText(prev => prev + (d.text ?? ''));
      briefAccum.current += d.text ?? '';
    }
    if (d.phase === 'brief_done' && d.brief) {
      setV2Brief(d.brief);
      patchDetail(orchestratorCardId.current, {
        status: "done",
        brief: d.brief,
        fullText: briefAccum.current,
      });
    }
    if (d.phase === 'generating') {
      const att = d.attempt ?? 1;
      setV2Phase(`Generating strategy (attempt ${att}/3)...`);
      setV2Attempt(att);
      const id = ++detailIdRef.current;
      generatorCardId.current = id;
      codeAccum.current = "";
      setDetailLog(prev => [...prev, {
        id,
        ts: Date.now(),
        agent: "GENERATOR",
        model: "claude-sonnet-4-6",
        attempt: att,
        status: "streaming",
        inputSummary: `implementing brief (attempt ${att}/3)`,
      }]);
    }
    if (d.phase === 'code_chunk') {
      setText(prev => prev + (d.text ?? ''));
      codeAccum.current += d.text ?? '';
    }
    if (d.phase === 'backtesting') {
      setV2Phase('Running backtest...');
      setText('');
      // Finalize generator card with extracted code
      const codeMatch = codeAccum.current.match(/```python\s*([\s\S]*?)```/);
      const extractedCode = codeMatch ? codeMatch[1].trim() : undefined;
      patchDetail(generatorCardId.current, {
        status: "done",
        code: extractedCode,
        fullText: codeAccum.current,
      });
    }
    if (d.phase === 'backtest_result' && d.metrics) {
      const m = d.metrics as Record<string, unknown>;
      const isMetrics = (m.is_metrics ?? {}) as Record<string, unknown>;
      const oosMetrics = (m.oos_metrics ?? {}) as Record<string, unknown>;
      const id = ++detailIdRef.current;
      setDetailLog(prev => [...prev, {
        id,
        ts: Date.now(),
        agent: "ENGINE",
        model: "backtest-engine",
        status: (d as VibeV2Progress & { safe_exec_error?: string }).safe_exec_error
          || !m.agent_fn_loaded ? "warn" : "done",
        inputSummary: "running IS + OOS backtest",
        isMetrics,
        oosMetrics,
        bestVersion: typeof m.best_version === "string" ? m.best_version : undefined,
        agentFnLoaded: typeof m.agent_fn_loaded === "boolean" ? m.agent_fn_loaded : undefined,
        config: d.config,
        note: typeof m.safe_exec_error === "string" ? m.safe_exec_error : undefined,
      }]);
    }
    if (d.phase === 'evaluating') {
      setV2Phase('Expert evaluation...');
    }
    if (d.phase === 'evaluation' && d.result) {
      setV2Evaluation(d.result);
      const id = ++detailIdRef.current;
      setDetailLog(prev => [...prev, {
        id,
        ts: Date.now(),
        agent: "EVALUATOR",
        model: "claude-opus-4-8",
        status: "done",
        inputSummary: "scoring code + backtest metrics",
        evaluation: d.result,
      }]);
    }
    if (d.phase === 'decision') {
      setV2Verdict(d.verdict ?? '');
      setV2Phase(d.msg ?? '');
      const id = ++detailIdRef.current;
      setDetailLog(prev => [...prev, {
        id,
        ts: Date.now(),
        agent: "DECISION",
        model: "claude-opus-4-8",
        status: "done",
        inputSummary: "reviewing brief + metrics + evaluation",
        verdict: d.verdict,
        rationale: d.msg,
      }]);
    }
    if (d.phase === 'iteration') {
      setV2Phase(`Refining strategy (attempt ${d.attempt}/3)...`);
      setV2Brief(null);
      setV2Evaluation(null);
      setText('');
    }
    if (d.phase === 'done') {
      setGenerating(false);
      setV2Phase(d.note ? 'Done (research)' : 'Complete');
    }
    if (d.phase === 'warn') {
      // Patch last card with warn status and note
      setDetailLog(prev => {
        if (prev.length === 0) return prev;
        const last = prev[prev.length - 1];
        return prev.map(e => e.id === last.id
          ? { ...e, status: "warn" as const, note: d.msg ?? "warning" }
          : e
        );
      });
    }
    if (d.phase === 'error') {
      setGenerating(false);
      setV2Phase('Error');
      setText(prev => prev + `\n\n[Error: ${d.msg ?? 'generation failed'}]`);
      setDetailLog(prev => {
        if (prev.length === 0) return prev;
        const last = prev[prev.length - 1];
        return prev.map(e => e.id === last.id
          ? { ...e, status: "error" as const, note: d.msg ?? "generation failed" }
          : e
        );
      });
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setStatus("");
    setText("");
    setConfig(null);
    setCode(null);
    setShowSaveInput(false);
    setOutputTab("explanation");

    // Reset v2 state
    setV2Phase('');
    setV2RawPhase('');
    setV2Pct(0);
    setV2Attempt(1);
    setV2Brief(null);
    setV2Evaluation(null);
    setV2Verdict('');
    setDetailLog([]);
    detailIdRef.current = 0;
    orchestratorCardId.current = -1;
    generatorCardId.current = -1;
    briefAccum.current = "";
    codeAccum.current = "";

    const enc = encodeURIComponent(asset);
    const [assetStats, quantAnalysis, garchForecast] = await Promise.all([
      fetch(`/api/assets/${enc}/stats?interval=${timeframe}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`/api/assets/${enc}/quant?interval=${timeframe}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`/api/assets/${enc}/garch-forecast?interval=${timeframe}`).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]);

    const requestBody = JSON.stringify({
      prompt: prompt.trim(), asset, timeframe, n_candidates: 1,
      asset_stats: assetStats,
      quant_analysis: quantAnalysis,
      garch_forecast: garchForecast,
    });

    const endpoint = useV2 ? "/api/vibe/generate-v2" : "/api/vibe/generate";

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: requestBody,
      });

      if (!res.body) throw new Error("No stream body");

      try {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const ev = JSON.parse(line.slice(6));

              if (useV2) {
                handleV2Message(ev);
              } else {
                if (ev.type === "analysis_start") {
                  setStatus(`Analyzing: ${ev.tool.replace(/_/g, " ")}…`);
                }
                if (ev.type === "analysis_done") {
                  setStatus(`Analysis complete: ${ev.tool.replace(/_/g, " ")}`);
                }
                if (ev.type === "delta") setText((t) => t + ev.text);
                if (ev.type === "done") {
                  setStatus("");
                  setConfig(ev.config ?? null);
                  setCode(ev.code ?? null);
                  setGenerating(false);
                  if (ev.code) setOutputTab("code");
                  if (ev.config && ev.code) {
                    const ticker = (ev.config.ticker || asset).replace(/[^a-zA-Z0-9_=-]/g, "_");
                    const tf = ev.config.timeframe || timeframe;
                    const ts = new Date().toISOString().slice(0, 16).replace("T", "_").replace(":", "h");
                    const autoName = `vibe_${ticker}_${tf}_${ts}`;
                    fetch("/api/strategies", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        name: autoName,
                        strategy_type: "vibe",
                        config: ev.config,
                        code: ev.code,
                        status: "research",
                      }),
                    })
                      .then((r) => r.ok ? r.json() : null)
                      .then((data) => {
                        if (data?.id) {
                          setToast(`Strategy saved to Library: ${autoName} (${data.id})`);
                          fetchStrategies();
                        }
                      })
                      .catch(() => {});
                  }
                }
              }
            } catch {
              // malformed SSE line — skip
            }
          }
        }
      } catch (err) {
        console.error("Stream error:", err);
        setText((t) => t + "\n\n[Stream error — connection may have dropped]");
        setGenerating(false);
      }
    } catch {
      setText((t) => t + "\n\n[Connection error — is the API running?]");
      setGenerating(false);
    }
  };

  const handleApply = () => {
    setToast("Vibe config applied → adjust in Setup");
    goto("setup");
  };

  const handleSave = async () => {
    if (!config || !saveName.trim()) return;
    setSaving(true);
    try {
      const res = await fetch("/api/strategies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: saveName.trim(),
          strategy_type: "vibe",
          config,
          code: code ?? "",
          status: "research",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setToast(`Strategy saved (${data.id})`);
        setShowSaveInput(false);
        setSaveName("");
        fetchStrategies();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleLoad = async () => {
    const s = strategies.find((s) => s.id === selectedStratId);
    if (!s) return;
    try {
      const res = await fetch(`/api/strategies/${s.id}`);
      if (res.ok) {
        const full = await res.json();
        setConfig(full.config ?? s.config);
        setCode(full.code || null);
        setOutputTab(full.code ? "code" : "explanation");
      } else {
        setConfig(s.config);
        setCode(null);
        setOutputTab("explanation");
      }
    } catch {
      setConfig(s.config);
      setCode(null);
      setOutputTab("explanation");
    }
    setText("");
    setShowSaveInput(false);
    setToast(`Loaded: ${s.name}`);
  };

  const handleCopyCode = () => {
    if (!code) return;
    navigator.clipboard.writeText(code).then(() => setToast("Code copied to clipboard"));
  };

  const formatConfigVal = (key: string, val: unknown): string => {
    if (key === "active_hours" && Array.isArray(val)) return `${val[0]}:00 – ${val[1]}:00 UTC`;
    if (key === "risk_per_trade" && typeof val === "number") return `${val}%`;
    return String(val);
  };

  // Suppress unused variable warnings for v2RawPhase (kept for future use)
  void v2RawPhase;

  return (
    <div className={styles.grid}>
      {/* Left: form — span 4 */}
      <div className={styles.panel} style={{ gridColumn: "span 4" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>VIBE TRADING</span>
          <span className={styles.panelSub}>natural language → strategy</span>
        </div>
        <div className={styles.panelBody}>
          <div>
            <div className={styles.label}>ASSET</div>
            <select
              className={styles.assetSelect}
              value={asset}
              onChange={(e) => setAsset(e.target.value)}
            >
              {assetOptions.map((a) => (
                <option key={a} value={a}>{a.replace("-USD", "")}</option>
              ))}
            </select>
            {assetsData && assetsData.length === 0 && (
              <span className={styles.assetHint}>no data — fetch from Assets first</span>
            )}
          </div>

          <div>
            <div className={styles.label}>TIMEFRAME</div>
            <select
              className={styles.assetSelect}
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
            >
              {(availableTimeframes.length > 0
                ? availableTimeframes
                : ["5m", "15m", "1h", "4h", "1d"]
              ).map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
            {availableTimeframes.length === 0 && assetsData && assetsData.length > 0 && (
              <span className={styles.assetHint}>no data for this asset</span>
            )}
          </div>

          <div className={styles.promptWrap}>
            <div className={styles.label}>STRATEGY IDEA</div>
            <textarea
              className={styles.promptTextarea}
              rows={6}
              placeholder={
                "Describe your strategy idea… (optional)\ne.g. \"scalp BTC on 15m, long only, tighter stops at night, risk 0.5% per trade\"\nLeave blank to let Claude suggest a strategy based on the asset's statistics."
              }
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleGenerate();
              }}
            />
          </div>

          {/* Enhanced Mode toggle */}
          <div className={styles.modeToggle}>
            <label className={styles.toggleLabel}>
              <input
                type="checkbox"
                checked={useV2}
                onChange={e => setUseV2(e.target.checked)}
                disabled={generating}
              />
              <span>Enhanced Mode</span>
              <span className={styles.modeBadge}>3-agent</span>
            </label>
          </div>

          <button
            className={styles.generateBtn}
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? "▶ GENERATING…" : "▶ GENERATE"}
          </button>

          <div className={styles.hint}>
            Powered by Claude · ⌘↵ to generate · results are illustrative
          </div>

          {/* Knowledge base sync */}
          <div className={styles.loadSection}>
            <div className={styles.label}>KNOWLEDGE BASE</div>
            <div className={styles.loadRow}>
              <span className={styles.brainStatus}>
                {brainStatus
                  ? `${brainStatus.synced} chapters${brainStatus.errors > 0 ? ` · ${brainStatus.errors} errors` : ""}`
                  : "not synced"}
              </span>
              <button
                className={styles.loadBtn}
                onClick={handleBrainSync}
                disabled={brainSyncing}
              >
                {brainSyncing ? "SYNCING…" : "SYNC"}
              </button>
            </div>
            <div className={styles.hint} style={{ marginTop: 4 }}>
              Downloads ML-trading book chapters for smarter strategy generation
            </div>
          </div>

          {/* Load previous strategy */}
          {strategies.length > 0 && (
            <div className={styles.loadSection}>
              <div className={styles.label}>LOAD PREVIOUS</div>
              <div className={styles.loadRow}>
                <select
                  className={styles.assetSelect}
                  style={{ flex: 1, minWidth: 0 }}
                  value={selectedStratId}
                  onChange={(e) => setSelectedStratId(e.target.value)}
                >
                  <option value="">— select —</option>
                  {strategies.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                <button
                  className={styles.loadBtn}
                  onClick={handleLoad}
                  disabled={!selectedStratId}
                >
                  LOAD
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right: output — span 8 */}
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>OUTPUT</span>
          <span className={styles.panelSub}>
            {status
              ? status
              : generating ? "streaming…" : config ? "done" : "waiting"}
          </span>
          <span style={{ flex: 1 }} />
          {/* Tab switcher */}
          <button
            className={`${styles.tabBtn} ${outputTab === "explanation" ? styles.tabBtnActive : ""}`}
            onClick={() => setOutputTab("explanation")}
          >
            EXPLANATION
          </button>
          <button
            className={`${styles.tabBtn} ${outputTab === "code" ? styles.tabBtnActive : ""} ${code ? styles.tabBtnHasData : ""}`}
            onClick={() => setOutputTab("code")}
          >
            CODE{code ? " ●" : ""}
          </button>
        </div>
        <div className={styles.panelBody}>

          {/* ── v2 progress bar ── */}
          {useV2 && generating && (
            <div className={styles.v2Progress}>
              <div className={styles.v2Phase}>{v2Phase}</div>
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: `${v2Pct}%` }} />
              </div>
              {v2Attempt > 1 && (
                <div className={styles.attemptBadge}>Attempt {v2Attempt}/3</div>
              )}
            </div>
          )}

          {/* ── v2 verdict banner (after completion) ── */}
          {useV2 && !generating && v2Verdict && (
            <div className={styles.v2Progress}>
              <div className={styles.v2Phase}>{v2Phase} · verdict: {v2Verdict}</div>
            </div>
          )}

          {/* ── architecture brief (collapsible) ── */}
          {v2Brief && (
            <details className={styles.briefPanel}>
              <summary>Architecture Brief · {v2Brief.strategy_type} · confidence: {v2Brief.confidence}</summary>
              <p><strong>Regime:</strong> {v2Brief.regime_assessment}</p>
              <p><strong>Edge:</strong> {v2Brief.edge_hypothesis}</p>
              <p><strong>Entry:</strong> {v2Brief.entry_logic}</p>
              <p><strong>Indicators:</strong> {v2Brief.recommended_indicators.join(', ')}</p>
            </details>
          )}

          {/* ── EXPLANATION tab ── */}
          {outputTab === "explanation" && (
            <>
              <div className={styles.streamBox} ref={streamRef}>
                {text ? (
                  <>
                    {text}
                    {generating && <span className={styles.cursor} />}
                  </>
                ) : (
                  <span className={styles.emptyHint}>
                    {generating ? "Connecting…" : "Claude response will appear here…"}
                  </span>
                )}
              </div>

              {/* ── evaluation card (v2 only) ── */}
              {v2Evaluation && (
                <EvaluationCard evaluation={v2Evaluation} attempt={v2Attempt} />
              )}

              {config && (
                <div className={styles.configTable}>
                  {(Object.keys(CONFIG_LABELS) as (keyof StrategyConfig)[]).map((key) => {
                    const val = config[key];
                    if (val === undefined) return null;
                    return (
                      <div key={key} className={styles.configRow}>
                        <span className={styles.configKey}>{CONFIG_LABELS[key]}</span>
                        <span className={styles.configVal}>{formatConfigVal(key, val)}</span>
                      </div>
                    );
                  })}
                </div>
              )}

              {config && (
                <div className={styles.actionRow}>
                  {showSaveInput ? (
                    <div className={styles.saveInputRow}>
                      <input
                        className={styles.saveInput}
                        placeholder="strategy name…"
                        value={saveName}
                        onChange={(e) => setSaveName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSave()}
                        autoFocus
                      />
                      <button
                        className={styles.saveConfirmBtn}
                        onClick={handleSave}
                        disabled={saving || !saveName.trim()}
                      >
                        {saving ? "…" : "SAVE"}
                      </button>
                      <button
                        className={styles.cancelBtn}
                        onClick={() => { setShowSaveInput(false); setSaveName(""); }}
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button className={styles.saveOutlineBtn} onClick={() => setShowSaveInput(true)}>
                      + SAVE
                    </button>
                  )}
                  <button className={styles.applyBtn} onClick={handleApply}>
                    APPLY TO SETUP →
                  </button>
                </div>
              )}
            </>
          )}

          {/* ── CODE tab ── */}
          {outputTab === "code" && (
            <>
              <div className={styles.codeSection} style={{ flex: 1 }}>
                <div className={styles.codeSectionHeader}>
                  <span className={styles.codeSectionTitle}>STRATEGY CODE (Python agent_fn)</span>
                  <button className={styles.copyBtn} onClick={handleCopyCode} disabled={!code}>
                    COPY
                  </button>
                </div>
                <pre className={`${styles.codeBox} ${styles.codeBoxTall}`}>
                  {code ?? <span className={styles.emptyHint}>No code yet — generate a strategy or load one from the dropdown.</span>}
                </pre>
              </div>

              {config && (
                <div className={styles.actionRow}>
                  {showSaveInput ? (
                    <div className={styles.saveInputRow}>
                      <input
                        className={styles.saveInput}
                        placeholder="strategy name…"
                        value={saveName}
                        onChange={(e) => setSaveName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSave()}
                        autoFocus
                      />
                      <button
                        className={styles.saveConfirmBtn}
                        onClick={handleSave}
                        disabled={saving || !saveName.trim()}
                      >
                        {saving ? "…" : "SAVE"}
                      </button>
                      <button
                        className={styles.cancelBtn}
                        onClick={() => { setShowSaveInput(false); setSaveName(""); }}
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button className={styles.saveOutlineBtn} onClick={() => setShowSaveInput(true)}>
                      + SAVE
                    </button>
                  )}
                  <button className={styles.applyBtn} onClick={handleApply}>
                    APPLY TO SETUP →
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Agent Workflow — full width */}
      <div style={{ gridColumn: "span 12" }}>
        <AgentWorkflow
          useV2={useV2}
          generating={generating}
          v2RawPhase={v2RawPhase}
          v2Attempt={v2Attempt}
          v2Verdict={v2Verdict}
          v1Status={status}
        />
      </div>

      {/* Agent Detail Log — always visible */}
      <div style={{ gridColumn: "span 12" }}>
        <AgentDetailLog
          entries={detailLog}
          onClear={() => { setDetailLog([]); detailIdRef.current = 0; }}
        />
      </div>
    </div>
  );
}
