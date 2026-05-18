"use client";
import { useMemo, useRef, useEffect, useState } from "react";
import { useStore } from "@/store";
import { fixtures } from "@/lib/fixtures";
import styles from "./CompareScreen.module.css";
import type { Run } from "@/lib/fixtures";

const RUN_COLORS: Record<string, string> = {
  r1: "#ffb53b", r2: "#5cc1ff", r3: "#6fd17a", r4: "#ff7a55",
};
function colorFor(id: string, idx: number) {
  return RUN_COLORS[id] ?? ["#ffb53b","#5cc1ff","#6fd17a","#ff7a55"][idx % 4];
}

export function CompareScreen() {
  const { compareIds, toggleCompare, runs } = useStore();
  const allRuns = runs.length ? runs : fixtures.runs;
  const active = allRuns.filter((r) => compareIds.includes(r.id));

  const wrapRef = useRef<HTMLDivElement>(null);
  const [svgW, setSvgW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver((es) => { if (es[0]) setSvgW(es[0].contentRect.width); });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const H = 280, padL = 44, padR = 12, padT = 8, padB = 20;
  const innerW = Math.max(10, svgW - padL - padR);
  const innerH = H - padT - padB;

  const allV = active.flatMap((r) => r.equity.map((e) => e.v));
  const mn = allV.length ? Math.min(...allV) * 0.98 : 0;
  const mx = allV.length ? Math.max(...allV) * 1.02 : 2;

  const xy = (i: number, v: number, len: number) => [
    padL + (i / (len - 1)) * innerW,
    padT + innerH - ((v - mn) / (mx - mn || 1)) * innerH,
  ];

  function linePath(run: Run, idx: number) {
    const pts = run.equity.map((e, i) => xy(i, e.v, run.equity.length));
    const d = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    return <path key={run.id} d={d} fill="none" stroke={colorFor(run.id, idx)} strokeWidth={1.6} opacity={0.9} />;
  }

  // Grid lines
  const yTicks = [0.25, 0.5, 0.75, 1.0];

  // Pairwise correlations of equity returns
  const correlations = useMemo(() => {
    const ret = (r: Run) => r.equity.slice(1).map((e, i) => e.v / r.equity[i].v - 1);
    const corr = (a: number[], b: number[]) => {
      const n = Math.min(a.length, b.length);
      const ma = a.slice(0,n).reduce((s,x)=>s+x,0)/n;
      const mb = b.slice(0,n).reduce((s,x)=>s+x,0)/n;
      let num=0,da=0,db=0;
      for (let i=0;i<n;i++){num+=(a[i]-ma)*(b[i]-mb);da+=(a[i]-ma)**2;db+=(b[i]-mb)**2;}
      return da&&db ? num/Math.sqrt(da*db) : 0;
    };
    const out: {a:string;b:string;c:number}[] = [];
    for (let i=0;i<active.length;i++)
      for (let j=i+1;j<active.length;j++)
        out.push({a:active[i].name, b:active[j].name, c:corr(ret(active[i]),ret(active[j]))});
    return out;
  }, [active]);

  return (
    <div className={styles.wrapper}>
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span className={styles.panelTitle}>COMPARE</span>
          <span className={styles.panelSub}>{active.length} active</span>
        </div>
        <div className={styles.panelBody}>
          {/* Run chips */}
          <div className={styles.chips}>
            {allRuns.map((r, idx) => (
              <button key={r.id}
                className={`${styles.chip} ${compareIds.includes(r.id) ? styles.chipOn : ""}`}
                style={{ borderColor: colorFor(r.id, idx), color: compareIds.includes(r.id) ? colorFor(r.id, idx) : "var(--dim)" }}
                onClick={() => toggleCompare(r.id)}>
                <span className={styles.dot} style={{ background: colorFor(r.id, idx) }} />
                {r.name}
                <span className={styles.chipMeta}>· Sh {r.metricsOOS?.sharpe}</span>
              </button>
            ))}
          </div>

          {/* Equity overlay SVG */}
          <div ref={wrapRef} style={{ width: "100%", height: H }}>
            <svg width={svgW} height={H} style={{ display: "block" }}>
              {yTicks.map((q, i) => {
                const v = mn + (mx - mn) * q;
                const y = padT + innerH - q * innerH;
                return (
                  <g key={i}>
                    <line x1={padL} x2={padL+innerW} y1={y} y2={y}
                      stroke="#3a3c28" strokeDasharray="2 4" strokeWidth={0.8} />
                    <text x={padL-4} y={y+3} fill="#7e8163" fontSize={9}
                      textAnchor="end" fontFamily="JetBrains Mono,monospace">
                      {((v-1)*100).toFixed(0)}%
                    </text>
                  </g>
                );
              })}
              {active.map((r, idx) => linePath(r, idx))}
            </svg>
          </div>

          {/* Metrics table */}
          <div className={styles.table}>
            <div className={styles.thead} style={{ gridTemplateColumns: "1fr repeat(6, 80px)" }}>
              <span></span>
              <span>CAGR</span><span>SHARPE</span><span>SORTINO</span>
              <span>MAXDD</span><span>PF</span><span>TRADES</span>
            </div>
            {active.map((r, idx) => (
              <div key={r.id} className={styles.trow}
                style={{ gridTemplateColumns: "1fr repeat(6, 80px)" }}>
                <span style={{ color: colorFor(r.id, idx), fontWeight: 700 }}>{r.name}</span>
                <span style={{ color: "var(--green)" }}>+{r.metricsOOS?.cagr}%</span>
                <span>{r.metricsOOS?.sharpe}</span>
                <span>{r.metricsOOS?.sortino}</span>
                <span style={{ color: "var(--coral)" }}>{r.metricsOOS?.maxDD}%</span>
                <span>{r.profitFactor}</span>
                <span>{r.tradesCount}</span>
              </div>
            ))}
          </div>

          {/* Correlations */}
          {correlations.length > 0 && (
            <div className={styles.correlations}>
              <span className={styles.corrLabel}>CORRELAZIONI EQUITY:</span>
              {correlations.map((c, i) => (
                <span key={i} className={styles.corrItem}
                  style={{ color: Math.abs(c.c) < 0.4 ? "var(--green)" : "var(--amber)" }}>
                  {c.a.slice(0,10)} · {c.b.slice(0,10)} <b>{c.c.toFixed(2)}</b>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
