"use client";
import { useEffect } from "react";
import { useStore } from "@/store";
import { fixtures, type Run } from "@/lib/fixtures";
import { TopBar } from "@/components/shell/TopBar";
import { Sidebar } from "@/components/shell/Sidebar";
import { StatusBar } from "@/components/shell/StatusBar";
import { Palette } from "@/components/shell/Palette";
import { HelpToast } from "@/components/shell/HelpToast";
import { Toast } from "@/components/shell/Toast";
import { useHotkeys } from "@/hooks/useHotkeys";

// ── Shell ────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { runs, activeRunId, screen, paletteOpen, setPaletteOpen, toast, setRun } =
    useStore();

  // Seed store with fixture data on mount
  useEffect(() => {
    if (runs.length === 0) {
      useStore.getState().setRuns(fixtures.runs);
      useStore.getState().setRun(fixtures.activeRunId);
    }
  }, [runs.length]);

  // Activate hotkeys
  useHotkeys();

  const run = runs.find((r) => r.id === activeRunId);
  const screenLabel = screen.toUpperCase();

  return (
    <div className="app">
      <TopBar
        run={run}
        runs={runs}
        setRunId={setRun}
        screenLabel={screenLabel}
        onOpenPalette={() => setPaletteOpen(true)}
      />
      <div className="body">
        <Sidebar />
        <main className="main">
          <DashboardContent run={run} runs={runs} />
        </main>
      </div>
      <StatusBar />
      {paletteOpen && <Palette />}
      <HelpToast />
      <Toast msg={toast} />
    </div>
  );
}

// ── Dashboard main content ───────────────────────────────────────────────────

interface DashboardContentProps {
  run: Run | undefined;
  runs: Run[];
}

function MetricCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <div
      style={{
        background: "var(--panel)",
        border: "1px solid var(--border)",
        padding: "10px 14px",
        minWidth: 120,
      }}
    >
      <div
        style={{
          color: "var(--faint)",
          fontSize: 9,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          color: color ?? "var(--amber)",
          fontSize: 18,
          fontWeight: 700,
          lineHeight: 1,
        }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ color: "var(--faint)", fontSize: 10, marginTop: 3 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function RunRow({ r, active }: { r: Run; active: boolean }) {
  const { setRun } = useStore();
  return (
    <tr
      onClick={() => setRun(r.id)}
      style={{
        cursor: "pointer",
        background: active ? "var(--panel-3)" : "transparent",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <td
        style={{
          padding: "5px 8px",
          color: active ? "var(--amber)" : "var(--text)",
        }}
      >
        {active ? "▶ " : "  "}
        {r.name}
      </td>
      <td style={{ padding: "5px 8px", color: "var(--dim)" }}>{r.strategy}</td>
      <td
        style={{
          padding: "5px 8px",
          color: r.metricsOOS.sharpe >= 1.5 ? "var(--green)" : "var(--amber)",
          textAlign: "right",
        }}
      >
        {r.metricsOOS.sharpe.toFixed(2)}
      </td>
      <td
        style={{
          padding: "5px 8px",
          color: r.metricsOOS.cagr >= 0 ? "var(--green)" : "var(--coral)",
          textAlign: "right",
        }}
      >
        {(r.metricsOOS.cagr * 100).toFixed(1)}%
      </td>
      <td
        style={{
          padding: "5px 8px",
          color: "var(--coral)",
          textAlign: "right",
        }}
      >
        {(r.metricsOOS.maxDD * 100).toFixed(1)}%
      </td>
      <td
        style={{ padding: "5px 8px", color: "var(--dim)", textAlign: "right" }}
      >
        {r.tradesCount}
      </td>
      <td
        style={{ padding: "5px 8px", color: "var(--dim)", textAlign: "right" }}
      >
        {(r.winRate * 100).toFixed(0)}%
      </td>
    </tr>
  );
}

function DashboardContent({ run, runs }: DashboardContentProps) {
  if (!run) {
    return (
      <div style={{ color: "var(--faint)", padding: 20 }}>
        Loading fixture data...
      </div>
    );
  }

  const oos = run.metricsOOS;
  const iis = run.metricsIS;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 12,
          borderBottom: "1px solid var(--border)",
          paddingBottom: 8,
        }}
      >
        <span style={{ color: "var(--amber)", fontSize: 14, fontWeight: 700 }}>
          DASHBOARD
        </span>
        <span style={{ color: "var(--dim)", fontSize: 11 }}>
          — fixture data loaded ·{" "}
          <span style={{ color: "var(--green)" }}>{runs.length} runs</span>
        </span>
        <span
          style={{ color: "var(--faint)", fontSize: 10, marginLeft: "auto" }}
        >
          active: {run.name} · {run.strategy}
        </span>
      </div>

      {/* OOS metrics grid */}
      <div>
        <div
          style={{
            color: "var(--faint)",
            fontSize: 9,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          Out-of-sample metrics · {run.dates.oosStart} → {run.dates.oosEnd}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <MetricCard
            label="Sharpe"
            value={oos.sharpe.toFixed(2)}
            color={oos.sharpe >= 1.5 ? "var(--green)" : "var(--amber)"}
          />
          <MetricCard
            label="Sortino"
            value={oos.sortino.toFixed(2)}
            color="var(--amber)"
          />
          <MetricCard
            label="CAGR"
            value={`${(oos.cagr * 100).toFixed(1)}%`}
            color={oos.cagr >= 0 ? "var(--green)" : "var(--coral)"}
          />
          <MetricCard
            label="Max DD"
            value={`${(oos.maxDD * 100).toFixed(1)}%`}
            color="var(--coral)"
          />
          <MetricCard
            label="Calmar"
            value={oos.calmar.toFixed(2)}
            color="var(--amber)"
          />
          <MetricCard
            label="Win Rate"
            value={`${(run.winRate * 100).toFixed(0)}%`}
            color="var(--amber)"
          />
          <MetricCard
            label="Profit Factor"
            value={run.profitFactor.toFixed(2)}
            color={run.profitFactor >= 1.5 ? "var(--green)" : "var(--amber)"}
          />
          <MetricCard
            label="Trades"
            value={String(run.tradesCount)}
            color="var(--cyan)"
          />
          <MetricCard
            label="Avg Dur"
            value={`${run.avgDur}h`}
            color="var(--dim)"
          />
          <MetricCard
            label="Exposure"
            value={`${(run.exposure * 100).toFixed(0)}%`}
            color="var(--dim)"
          />
        </div>
      </div>

      {/* IS vs OOS comparison */}
      <div>
        <div
          style={{
            color: "var(--faint)",
            fontSize: 9,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          IS vs OOS comparison
        </div>
        <table
          style={{
            borderCollapse: "collapse",
            width: "auto",
            fontSize: 12,
            background: "var(--panel)",
            border: "1px solid var(--border)",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-l)" }}>
              {["Metric", "In-Sample", "Out-of-Sample"].map((h, i) => (
                <th
                  key={h}
                  style={{
                    padding: "5px 12px",
                    color: "var(--faint)",
                    fontWeight: 400,
                    textAlign: i === 0 ? "left" : "right",
                    fontSize: 10,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["Sharpe", iis.sharpe.toFixed(2), oos.sharpe.toFixed(2)],
                ["Sortino", iis.sortino.toFixed(2), oos.sortino.toFixed(2)],
                [
                  "CAGR",
                  `${(iis.cagr * 100).toFixed(1)}%`,
                  `${(oos.cagr * 100).toFixed(1)}%`,
                ],
                [
                  "Max DD",
                  `${(iis.maxDD * 100).toFixed(1)}%`,
                  `${(oos.maxDD * 100).toFixed(1)}%`,
                ],
                ["Calmar", iis.calmar.toFixed(2), oos.calmar.toFixed(2)],
              ] as [string, string, string][]
            ).map(([label, isVal, oosVal]) => (
              <tr
                key={label}
                style={{ borderBottom: "1px solid var(--border)" }}
              >
                <td style={{ padding: "4px 12px", color: "var(--dim)" }}>
                  {label}
                </td>
                <td
                  style={{
                    padding: "4px 12px",
                    color: "var(--text)",
                    textAlign: "right",
                  }}
                >
                  {isVal}
                </td>
                <td
                  style={{
                    padding: "4px 12px",
                    color: "var(--amber)",
                    textAlign: "right",
                  }}
                >
                  {oosVal}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Runs table */}
      <div>
        <div
          style={{
            color: "var(--faint)",
            fontSize: 9,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          All runs · use [ ] to cycle · click to select
        </div>
        <table
          style={{
            borderCollapse: "collapse",
            width: "100%",
            fontSize: 12,
            background: "var(--panel)",
            border: "1px solid var(--border)",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-l)" }}>
              {[
                "Name",
                "Strategy",
                "Sharpe",
                "CAGR",
                "MaxDD",
                "Trades",
                "Win%",
              ].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "5px 8px",
                    color: "var(--faint)",
                    fontWeight: 400,
                    textAlign:
                      h === "Name" || h === "Strategy" ? "left" : "right",
                    fontSize: 10,
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <RunRow key={r.id} r={r} active={r.id === run.id} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Run parameters */}
      <div>
        <div
          style={{
            color: "var(--faint)",
            fontSize: 9,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          Run parameters
        </div>
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            background: "var(--panel)",
            border: "1px solid var(--border)",
            padding: "10px 12px",
          }}
        >
          {Object.entries(run.params).map(([k, v]) => (
            <div key={k} style={{ marginRight: 16 }}>
              <span style={{ color: "var(--faint)", fontSize: 10 }}>{k}: </span>
              <span style={{ color: "var(--cyan)", fontSize: 11 }}>
                {Array.isArray(v) ? v.join(", ") : String(v)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Hotkey hint */}
      <div
        style={{
          color: "var(--faint)",
          fontSize: 10,
          borderTop: "1px solid var(--border)",
          paddingTop: 8,
        }}
      >
        Press <kbd>?</kbd> for shortcuts · <kbd>⌘K</kbd> for commands ·{" "}
        <kbd>1-9</kbd> switch views · <kbd>g</kbd> then letter for go-to
      </div>
    </div>
  );
}
