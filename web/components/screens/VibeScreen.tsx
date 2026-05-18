"use client";
import { useState, useRef, useEffect } from "react";
import { useStore } from "@/store";
import styles from "./VibeScreen.module.css";

const ASSETS = ["BTC-USD", "ETH-USD", "SOL-USD", "ARB-USD", "OP-USD", "AVAX-USD"];

interface StrategyConfig {
  ticker?: string;
  timeframe?: string;
  sl_mult?: number;
  tp_mult?: number;
  active_hours?: number[];
  risk_per_trade?: number;
  direction?: string;
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
  const { goto, setToast } = useStore();
  const [asset, setAsset] = useState("BTC-USD");
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [text, setText] = useState("");
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const streamRef = useRef<HTMLDivElement>(null);

  // Auto-scroll stream box
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [text]);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    setText("");
    setConfig(null);

    try {
      const res = await fetch("/api/vibe/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim(), asset, n_candidates: 1 }),
      });

      if (!res.body) throw new Error("No stream body");

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
            if (ev.type === "delta") setText((t) => t + ev.text);
            if (ev.type === "done") {
              setConfig(ev.config ?? null);
              setGenerating(false);
            }
          } catch {
            // malformed SSE line — skip
          }
        }
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

  const formatConfigVal = (key: string, val: unknown): string => {
    if (key === "active_hours" && Array.isArray(val)) return `${val[0]}:00 – ${val[1]}:00 UTC`;
    if (key === "risk_per_trade" && typeof val === "number") return `${val}%`;
    return String(val);
  };

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
            <div className={styles.assetPills}>
              {ASSETS.map((a) => (
                <button
                  key={a}
                  className={`${styles.pill} ${asset === a ? styles.pillActive : ""}`}
                  onClick={() => setAsset(a)}
                >
                  {a.replace("-USD", "")}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.promptWrap}>
            <div className={styles.label}>STRATEGY IDEA</div>
            <textarea
              className={styles.promptTextarea}
              rows={8}
              placeholder={
                "Describe your strategy idea…\ne.g. \"scalp BTC on 15m, long only, tighter stops at night, risk 0.5% per trade\""
              }
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleGenerate();
              }}
            />
          </div>

          <button
            className={styles.generateBtn}
            onClick={handleGenerate}
            disabled={generating || !prompt.trim()}
          >
            {generating ? "▶ GENERATING…" : "▶ GENERATE"}
          </button>

          <div className={styles.hint}>
            Powered by Claude · ⌘↵ to generate · results are illustrative
          </div>
        </div>
      </div>

      {/* Right: output — span 8 */}
      <div className={styles.panel} style={{ gridColumn: "span 8" }}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>OUTPUT</span>
          <span className={styles.panelSub}>
            {generating ? "streaming…" : config ? "done" : "waiting"}
          </span>
        </div>
        <div className={styles.panelBody}>
          {/* Streaming text */}
          <div className={styles.streamBox} ref={streamRef}>
            {text ? (
              <>
                {text}
                {generating && <span className={styles.cursor} />}
              </>
            ) : (
              <span className={styles.emptyHint}>
                {generating
                  ? "Connecting…"
                  : "Claude response will appear here…"}
              </span>
            )}
          </div>

          {/* Config table */}
          {config && (
            <>
              <div className={styles.configTable}>
                {(Object.keys(CONFIG_LABELS) as (keyof StrategyConfig)[]).map((key) => {
                  const val = config[key];
                  if (val === undefined) return null;
                  return (
                    <div key={key} className={styles.configRow}>
                      <span className={styles.configKey}>{CONFIG_LABELS[key]}</span>
                      <span className={styles.configVal}>
                        {formatConfigVal(key, val)}
                      </span>
                    </div>
                  );
                })}
              </div>

              <button className={styles.applyBtn} onClick={handleApply}>
                APPLY TO SETUP →
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
