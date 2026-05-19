"use client";
import { useStore, type ScreenId } from "@/store";
import styles from "./Sidebar.module.css";

interface NavItem {
  id: ScreenId;
  label: string;
  icon: string;
  key: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", icon: "◈", key: "1" },
      { id: "compare", label: "Compare", icon: "⇄", key: "C" },
    ],
  },
  {
    label: "Analysis",
    items: [
      { id: "equity", label: "Equity", icon: "↗", key: "6" },
      { id: "trades", label: "Trades", icon: "⊞", key: "7" },
      { id: "sweep", label: "Param Sweep", icon: "⊟", key: "8" },
      { id: "underwater", label: "Underwater", icon: "↓", key: "9" },
      { id: "mc", label: "Monte Carlo", icon: "⊙", key: "0" },
      { id: "wfo", label: "Walk-Forward", icon: "⇌", key: "g+w" },
    ],
  },
  {
    label: "Research",
    items: [
      { id: "assets", label: "Assets", icon: "◎", key: "2" },
      { id: "library", label: "Library", icon: "▤", key: "3" },
      { id: "vibe", label: "Vibe", icon: "✦", key: "4" },
    ],
  },
  {
    label: "Config",
    items: [{ id: "setup", label: "Setup", icon: "⚙", key: "5" }],
  },
];

export function Sidebar() {
  const { screen, goto } = useStore();

  return (
    <nav className={styles.sidebar}>
      {NAV_GROUPS.map((group, gi) => (
        <div key={group.label} className={styles.group}>
          {gi > 0 && <div className={styles.separator} />}
          <span className={styles.groupLabel}>{group.label}</span>
          {group.items.map((item) => (
            <button
              key={item.id}
              className={`${styles.item} ${screen === item.id ? styles.itemActive : ""}`}
              onClick={() => goto(item.id)}
            >
              <span className={styles.itemIcon}>{item.icon}</span>
              <span className={styles.itemLabel}>{item.label}</span>
              <span className={styles.itemKey}>{item.key}</span>
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}
