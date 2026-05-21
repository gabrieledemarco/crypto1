import { create } from "zustand";
import type { Run } from "@/lib/fixtures";

export type ScreenId =
  | "dashboard"
  | "assets"
  | "library"
  | "vibe"
  | "setup"
  | "equity"
  | "trades"
  | "sweep"
  | "underwater"
  | "mc"
  | "compare"
  | "wfo"
  | "analysis";

export interface SetupParams {
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
  wfo_is_window?: number;
  wfo_oos_window?: number;
  mc_sims?: number;
  mc_bars?: number;
}

interface Store {
  runs: Run[];
  activeRunId: string;
  activeStrategyId: string | null;
  pendingSetupParams: SetupParams | null;
  screen: ScreenId;
  paletteOpen: boolean;
  helpOpen: boolean;
  compareIds: string[];
  gPrefix: boolean;
  toast: string | null;
  setRuns: (runs: Run[]) => void;
  setRun: (id: string) => void;
  setActiveStrategy: (id: string | null) => void;
  setPendingSetupParams: (p: SetupParams | null) => void;
  loadRunFromHistory: (run: Run) => void;
  goto: (screen: ScreenId) => void;
  setPaletteOpen: (open: boolean) => void;
  setHelpOpen: (open: boolean) => void;
  setGPrefix: (v: boolean) => void;
  setToast: (msg: string | null) => void;
  toggleCompare: (id: string) => void;
}

export const useStore = create<Store>((set) => ({
  runs: [],
  activeRunId: "",
  activeStrategyId: null,
  pendingSetupParams: null,
  screen: "dashboard",
  paletteOpen: false,
  helpOpen: false,
  compareIds: [],
  gPrefix: false,
  toast: null,
  setRuns: (runs) => set({ runs }),
  setRun: (id) => set({ activeRunId: id }),
  setActiveStrategy: (id) => set({ activeStrategyId: id }),
  setPendingSetupParams: (p) => set({ pendingSetupParams: p }),
  loadRunFromHistory: (run) =>
    set((s) => ({
      activeRunId: run.id,
      runs: s.runs.some((r) => r.id === run.id)
        ? s.runs.map((r) => (r.id === run.id ? run : r))
        : [...s.runs, run],
    })),
  goto: (screen) => set({ screen }),
  setPaletteOpen: (open) => set({ paletteOpen: open }),
  setHelpOpen: (open) => set({ helpOpen: open }),
  setGPrefix: (v) => set({ gPrefix: v }),
  setToast: (toast) => set({ toast }),
  toggleCompare: (id) =>
    set((s) => ({
      compareIds: s.compareIds.includes(id)
        ? s.compareIds.filter((x) => x !== id)
        : [...s.compareIds, id],
    })),
}));
