"use client";
import { useEffect, useCallback } from "react";
import { useStore, type ScreenId } from "@/store";

const SCREEN_LETTERS: Record<string, ScreenId> = {
  d: "dashboard",
  a: "assets",
  l: "library",
  v: "vibe",
  s: "setup",
  e: "equity",
  t: "trades",
  p: "sweep",
  u: "underwater",
  m: "mc",
  c: "compare",
};
const SCREEN_NUMS: Record<number, ScreenId> = {
  1: "dashboard",
  2: "assets",
  3: "library",
  4: "vibe",
  5: "setup",
  6: "equity",
  7: "trades",
  8: "sweep",
  9: "underwater",
  0: "mc",
};

export function useHotkeys() {
  const {
    goto,
    paletteOpen,
    setPaletteOpen,
    setHelpOpen,
    gPrefix,
    setGPrefix,
    runs,
    activeRunId,
    setRun,
    setToast,
  } = useStore();

  const showToast = useCallback(
    (msg: string) => {
      setToast(msg);
      setTimeout(() => setToast(null), 1800);
    },
    [setToast]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (document.activeElement as HTMLElement)?.tagName;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
        if (e.key === "Escape") (document.activeElement as HTMLElement).blur();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }
      if (e.key === "Escape") {
        setPaletteOpen(false);
        setHelpOpen(false);
        return;
      }
      if (paletteOpen) return;
      if (e.key === "?") {
        setHelpOpen(true);
        return;
      }
      if (e.key === "g") {
        setGPrefix(true);
        setTimeout(() => setGPrefix(false), 1200);
        return;
      }
      if (gPrefix) {
        const target = SCREEN_LETTERS[e.key.toLowerCase()];
        if (target) {
          goto(target);
          setGPrefix(false);
          showToast(`→ ${target.toUpperCase()}`);
          return;
        }
      }
      const num = parseInt(e.key, 10);
      if (!isNaN(num) && SCREEN_NUMS[num]) {
        goto(SCREEN_NUMS[num]);
        return;
      }
      if (e.key === "[") {
        const i = runs.findIndex((r) => r.id === activeRunId);
        const next = runs[(i - 1 + runs.length) % runs.length];
        if (next) setRun(next.id);
      } else if (e.key === "]") {
        const i = runs.findIndex((r) => r.id === activeRunId);
        const next = runs[(i + 1) % runs.length];
        if (next) setRun(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    gPrefix,
    paletteOpen,
    runs,
    activeRunId,
    goto,
    setPaletteOpen,
    setHelpOpen,
    setGPrefix,
    setRun,
    showToast,
  ]);
}
