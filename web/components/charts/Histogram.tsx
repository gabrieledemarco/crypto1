"use client";
import { useEffect, useRef, useState } from "react";

interface Props {
  data: number[];
  bins?: number;
  height?: number;
  color?: string;
  fmt?: (v: number) => string;
}

export function Histogram({ data, bins = 30, height = 150, color = "#ffb53b", fmt }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);

  useEffect(() => {
    const ro = new ResizeObserver((es) => { if (es[0]) setWidth(es[0].contentRect.width); });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  if (!data || data.length === 0) return <div ref={wrapRef} style={{ height }} />;

  const mn = Math.min(...data), mx = Math.max(...data);
  const range = mx - mn || 1;
  const binW = range / bins;
  const counts = Array(bins).fill(0);
  data.forEach((v) => {
    const i = Math.min(bins - 1, Math.floor((v - mn) / binW));
    counts[i]++;
  });
  const maxCount = Math.max(...counts);

  const padL = 8, padR = 8, padT = 8, padB = 20;
  const innerW = Math.max(10, width - padL - padR);
  const innerH = height - padT - padB;
  const bw = innerW / bins;

  // 3 x-axis labels
  const xLabels = [mn, mn + range / 2, mx].map((v) => fmt ? fmt(v) : v.toFixed(1));

  return (
    <div ref={wrapRef} style={{ width: "100%", height }}>
      <svg width={width} height={height} style={{ display: "block" }}>
        {counts.map((c, i) => {
          const bh = maxCount > 0 ? (c / maxCount) * innerH : 0;
          const x = padL + i * bw;
          const y = padT + innerH - bh;
          const isPositive = mn + (i + 0.5) * binW >= 0;
          return (
            <rect key={i}
              x={x + 0.5} y={y} width={Math.max(1, bw - 1)} height={bh}
              fill={isPositive ? "#6fd17a" : color}
              opacity={0.8}
            />
          );
        })}
        {/* Baseline */}
        <line x1={padL} x2={padL + innerW} y1={padT + innerH} y2={padT + innerH}
          stroke="#3a3c28" strokeWidth={0.8} />
        {/* Zero line if range spans 0 */}
        {mn < 0 && mx > 0 && (
          <line
            x1={padL + ((-mn) / range) * innerW}
            x2={padL + ((-mn) / range) * innerW}
            y1={padT} y2={padT + innerH}
            stroke="#5a5d3a" strokeDasharray="3 3" strokeWidth={0.8}
          />
        )}
        {/* X labels */}
        {xLabels.map((l, i) => (
          <text key={i}
            x={padL + (i / 2) * innerW} y={height - 4}
            fill="#7e8163" fontSize={9} fontFamily="JetBrains Mono,monospace"
            textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>
            {l}
          </text>
        ))}
      </svg>
    </div>
  );
}
