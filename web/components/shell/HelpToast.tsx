"use client";
import { useStore } from "@/store";
import styles from "./HelpToast.module.css";

interface HotkeyRow {
  keys: string[];
  desc: string;
}

interface HotkeySection {
  title: string;
  rows: HotkeyRow[];
}

const SECTIONS: HotkeySection[] = [
  {
    title: "Navigation",
    rows: [
      { keys: ["1-9", "0"], desc: "Switch view by number" },
      { keys: ["g", "d/a/l/..."], desc: "Go-to prefix + letter" },
      { keys: ["[", "]"], desc: "Cycle prev/next run" },
      { keys: ["⌘K"], desc: "Open command palette" },
      { keys: ["?"], desc: "Show this help" },
      { keys: ["Esc"], desc: "Close modal / blur input" },
    ],
  },
  {
    title: "Views",
    rows: [
      { keys: ["1"], desc: "Dashboard" },
      { keys: ["2"], desc: "Assets" },
      { keys: ["3"], desc: "Library" },
      { keys: ["4"], desc: "Vibe" },
      { keys: ["5"], desc: "Setup" },
      { keys: ["6"], desc: "Equity curve" },
    ],
  },
  {
    title: "More Views",
    rows: [
      { keys: ["7"], desc: "Trades table" },
      { keys: ["8"], desc: "Param sweep" },
      { keys: ["9"], desc: "Underwater DD" },
      { keys: ["0"], desc: "Monte Carlo" },
      { keys: ["g", "c"], desc: "Compare runs" },
      { keys: ["g", "v"], desc: "Vibe (AI)" },
    ],
  },
  {
    title: "Go-to shortcuts",
    rows: [
      { keys: ["g", "d"], desc: "Dashboard" },
      { keys: ["g", "a"], desc: "Assets" },
      { keys: ["g", "l"], desc: "Library" },
      { keys: ["g", "e"], desc: "Equity" },
      { keys: ["g", "t"], desc: "Trades" },
      { keys: ["g", "m"], desc: "Monte Carlo" },
    ],
  },
];

export function HelpToast() {
  const { helpOpen, setHelpOpen } = useStore();
  if (!helpOpen) return null;

  return (
    <div className={styles.overlay} onClick={() => setHelpOpen(false)}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.title}>
          <span>KEYBOARD SHORTCUTS</span>
          <button className={styles.closeBtn} onClick={() => setHelpOpen(false)}>
            Esc / close
          </button>
        </div>
        <div className={styles.grid}>
          {SECTIONS.map((section) => (
            <div key={section.title} className={styles.section}>
              <div className={styles.sectionTitle}>{section.title}</div>
              {section.rows.map((row, i) => (
                <div key={i} className={styles.row}>
                  <div className={styles.keyGroup}>
                    {row.keys.map((k, j) => (
                      <kbd key={j}>{k}</kbd>
                    ))}
                  </div>
                  <span className={styles.desc}>{row.desc}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className={styles.footer}>
          Press <kbd>?</kbd> or <kbd>Esc</kbd> to close
        </div>
      </div>
    </div>
  );
}
