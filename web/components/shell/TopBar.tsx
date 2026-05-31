"use client";
import type { Run } from "@/lib/fixtures";
import styles from "./TopBar.module.css";

interface RibbonStatProps {
  label: string;
  value: string;
  colorClass: string;
}

function RibbonStat({ label, value, colorClass }: RibbonStatProps) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={`${styles.statValue} ${colorClass}`}>{value}</span>
    </div>
  );
}

interface Props {
  run: Run | undefined;
  runs: Run[];
  setRunId: (id: string) => void;
  screenLabel: string;
  onOpenPalette: () => void;
}

export function TopBar({ run, runs, setRunId, screenLabel, onOpenPalette }: Props) {
  const cagr = run ? run.metricsOOS.cagr : 0;
  const maxDD = run ? run.metricsOOS.maxDD : 0;
  const sharpe = run ? run.metricsOOS.sharpe : 0;
  const winRate = run ? run.winRate : 0;
  const tradesCount = run ? run.tradesCount : 0;

  const cagrStr = `${cagr >= 0 ? "+" : ""}${(cagr * 100).toFixed(1)}%`;
  const ddStr = `${(maxDD * 100).toFixed(1)}%`;
  const sharpeStr = sharpe.toFixed(2);
  const wrStr = `${(winRate * 100).toFixed(0)}%`;
  const trStr = String(tradesCount);

  return (
    <header className={styles.topbar}>
      <div className={styles.brand}>
        <span className={styles.brandSquare}>■</span>
        <span className={styles.brandName}>PARETO</span>
        <span className={styles.brandSub}>backtest terminal</span>
      </div>

      <div className={styles.divider} />

      <select
        className={styles.runSelector}
        value={run?.id ?? ""}
        onChange={(e) => setRunId(e.target.value)}
        aria-label="Select active run"
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>

      <div className={styles.divider} />

      <span className={styles.screenLabel}>{screenLabel}</span>

      <div className={styles.ribbon}>
        <RibbonStat
          label="CAGR"
          value={cagrStr}
          colorClass={cagr >= 0 ? styles.green : styles.coral}
        />
        <RibbonStat label="MAXDD" value={ddStr} colorClass={styles.coral} />
        <RibbonStat label="SHARPE" value={sharpeStr} colorClass={styles.amber} />
        <RibbonStat label="WIN%" value={wrStr} colorClass={styles.amber} />
        <RibbonStat label="TRADES" value={trStr} colorClass={styles.amber} />
      </div>

      <button className={styles.paletteBtn} onClick={onOpenPalette}>
        ⌘K
      </button>
    </header>
  );
}
