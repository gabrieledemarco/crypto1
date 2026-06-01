"use client";
import React, { useEffect, useRef } from "react";
import styles from "./AgentLog.module.css";

export type LogAgent =
  | "ORCHESTRATOR"
  | "GENERATOR"
  | "EVALUATOR"
  | "DECISION"
  | "ENGINE"
  | "SYSTEM";

export interface LogEntry {
  id: number;
  ts: number;
  agent: LogAgent;
  text: string;
  type: "msg" | "data" | "error";
}

interface Props {
  entries: LogEntry[];
  onClear: () => void;
}

const AGENT_CLR: Record<LogAgent, string> = {
  ORCHESTRATOR: "#ffb000",
  GENERATOR:    "#38bdf8",
  EVALUATOR:    "#c084fc",
  DECISION:     "#4ade80",
  ENGINE:       "#94a3b8",
  SYSTEM:       "#64748b",
};

function fmtTs(ms: number) {
  const d = new Date(ms);
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map(n => String(n).padStart(2, "0"))
    .join(":");
}

export function AgentLog({ entries, onClear }: Props) {
  const tailRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    tailRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.title}>PIPELINE LOG</span>
        <span className={styles.sub}>agent messages · process events</span>
        <span className={styles.spacer} />
        <span className={styles.count}>{entries.length} events</span>
        {entries.length > 0 && (
          <button className={styles.clearBtn} onClick={onClear}>CLR</button>
        )}
      </div>

      <div className={styles.body}>
        {entries.length === 0 ? (
          <div className={styles.empty}>
            Pipeline log appears here during Enhanced Mode generation…
          </div>
        ) : (
          entries.map(e => (
            <div
              key={e.id}
              className={[
                styles.row,
                e.type === "error" ? styles.rowError : "",
                e.type === "data"  ? styles.rowData  : "",
              ].filter(Boolean).join(" ")}
            >
              <span className={styles.time}>{fmtTs(e.ts)}</span>
              <span className={styles.agentLabel} style={{ color: AGENT_CLR[e.agent] }}>
                {e.agent}
              </span>
              <span className={styles.text}>{e.text}</span>
            </div>
          ))
        )}
        <div ref={tailRef} />
      </div>
    </div>
  );
}
