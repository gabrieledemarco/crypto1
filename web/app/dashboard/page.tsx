"use client";
import { useEffect } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import { TopBar } from "@/components/shell/TopBar";
import { Sidebar } from "@/components/shell/Sidebar";
import { StatusBar } from "@/components/shell/StatusBar";
import { Palette } from "@/components/shell/Palette";
import { HelpToast } from "@/components/shell/HelpToast";
import { Toast } from "@/components/shell/Toast";
import { DashboardScreen } from "@/components/screens/DashboardScreen";
import { EquityScreen } from "@/components/screens/EquityScreen";
import { TradesScreen } from "@/components/screens/TradesScreen";
import { useHotkeys } from "@/hooks/useHotkeys";
import type { ScreenId } from "@/store";

function ScreenContent({ screen }: { screen: ScreenId }) {
  switch (screen) {
    case "dashboard":
      return <DashboardScreen />;
    case "equity":
      return <EquityScreen />;
    case "trades":
      return <TradesScreen />;
    default:
      return (
        <div
          style={{
            padding: 24,
            color: "var(--dim)",
            fontFamily: "var(--font-mono)",
          }}
        >
          <div style={{ color: "var(--amber)", marginBottom: 8 }}>
            {screen.toUpperCase()}
          </div>
          <div>Coming in M4/M5</div>
        </div>
      );
  }
}

export default function DashboardPage() {
  const {
    runs,
    activeRunId,
    screen,
    paletteOpen,
    setPaletteOpen,
    toast,
    setRun,
  } = useStore();

  useEffect(() => {
    if (runs.length === 0) {
      useStore.getState().setRuns(fixtures.runs);
      useStore.getState().setRun(fixtures.activeRunId);
    }
  }, [runs.length]);

  useHotkeys();

  const run = runs.find((r) => r.id === activeRunId);

  return (
    <div className="app">
      <TopBar
        run={run}
        runs={runs}
        setRunId={setRun}
        screenLabel={screen.toUpperCase()}
        onOpenPalette={() => setPaletteOpen(true)}
      />
      <div className="body">
        <Sidebar />
        <main className="main">
          <ScreenContent screen={screen} />
        </main>
      </div>
      <StatusBar />
      {paletteOpen && <Palette />}
      <HelpToast />
      <Toast msg={toast} />
    </div>
  );
}
