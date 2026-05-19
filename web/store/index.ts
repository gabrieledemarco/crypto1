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

interface Store {
  runs: Run[];
  activeRunId: string;
  screen: ScreenId;
  paletteOpen: boolean;
  helpOpen: boolean;
  compareIds: string[];
  gPrefix: boolean;
  toast: string | null;
  setRuns: (runs: Run[]) => void;
  setRun: (id: string) => void;
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
  screen: "dashboard",
  paletteOpen: false,
  helpOpen: false,
  compareIds: [],
  gPrefix: false,
  toast: null,
  setRuns: (runs) => set({ runs }),
  setRun: (id) => set({ activeRunId: id }),
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
