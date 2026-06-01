"use client";

interface DonutSlice {
  label: string;
  value: number;
  color: string;
}

interface Props {
  data: DonutSlice[];
  size?: number;
  strokeWidth?: number;
}

function polar(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polar(cx, cy, r, endAngle);
  const end = polar(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

export function DonutChart({ data, size = 172, strokeWidth = 18 }: Props) {
  const total = data.reduce((acc, d) => acc + Math.max(0, d.value), 0);
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  let cursor = 0;

  if (total <= 0) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: size, color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 10 }}>
        NO RUNS
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: `${size}px 1fr`, gap: 12, alignItems: "center" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Outcome distribution donut chart">
        <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--border)" strokeWidth={strokeWidth} />
        {data.map((slice) => {
          const start = cursor;
          const angle = (Math.max(0, slice.value) / total) * 360;
          const end = cursor + Math.min(angle, 359.99);
          cursor += angle;
          if (angle <= 0.01) return null;
          return (
            <path
              key={slice.label}
              d={arcPath(center, center, radius, start, end)}
              fill="none"
              stroke={slice.color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
            />
          );
        })}
        <text x={center} y={center - 3} textAnchor="middle" fill="var(--text)" fontFamily="JetBrains Mono, monospace" fontSize="20" fontWeight="700">
          {total}
        </text>
        <text x={center} y={center + 14} textAnchor="middle" fill="var(--faint)" fontFamily="JetBrains Mono, monospace" fontSize="9">
          RUNS
        </text>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {data.map((slice) => (
          <div key={slice.label} style={{ display: "grid", gridTemplateColumns: "10px 1fr auto", gap: 7, alignItems: "center" }}>
            <span style={{ width: 8, height: 8, background: slice.color, display: "inline-block" }} />
            <span style={{ color: "var(--dim)", fontFamily: "var(--font-mono)", fontSize: 10 }}>{slice.label}</span>
            <span style={{ color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 11 }}>{slice.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
