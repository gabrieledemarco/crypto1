"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useStore, type ScreenId } from "@/store";
import styles from "./Palette.module.css";

interface PaletteAction {
  id: string;
  label: string;
  hint?: string;
  icon: string;
  group: string;
  action: () => void;
}

export function Palette() {
  const {
    paletteOpen,
    setPaletteOpen,
    goto,
    runs,
    setRun,
    setToast,
  } = useStore();

  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const showToast = useCallback(
    (msg: string) => {
      setToast(msg);
      setTimeout(() => setToast(null), 1800);
    },
    [setToast]
  );

  const close = useCallback(() => {
    setPaletteOpen(false);
    setQuery("");
    setActiveIdx(0);
  }, [setPaletteOpen]);

  const SCREEN_ACTIONS: { id: ScreenId; label: string; key: string }[] = [
    { id: "dashboard", label: "Dashboard", key: "1" },
    { id: "equity", label: "Equity Curve", key: "6" },
    { id: "trades", label: "Trades Table", key: "7" },
    { id: "sweep", label: "Param Sweep", key: "8" },
    { id: "underwater", label: "Underwater DD", key: "9" },
    { id: "mc", label: "Monte Carlo", key: "0" },
    { id: "assets", label: "Assets", key: "2" },
    { id: "library", label: "Library", key: "3" },
    { id: "vibe", label: "Vibe", key: "4" },
    { id: "setup", label: "Setup", key: "5" },
    { id: "compare", label: "Compare Runs", key: "C" },
  ];

  const actions: PaletteAction[] = [
    ...SCREEN_ACTIONS.map((s) => ({
      id: `goto-${s.id}`,
      label: `Go to ${s.label}`,
      hint: s.key,
      icon: "→",
      group: "Navigate",
      action: () => {
        goto(s.id);
        close();
      },
    })),
    ...runs.map((r) => ({
      id: `run-${r.id}`,
      label: `Load run: ${r.name}`,
      hint: r.strategy,
      icon: "◈",
      group: "Runs",
      action: () => {
        setRun(r.id);
        showToast(`Loaded ${r.name}`);
        close();
      },
    })),
    {
      id: "export",
      label: "Export results as JSON",
      icon: "↓",
      group: "Actions",
      action: () => {
        showToast("Export: not yet implemented");
        close();
      },
    },
    {
      id: "snapshot",
      label: "Save snapshot",
      icon: "◉",
      group: "Actions",
      action: () => {
        showToast("Snapshot saved");
        close();
      },
    },
    {
      id: "help",
      label: "Show keyboard shortcuts",
      hint: "?",
      icon: "?",
      group: "Help",
      action: () => {
        useStore.getState().setHelpOpen(true);
        close();
      },
    },
  ];

  const filtered = query
    ? actions.filter(
        (a) =>
          a.label.toLowerCase().includes(query.toLowerCase()) ||
          (a.hint?.toLowerCase().includes(query.toLowerCase()) ?? false) ||
          a.group.toLowerCase().includes(query.toLowerCase())
      )
    : actions;

  // Group filtered actions
  const groups = filtered.reduce<Record<string, PaletteAction[]>>((acc, a) => {
    if (!acc[a.group]) acc[a.group] = [];
    acc[a.group].push(a);
    return acc;
  }, {});

  const flatFiltered = filtered;

  useEffect(() => {
    if (paletteOpen) {
      setQuery("");
      setActiveIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [paletteOpen]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  if (!paletteOpen) return null;

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, flatFiltered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      flatFiltered[activeIdx]?.action();
    } else if (e.key === "Escape") {
      close();
    }
  };

  return (
    <div className={styles.overlay} onClick={close}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.inputRow}>
          <span className={styles.inputIcon}>⌘</span>
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Type a command or search..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKey}
          />
        </div>

        <div className={styles.list}>
          {Object.entries(groups).map(([groupName, items], gi) => (
            <div key={groupName}>
              {gi > 0 && <div className={styles.groupDivider} />}
              <div className={styles.groupLabel}>{groupName}</div>
              {items.map((item) => {
                const idx = flatFiltered.indexOf(item);
                return (
                  <button
                    key={item.id}
                    className={`${styles.listItem} ${idx === activeIdx ? styles.listItemActive : ""}`}
                    onClick={item.action}
                    onMouseEnter={() => setActiveIdx(idx)}
                  >
                    <span className={styles.listItemIcon}>{item.icon}</span>
                    <span className={styles.listItemLabel}>{item.label}</span>
                    {item.hint && (
                      <span className={styles.listItemHint}>{item.hint}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
          {flatFiltered.length === 0 && (
            <div className={styles.listItem} style={{ color: "var(--faint)" }}>
              No results for &quot;{query}&quot;
            </div>
          )}
        </div>

        <div className={styles.footer}>
          <span className={styles.footerHint}>
            <kbd>↑↓</kbd> navigate
          </span>
          <span className={styles.footerHint}>
            <kbd>↵</kbd> select
          </span>
          <span className={styles.footerHint}>
            <kbd>Esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
