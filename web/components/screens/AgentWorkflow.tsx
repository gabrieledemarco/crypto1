"use client";
import React, { Fragment } from "react";
import styles from "./AgentWorkflow.module.css";

type Status = "idle" | "active" | "done" | "error";

const STATUS_LABEL: Record<Status, string> = {
  idle: "IDLE",
  active: "PROCESSING",
  done: "DONE",
  error: "FAILED",
};

const V2_NODES = [
  { id: "orchestrator", label: "ORCHESTRATOR", model: "opus-4.5",   role: "market ctx · brief"         },
  { id: "generator",    label: "GENERATOR",    model: "sonnet-4.6", role: "code · backtest"             },
  { id: "evaluator",    label: "EVALUATOR",    model: "opus-4.5",   role: "6-dim scoring"               },
  { id: "decision",     label: "DECISION",     model: "opus-4.5",   role: "promote · iterate · reject"  },
] as const;

type NodeId = typeof V2_NODES[number]["id"];

// Phase → which agent owns it (used to pinpoint failures)
const PHASE_OWNER: Record<string, NodeId> = {
  orchestrating: "orchestrator", brief_chunk: "orchestrator", brief_done: "orchestrator",
  generating: "generator", code_chunk: "generator", backtesting: "generator", iteration: "generator",
  evaluating: "evaluator", evaluation: "evaluator",
  decision: "decision",
};

function deriveStates(raw: string, lastGoodPhase: string, generating: boolean, verdict: string): Record<NodeId, Status> {
  if (!generating && !raw)
    return { orchestrator: "idle", generator: "idle", evaluator: "idle", decision: "idle" };
  if (raw === "done")
    return { orchestrator: "done", generator: "done", evaluator: "done", decision: verdict === "reject" ? "error" : "done" };
  if (raw === "error") {
    // Blame the agent that owned the last successful phase
    const failed = PHASE_OWNER[lastGoodPhase] ?? "orchestrator";
    const s: Record<NodeId, Status> = { orchestrator: "done", generator: "done", evaluator: "done", decision: "done" };
    // Mark nodes before the failing one as done, the failing one as error, rest as idle
    const order: NodeId[] = ["orchestrator", "generator", "evaluator", "decision"];
    const idx = order.indexOf(failed);
    order.forEach((id, i) => { s[id] = i < idx ? "done" : i === idx ? "error" : "idle"; });
    return s;
  }
  if (["orchestrating", "brief_chunk", "brief_done"].includes(raw))
    return { orchestrator: "active", generator: "idle", evaluator: "idle", decision: "idle" };
  if (["generating", "code_chunk", "backtesting", "iteration"].includes(raw))
    return { orchestrator: "done", generator: "active", evaluator: "idle", decision: "idle" };
  if (["evaluating", "evaluation"].includes(raw))
    return { orchestrator: "done", generator: "done", evaluator: "active", decision: "idle" };
  if (raw === "decision")
    return { orchestrator: "done", generator: "done", evaluator: "done", decision: "active" };
  return { orchestrator: "idle", generator: "idle", evaluator: "idle", decision: "idle" };
}

function nodeDetail(id: NodeId, raw: string, verdict: string, attempt: number): string {
  if (id === "orchestrator") {
    if (raw === "orchestrating" || raw === "brief_chunk") return "analyzing market…";
    if (["brief_done", "generating", "code_chunk", "backtesting", "evaluating", "evaluation", "decision", "iteration", "done"].includes(raw))
      return "brief ready";
    return "";
  }
  if (id === "generator") {
    if (raw === "generating" || raw === "iteration") return attempt > 1 ? `iteration ${attempt}/3` : "writing code…";
    if (raw === "code_chunk") return "streaming…";
    if (raw === "backtesting") return "running backtest…";
    if (["evaluating", "evaluation", "decision", "done"].includes(raw)) return "code + metrics";
    return "";
  }
  if (id === "evaluator") {
    if (raw === "evaluating") return "scoring…";
    if (["evaluation", "decision", "done"].includes(raw)) return "scored";
    return "";
  }
  if (id === "decision") {
    if (raw === "decision") return "deciding…";
    if (raw === "done") return verdict || "complete";
    return "";
  }
  return "";
}

interface Props {
  useV2: boolean;
  generating: boolean;
  v2RawPhase: string;
  v2Attempt: number;
  v2Verdict: string;
  v1Status: string;
}

export function AgentWorkflow({ useV2, generating, v2RawPhase, v2Attempt, v2Verdict, v1Status }: Props) {
  // Track last non-error phase to identify which agent actually failed
  const lastGoodPhaseRef = React.useRef("");
  if (v2RawPhase && v2RawPhase !== "error" && v2RawPhase !== "done") {
    lastGoodPhaseRef.current = v2RawPhase;
  }
  if (!generating && !v2RawPhase) lastGoodPhaseRef.current = "";

  const states = deriveStates(v2RawPhase, lastGoodPhaseRef.current, generating, v2Verdict);
  const allDone = !generating && v2RawPhase === "done";

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.title}>LIVE AGENT DATA FLOW</span>
        <span className={styles.sub}>
          {useV2 ? "Enhanced Mode · 3-agent orchestrated pipeline" : "Standard Mode · single-agent generation"}
        </span>
        {generating && <span className={styles.liveBadge}>● LIVE</span>}
      </div>

      <div className={styles.flow}>
        <AgentNode
          label="INPUT"
          sub="prompt + asset stats"
          status={generating ? "active" : allDone ? "done" : "idle"}
          isEndpoint
        />

        {useV2 ? (
          V2_NODES.map((n) => {
            const st = states[n.id];
            const detail = nodeDetail(n.id, v2RawPhase, v2Verdict, v2Attempt);
            return (
              <Fragment key={n.id}>
                <FlowArrow status={st} />
                <AgentNode label={n.label} sub={n.model} detail={detail} status={st} />
              </Fragment>
            );
          })
        ) : (
          <>
            <FlowArrow status={generating ? "active" : "idle"} />
            <AgentNode
              label="ANALYST"
              sub="claude-sonnet-4.6"
              detail={v1Status || "tool calls · streaming"}
              status={generating ? "active" : "idle"}
            />
          </>
        )}

        <FlowArrow status={allDone ? "done" : "idle"} />

        <AgentNode
          label="OUTPUT"
          sub="strategy + code"
          status={allDone ? "done" : "idle"}
          isEndpoint
        />
      </div>
    </div>
  );
}

function AgentNode({ label, sub, detail, status, isEndpoint = false }: {
  label: string; sub: string; detail?: string; status: Status; isEndpoint?: boolean;
}) {
  return (
    <div className={[
      styles.node,
      isEndpoint      ? styles.nodeEndpoint : "",
      status === "active" ? styles.nodeActive  : "",
      status === "done"   ? styles.nodeDone    : "",
      status === "error"  ? styles.nodeError   : "",
    ].filter(Boolean).join(" ")}>
      <span className={styles.nodeLabel}>{label}</span>
      <span className={styles.nodeSub}>{sub}</span>
      {detail && <span className={styles.nodeDetail}>{detail}</span>}
      <span className={[
        styles.badge,
        status === "active" ? styles.badgeActive : "",
        status === "done"   ? styles.badgeDone   : "",
        status === "error"  ? styles.badgeError  : "",
      ].filter(Boolean).join(" ")}>
        {STATUS_LABEL[status]}
      </span>
    </div>
  );
}

function FlowArrow({ status }: { status: Status }) {
  return (
    <div className={[
      styles.arrow,
      status === "active"                    ? styles.arrowActive : "",
      status === "done" || status === "error" ? styles.arrowDone   : "",
    ].filter(Boolean).join(" ")}>
      <span className={styles.arrowLine} />
      <span className={styles.arrowHead}>▶</span>
    </div>
  );
}
