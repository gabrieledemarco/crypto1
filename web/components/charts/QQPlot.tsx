"use client";
import { useEffect, useRef, useState } from "react";

interface Props {
  data: number[];
  height?: number;
  color?: string;
}

function normalInv(p: number): number {
  const a = 0.147;
  const ln1mx2 = Math.log(1 - (2 * p - 1) * (2 * p - 1));
  const t1 = 2 / (Math.PI * a) + ln1mx2 / 2;
  const t2 = ln1mx2 / a;
  const sign = p >= 0.5 ? 1 : -1;
  return sign * Math.sqrt(Math.sqrt(t1 * t1 - t2) - t1);
}

export function QQPlot({ data, height = 160, color = "#5cc1ff" }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);

  useEffect(() => {
    const ro = new ResizeObserver((es) => {
      if (es[0]) setWidth(es[0].contentRect.width);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const padT = 10, padR = 10, padB = 30, padL = 30;
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

  const n = data.length;
  const mean = data.reduce((a, b) => a + b, 0) / n;
  const variance = data.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
  const std = Math.sqrt(variance) || 1;
  const zScores = data.map((v) => (v - mean) / std);
  zScores.sort((a, b) => a - b);

  // Sample at most 200 points
  const maxPoints = 200;
  let indices: number[];
  if (n <= maxPoints) {
    indices = Array.from({ length: n }, (_, i) => i);
  } else {
    const step = (n - 1) / (maxPoints - 1);
    indices = Array.from({ length: maxPoints }, (_, i) => Math.round(i * step));
  }

  const points = indices.map((idx) => {
    // rank is 1-based in original sorted array
    const rank = idx + 1;
    const p = (rank - 0.375) / (n + 0.25);
    const theoretical = normalInv(Math.max(1e-9, Math.min(1 - 1e-9, p)));
    const sample = zScores[idx];
    return { theoretical, sample };
  });

  // Axis range
  const allTheoretical = points.map((p) => p.theoretical);
  const allSample = points.map((p) => p.sample);
  const minQ = Math.min(...allTheoretical);
  const maxQ = Math.max(...allTheoretical);
  const minS = Math.min(...allSample);
  const maxS = Math.max(...allSample);
  const xMin = minQ - 0.1, xMax = maxQ + 0.1;
  const yMin = minS - 0.1, yMax = maxS + 0.1;
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  const toX = (v: number) => padL + ((v - xMin) / xRange) * innerW;
  const toY = (v: number) => padT + ((yMax - v) / yRange) * innerH;

  // Reference 45° line from (minQ, minQ) to (maxQ, maxQ) — clamped to view
  const refLineMinVal = Math.max(xMin, yMin);
  const refLineMaxVal = Math.min(xMax, yMax);

  // Grid lines
  const xGridVals = [-3, -1, 1, 3];
  const yGridVals = [-3, -1, 1, 3];
  const xAxisLabels = [-3, -1, 1, 3];
  const yAxisLabels = [-3, -1, 1, 3];

  return (
    <div ref={wrapRef} style={{ width: "100%", height }}>
      <svg width={width} height={height} style={{ display: "block" }}>
        {/* Grid lines vertical */}
        {xGridVals.map((v) => (
          <line
            key={`gx-${v}`}
            x1={toX(v)} x2={toX(v)} y1={padT} y2={padT + innerH}
            stroke="#ffffff10" strokeWidth={0.8}
          />
        ))}
        {/* Grid lines horizontal */}
        {yGridVals.map((v) => (
          <line
            key={`gy-${v}`}
            x1={padL} x2={padL + innerW} y1={toY(v)} y2={toY(v)}
            stroke="#ffffff10" strokeWidth={0.8}
          />
        ))}
        {/* 45° reference line (dashed amber) */}
        {refLineMaxVal > refLineMinVal && (
          <line
            x1={toX(refLineMinVal)} y1={toY(refLineMinVal)}
            x2={toX(refLineMaxVal)} y2={toY(refLineMaxVal)}
            stroke="#ffb53b" strokeWidth={1} strokeDasharray="4 3"
          />
        )}
        {/* Data points */}
        {points.map((pt, i) => (
          <circle
            key={i}
            cx={toX(pt.theoretical)} cy={toY(pt.sample)}
            r={2} fill={color} opacity={0.75}
          />
        ))}
        {/* Axes */}
        <line x1={padL} x2={padL + innerW} y1={padT + innerH} y2={padT + innerH}
          stroke="#3a3c28" strokeWidth={0.8} />
        <line x1={padL} x2={padL} y1={padT} y2={padT + innerH}
          stroke="#3a3c28" strokeWidth={0.8} />
        {/* X axis labels */}
        {xAxisLabels.map((v) => (
          <text
            key={`xl-${v}`}
            x={toX(v)} y={height - 14}
            fill="var(--faint, #7e8163)" fontSize={9}
            fontFamily="var(--font-mono)" textAnchor="middle"
          >
            {v}
          </text>
        ))}
        {/* Y axis labels */}
        {yAxisLabels.map((v) => (
          <text
            key={`yl-${v}`}
            x={padL - 4} y={toY(v)}
            fill="var(--faint, #7e8163)" fontSize={9}
            fontFamily="var(--font-mono)" textAnchor="end" dominantBaseline="middle"
          >
            {v}
          </text>
        ))}
        {/* X axis title */}
        <text
          x={padL + innerW / 2} y={height - 2}
          fill="var(--faint, #7e8163)" fontSize={9}
          fontFamily="var(--font-mono)" textAnchor="middle"
        >
          THEORETICAL QUANTILE
        </text>
        {/* Y axis title (rotated) */}
        <text
          x={0} y={0}
          fill="var(--faint, #7e8163)" fontSize={9}
          fontFamily="var(--font-mono)" textAnchor="middle"
          transform={`translate(9, ${padT + innerH / 2}) rotate(-90)`}
        >
          SAMPLE QUANTILE
        </text>
      </svg>
    </div>
  );
}
