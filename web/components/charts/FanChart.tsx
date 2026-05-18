"use client";
import { useEffect, useRef, useState } from "react";

interface MCData {
  percentiles: { p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };
  paths?: number[][];
}

interface Props {
  mc: MCData;
  height?: number;
  color?: string;
}

export function FanChart({ mc, height = 280, color = "#ffb53b" }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);

  useEffect(() => {
    const ro = new ResizeObserver((es) => {
      if (es[0]) setWidth(es[0].contentRect.width);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const { p5, p25, p50, p75, p95 } = mc.percentiles;
  const steps = p50.length;
  if (steps < 2) return null;

  const padL = 44, padR = 12, padT = 12, padB = 20;
  const innerW = Math.max(10, width - padL - padR);
  const innerH = height - padT - padB;

  // All values for y-scale
  const allV = [...p5, ...p95];
  const mn = Math.min(...allV) * 0.98;
  const mx = Math.max(...allV) * 1.02;

  const xOf = (i: number) => padL + (i / (steps - 1)) * innerW;
  const yOf = (v: number) => padT + innerH - ((v - mn) / (mx - mn)) * innerH;

  // Build SVG path from array of values
  const line = (arr: number[]) =>
    arr.map((v, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");

  // Build closed band path (top array forward, bottom array backward)
  const band = (top: number[], bot: number[]) => {
    const fwd = top.map((v, i) => `${i === 0 ? "M" : "L"}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
    const rev = [...bot].reverse().map((v, i) => `L${xOf(bot.length - 1 - i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
    return `${fwd} ${rev} Z`;
  };

  // Y-axis gridlines
  const yTicks = 4;
  const gridLines = Array.from({ length: yTicks + 1 }, (_, i) => {
    const v = mn + (mx - mn) * (i / yTicks);
    const y = yOf(v);
    const label = ((v - 1) * 100).toFixed(0) + "%";
    return { y, label };
  });

  // Baseline (initial capital = 1.0)
  const baseY = yOf(1.0);

  return (
    <div ref={wrapRef} style={{ width: "100%", height }}>
      <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
        {/* Grid */}
        {gridLines.map((g, i) => (
          <g key={i}>
            <line x1={padL} x2={padL + innerW} y1={g.y} y2={g.y}
              stroke="#3a3c28" strokeDasharray="2 4" strokeWidth={0.8} />
            <text x={padL - 4} y={g.y + 3} fill="#7e8163" fontSize={9}
              textAnchor="end" fontFamily="JetBrains Mono,monospace">{g.label}</text>
          </g>
        ))}

        {/* Baseline */}
        <line x1={padL} x2={padL + innerW} y1={baseY} y2={baseY}
          stroke="#5a5d3a" strokeDasharray="4 4" strokeWidth={0.8} />

        {/* Bands */}
        <path d={band(p95, p5)} fill={color + "1a"} />
        <path d={band(p75, p25)} fill={color + "33"} />

        {/* Median */}
        <path d={line(p50)} fill="none" stroke={color} strokeWidth={2} />

        {/* p5 / p95 edges */}
        <path d={line(p5)}  fill="none" stroke={color + "66"} strokeWidth={1} />
        <path d={line(p95)} fill="none" stroke={color + "66"} strokeWidth={1} />
      </svg>
    </div>
  );
}
