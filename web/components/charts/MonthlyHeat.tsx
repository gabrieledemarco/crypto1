"use client";
import { useState } from "react";
import styles from "./MonthlyHeat.module.css";

interface Bucket {
  idx: number;
  pnl: number;
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function cellColor(pnl: number, maxAbs: number): string {
  const t = Math.min(Math.abs(pnl) / Math.max(maxAbs, 0.01), 1);
  if (pnl >= 0) {
    const r = Math.round(lerp(0x16, 0x6f, t));
    const g = Math.round(lerp(0x17, 0xd1, t));
    const b = Math.round(lerp(0x0f, 0x7a, t));
    return `rgb(${r},${g},${b})`;
  } else {
    const r = Math.round(lerp(0x16, 0xff, t));
    const g = Math.round(lerp(0x17, 0x7a, t));
    const b = Math.round(lerp(0x0f, 0x55, t));
    return `rgb(${r},${g},${b})`;
  }
}

interface Props {
  monthly: Bucket[];
  cellSize?: number;
}

export function MonthlyHeat({ monthly, cellSize = 22 }: Props) {
  const [hov, setHov] = useState<number | null>(null);
  const maxAbs = Math.max(...monthly.map((m) => Math.abs(m.pnl)));

  return (
    <div className={styles.root}>
      <div
        className={styles.grid}
        style={{ gridTemplateColumns: `repeat(12, ${cellSize}px)` }}
      >
        {monthly.map((m) => (
          <div
            key={m.idx}
            className={styles.cell}
            style={{
              width: cellSize,
              height: cellSize,
              background: cellColor(m.pnl, maxAbs),
            }}
            onMouseEnter={() => setHov(m.idx)}
            onMouseLeave={() => setHov(null)}
          >
            {hov === m.idx && (
              <div className={styles.tooltip}>
                M{m.idx + 1}
                <br />
                <span
                  style={{
                    color: m.pnl >= 0 ? "var(--green)" : "var(--coral)",
                  }}
                >
                  {m.pnl >= 0 ? "+" : ""}
                  {m.pnl.toFixed(2)}%
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
