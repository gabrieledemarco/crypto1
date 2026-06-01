"use client";
import React from "react";
import { StrategyBrief, StrategyEvaluation } from "@/lib/api-types";
import styles from "./AgentDetailLog.module.css";

export type DetailAgent =
  | "ORCHESTRATOR"
  | "GENERATOR"
  | "EVALUATOR"
  | "DECISION"
  | "ENGINE";

export interface DetailEntry {
  id: number;
  ts: number;
  agent: DetailAgent;
  model: string;
  attempt?: number;
  status: "streaming" | "done" | "warn" | "error";
  inputSummary: string;
  brief?: StrategyBrief;
  code?: string;
  config?: Record<string, unknown>;
  isMetrics?: Record<string, unknown>;
  oosMetrics?: Record<string, unknown>;
  bestVersion?: string;
  agentFnLoaded?: boolean;
  evaluation?: StrategyEvaluation;
  verdict?: string;
  rationale?: string;
  fullText?: string;
  note?: string;
}

interface Props {
  entries: DetailEntry[];
  onClear: () => void;
}

const AGENT_COLOR: Record<DetailAgent, string> = {
  ORCHESTRATOR: "#ffb000",
  GENERATOR:    "#38bdf8",
  EVALUATOR:    "#c084fc",
  DECISION:     "#4ade80",
  ENGINE:       "#94a3b8",
};

const SCORE_LABELS: Record<string, string> = {
  alpha_source:           "Alpha",
  signal_logic:           "Signal",
  risk_management:        "Risk",
  regime_sensitivity:     "Regime",
  statistical_robustness: "Stats",
  implementation_quality: "Impl",
};

function fmtTs(ms: number) {
  const d = new Date(ms);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, "0"))
    .join(":");
}

function fmtNum(v: unknown, dec = 2): string {
  if (v === undefined || v === null || v === "") return "N/A";
  const n = Number(v);
  return isNaN(n) ? "N/A" : n.toFixed(dec);
}

function scoreClass(v: number): string {
  if (v >= 4) return styles.scoreGreen;
  if (v >= 3) return styles.scoreAmber;
  return styles.scoreRed;
}

function StatusBadge({ status }: { status: DetailEntry["status"] }) {
  const cls = {
    streaming: styles.badgeStreaming,
    done:      styles.badgeDone,
    warn:      styles.badgeWarn,
    error:     styles.badgeError,
  }[status];
  const label = {
    streaming: "STREAMING…",
    done:      "DONE",
    warn:      "WARN",
    error:     "ERROR",
  }[status];
  return <span className={`${styles.badge} ${cls}`}>{label}</span>;
}

function MetricsRow({
  label,
  m,
}: {
  label: string;
  m: Record<string, unknown>;
}) {
  const sharpe = m.sharpe_ratio ?? m.sharpe;
  const dd     = m.max_drawdown_pct ?? m.max_dd;
  const trades = m.n_trades;
  const wr     = m.win_rate_pct;
  return (
    <div className={styles.dataRow}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={styles.rowValue}>
        Sharpe {fmtNum(sharpe, 3)} &nbsp;|&nbsp;
        DD {fmtNum(dd, 1)}% &nbsp;|&nbsp;
        Trades {trades !== undefined && trades !== null ? String(trades) : "N/A"} &nbsp;|&nbsp;
        Win {fmtNum(wr, 1)}%
      </span>
    </div>
  );
}

function OrchestratorBody({ e }: { e: DetailEntry }) {
  const b = e.brief;
  if (!b) return null;
  return (
    <div className={styles.body}>
      <div className={styles.dataRow}>
        <span className={styles.rowLabel}>TYPE</span>
        <span className={styles.rowValue}>{b.strategy_type}</span>
        <span className={styles.rowLabel} style={{ marginLeft: 12 }}>CONF</span>
        <span className={styles.rowValue}>{b.confidence}</span>
      </div>
      <div className={styles.dataRow}>
        <span className={styles.rowLabel}>EDGE</span>
        <span className={styles.rowValue}>{b.edge_hypothesis}</span>
      </div>
      <div className={styles.dataRow}>
        <span className={styles.rowLabel}>ENTRY</span>
        <span className={styles.rowValue}>{b.entry_logic}</span>
      </div>
      {b.recommended_indicators?.length > 0 && (
        <div className={styles.dataRow}>
          <span className={styles.rowLabel}>INDICATORS</span>
          <span className={styles.rowValue}>{b.recommended_indicators.join(", ")}</span>
        </div>
      )}
      {b.entry_filters?.length > 0 && (
        <div className={styles.dataRow}>
          <span className={styles.rowLabel}>FILTERS</span>
          <span className={styles.rowValue}>{b.entry_filters.join(" · ")}</span>
        </div>
      )}
      {e.fullText && (
        <details className={styles.details}>
          <summary>Full analysis text</summary>
          <pre className={styles.codeBlock}>{e.fullText}</pre>
        </details>
      )}
    </div>
  );
}

function GeneratorBody({ e }: { e: DetailEntry }) {
  const c = e.config;
  return (
    <div className={styles.body}>
      {c && (
        <div className={styles.dataRow}>
          <span className={styles.rowLabel}>CONFIG</span>
          <span className={styles.rowValue}>
            SL×{c.sl_mult ?? "?"} &nbsp;|&nbsp;
            TP×{c.tp_mult ?? "?"} &nbsp;|&nbsp;
            Dir {String(c.direction ?? "ALL")} &nbsp;|&nbsp;
            Hours {Array.isArray(c.active_hours)
              ? `${(c.active_hours as number[])[0]}–${(c.active_hours as number[])[1]}`
              : "?"
            }
          </span>
        </div>
      )}
      {e.code && (
        <details className={styles.details}>
          <summary>Code ({e.code.split("\n").length} lines)</summary>
          <pre className={styles.codeBlock}>{e.code}</pre>
        </details>
      )}
      {!e.code && e.fullText && (
        <details className={styles.details}>
          <summary>Generator output</summary>
          <pre className={styles.codeBlock}>{e.fullText}</pre>
        </details>
      )}
    </div>
  );
}

function EngineBody({ e }: { e: DetailEntry }) {
  const is  = (e.isMetrics  ?? {}) as Record<string, unknown>;
  const oos = (e.oosMetrics ?? {}) as Record<string, unknown>;
  const hasOos = Object.keys(oos).length > 0;
  return (
    <div className={styles.body}>
      <MetricsRow label="IS" m={is} />
      {hasOos && <MetricsRow label="OOS" m={oos} />}
      {e.bestVersion && (
        <div className={styles.dataRow}>
          <span className={styles.rowLabel}>VERSION</span>
          <span className={styles.rowValue}>{e.bestVersion}</span>
        </div>
      )}
      {e.agentFnLoaded === false && (
        <div className={styles.warnNote}>
          agent_fn not loaded — backtest ran fallback signals
        </div>
      )}
      {e.note && (
        <div className={styles.warnNote}>{e.note}</div>
      )}
    </div>
  );
}

function EvaluatorBody({ e }: { e: DetailEntry }) {
  const ev = e.evaluation;
  if (!ev) return null;
  const scores = ev.scores ?? ({} as Record<string, number>);
  return (
    <div className={styles.body}>
      <div className={styles.scoreRow}>
        {Object.entries(scores).map(([k, v]) => (
          <span key={k} className={`${styles.scoreChip} ${scoreClass(v)}`}>
            {SCORE_LABELS[k] ?? k}:{v}
          </span>
        ))}
        <span className={`${styles.scoreChip} ${scoreClass(ev.overall_score ?? 0)} ${styles.scoreOverall}`}>
          Overall:{fmtNum(ev.overall_score, 1)}
        </span>
      </div>
      {ev.verdict_rationale && (
        <div className={styles.dataRow}>
          <span className={styles.rowValue}>{ev.verdict_rationale}</span>
        </div>
      )}
      {ev.fatal_flaws?.length > 0 && (
        <div className={styles.fatalFlaws}>
          {ev.fatal_flaws.map((f, i) => (
            <div key={i} className={styles.fatalFlaw}>FATAL: {f}</div>
          ))}
        </div>
      )}
      {(ev.weaknesses?.length > 0 || ev.specific_improvements?.length > 0) && (
        <details className={styles.details}>
          <summary>Weaknesses &amp; improvements</summary>
          {ev.weaknesses?.map((w, i) => (
            <div key={i} className={styles.weakness}>⚠ {w}</div>
          ))}
          {ev.specific_improvements?.map((s, i) => (
            <div key={i} className={styles.improvement}>→ {s}</div>
          ))}
        </details>
      )}
    </div>
  );
}

function DecisionBody({ e }: { e: DetailEntry }) {
  const v = (e.verdict ?? "").toLowerCase();
  const cls = v === "promote"
    ? styles.verdictPromote
    : v === "iterate"
    ? styles.verdictIterate
    : styles.verdictReject;
  return (
    <div className={styles.body}>
      <div className={styles.verdictRow}>
        <span className={`${styles.verdictBadge} ${cls}`}>
          {(e.verdict ?? "UNKNOWN").toUpperCase()}
        </span>
      </div>
      {e.rationale && (
        <div className={styles.dataRow}>
          <span className={styles.rowValue}>{e.rationale}</span>
        </div>
      )}
    </div>
  );
}

function AgentCard({ e }: { e: DetailEntry }) {
  const color = AGENT_COLOR[e.agent];
  return (
    <div className={styles.card} style={{ borderLeftColor: color }}>
      <div className={styles.cardHeader}>
        <span className={styles.agentName} style={{ color }}>{e.agent}</span>
        <span className={styles.modelTag}>{e.model}</span>
        <span className={styles.timeTag}>{fmtTs(e.ts)}</span>
        {e.attempt !== undefined && (
          <span className={styles.attemptBadge}>attempt {e.attempt}/3</span>
        )}
        <span style={{ flex: 1 }} />
        <StatusBadge status={e.status} />
      </div>

      <div className={styles.inRow}>
        <span className={styles.inTag}>IN</span>
        <span className={styles.inText}>{e.inputSummary}</span>
      </div>

      {e.status !== "streaming" && (
        <>
          {e.agent === "ORCHESTRATOR" && <OrchestratorBody e={e} />}
          {e.agent === "GENERATOR"    && <GeneratorBody    e={e} />}
          {e.agent === "ENGINE"       && <EngineBody       e={e} />}
          {e.agent === "EVALUATOR"    && <EvaluatorBody    e={e} />}
          {e.agent === "DECISION"     && <DecisionBody     e={e} />}
        </>
      )}

      {e.status === "streaming" && (
        <div className={styles.streamingRow}>
          <span className={styles.streamingDot} />
          <span className={styles.streamingText}>processing…</span>
        </div>
      )}
    </div>
  );
}

export function AgentDetailLog({ entries, onClear }: Props) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.title}>AGENT DETAIL LOG</span>
        <span className={styles.sub}>per-agent input · processing · output</span>
        <span style={{ flex: 1 }} />
        <span className={styles.count}>{entries.length} agents</span>
        {entries.length > 0 && (
          <button className={styles.clearBtn} onClick={onClear}>CLR</button>
        )}
      </div>
      <div className={styles.scrollBody}>
        {entries.length === 0 ? (
          <div className={styles.empty}>
            Agent details appear here during Enhanced Mode generation…
          </div>
        ) : (
          entries.map(e => <AgentCard key={e.id} e={e} />)
        )}
      </div>
    </div>
  );
}
