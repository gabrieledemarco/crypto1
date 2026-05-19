"use client";
import { useEffect, useRef, useState } from "react";

interface Props {
  data: number[];
  maxLag?: number;
  height?: number;
  color?: string;
}

function computeACF(x: number[], maxLag: number): number[] {
  const n = x.length;
  const mean = x.reduce((a, b) => a + b, 0) / n;
  const variance = x.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
  if (variance === 0) return new Array(maxLag).fill(0);
  const acf: number[] = [];
  for (let lag = 1; lag <= maxLag; lag++) {
    let cov = 0;
    for (let i = lag; i < n; i++) {
      cov += (x[i] - mean) * (x[i - lag] - mean);
    }
    acf.push(cov / (n * variance));
  }
  return acf;
}

export function ACFPlot({ data, maxLag = 30, height = 140, color = "#ffb53b" }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);

  useEffect(() => {
    const ro = new ResizeObserver((es) => {
      if (es[0]) setWidth(es[0].contentRect.width);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const padT = 10, padR = 10, padB = 30, padL = 35;
  const innerW = Math.max(10, width - padL - padR);
  const innerH = height - padT - padB;

  if (!data || data.length < 10) {
    return (
      <div ref={wrapRef} style={{ width: "100%", height }}>
        <svg width={width} height={height} style={{ display: "block" }}>
          <text
            x={width / 2} y={height / 2}
            fill="#444" fontSize={9}
            fontFamily="var(--font-mono)"
            textAnchor="middle" dominantBaseline="middle"
          >
            INSUFFICIENT DATA
          </text>
        </svg>
      </div>
    );
  }

  const effectiveLag = Math.min(maxLag, data.length - 1);
  const acf = computeACF(data, effectiveLag);
  const ci = 1.96 / Math.sqrt(data.length);

  // Y axis: range -1 to 1
  const yMin = -1, yMax = 1;
  const yRange = yMax - yMin;

  const toY = (v: number) => padT + ((yMax - v) / yRange) * innerH;

  // Bar geometry
  const barSlotW = innerW / effectiveLag;
  const barW = Math.max(3, barSlotW - 2);

  // Y axis label values
  const yLabels = [-0.5, 0, 0.5];

  return (
    <div ref={wrapRef} style={{ width: "100%", height }}>
      <svg width={width} height={height} style={{ display: "block" }}>
        {/* Zero line (solid amber) */}
        <line
          x1={padL} x2={padL + innerW}
          y1={toY(0)} y2={toY(0)}
          stroke="#ffb53b" strokeWidth={0.8}
        />
        {/* CI dashed lines (coral) */}
        <line
          x1={padL} x2={padL + innerW}
          y1={toY(ci)} y2={toY(ci)}
          stroke="#ff7a55" strokeWidth={1} strokeDasharray="4 3"
        />
        <line
          x1={padL} x2={padL + innerW}
          y1={toY(-ci)} y2={toY(-ci)}
          stroke="#ff7a55" strokeWidth={1} strokeDasharray="4 3"
        />
        {/* ACF bars */}
        {acf.map((val, i) => {
          const lag = i + 1;
          const cx = padL + (i + 0.5) * barSlotW;
          const x = cx - barW / 2;

          const y0 = toY(0);
          const yVal = toY(val);
          const barTop = Math.min(y0, yVal);
          const barHeight = Math.abs(yVal - y0);

          const outsideCI = Math.abs(val) > ci;
          let barColor: string;
          if (!outsideCI) {
            barColor = "#3a3c28"; // dim — inside CI
          } else if (val > 0) {
            barColor = color;
          } else {
            barColor = "#ff7a55"; // coral for negative outside CI
          }

          return (
            <rect
              key={lag}
              x={x} y={barTop}
              width={barW} height={Math.max(1, barHeight)}
              fill={barColor} opacity={0.85}
            />
          );
        })}
        {/* Axes */}
        <line x1={padL} x2={padL + innerW} y1={padT + innerH} y2={padT + innerH}
          stroke="#3a3c28" strokeWidth={0.8} />
        <line x1={padL} x2={padL} y1={padT} y2={padT + innerH}
          stroke="#3a3c28" strokeWidth={0.8} />
        {/* X axis labels — every 5th lag */}
        {Array.from({ length: Math.floor(effectiveLag / 5) }, (_, i) => (i + 1) * 5).map((lag) => (
          <text
            key={`xl-${lag}`}
            x={padL + (lag - 0.5) * barSlotW}
            y={height - 14}
            fill="var(--faint, #7e8163)" fontSize={9}
            fontFamily="var(--font-mono)" textAnchor="middle"
          >
            {lag}
          </text>
        ))}
        {/* X axis title */}
        <text
          x={padL + innerW / 2} y={height - 2}
          fill="var(--faint, #7e8163)" fontSize={9}
          fontFamily="var(--font-mono)" textAnchor="middle"
        >
          LAG
        </text>
        {/* Y axis labels */}
        {yLabels.map((v) => (
          <text
            key={`yl-${v}`}
            x={padL - 4} y={toY(v)}
            fill="var(--faint, #7e8163)" fontSize={9}
            fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle"
          >
            {v.toFixed(1)}
          </text>
        ))}
      </svg>
    </div>
  );
}
