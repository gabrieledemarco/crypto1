"use client";

interface Props {
  grid: number[][];         // [row][col] → metric value (e.g. Sharpe)
  cellSize?: number;
  selected?: [number, number];
  onClick?: (cell: [number, number]) => void;
  xLabels?: string[];
  yLabels?: string[];
}

function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }

function cellColor(v: number, mn: number, mx: number): string {
  const t = mx === mn ? 0.5 : Math.max(0, Math.min(1, (v - mn) / (mx - mn)));
  if (t >= 0.5) {
    // green side
    const s = (t - 0.5) * 2;
    return `rgb(${Math.round(lerp(0x25, 0x6f, s))},${Math.round(lerp(0x27, 0xd1, s))},${Math.round(lerp(0x1a, 0x7a, s))})`;
  } else {
    // coral side
    const s = t * 2;
    return `rgb(${Math.round(lerp(0xff, 0x25, s))},${Math.round(lerp(0x7a, 0x27, s))},${Math.round(lerp(0x55, 0x1a, s))})`;
  }
}

export function HeatmapGrid({ grid, cellSize = 38, selected, onClick, xLabels, yLabels }: Props) {
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  const flat = grid.flat();
  const mn = Math.min(...flat);
  const mx = Math.max(...flat);

  return (
    <div style={{ display: "inline-block" }}>
      {/* X-axis labels */}
      {xLabels && (
        <div style={{ display: "flex", marginLeft: yLabels ? 32 : 0, marginBottom: 2 }}>
          {xLabels.map((l, i) => (
            <div key={i} style={{ width: cellSize, fontSize: 8, color: "var(--faint)",
              fontFamily: "var(--font-mono)", textAlign: "center", overflow: "hidden" }}>{l}</div>
          ))}
        </div>
      )}
      <div style={{ display: "flex" }}>
        {/* Y-axis labels */}
        {yLabels && (
          <div style={{ display: "flex", flexDirection: "column", marginRight: 2 }}>
            {yLabels.map((l, i) => (
              <div key={i} style={{ height: cellSize, fontSize: 8, color: "var(--faint)",
                fontFamily: "var(--font-mono)", display: "flex", alignItems: "center",
                justifyContent: "flex-end", paddingRight: 3, width: 28 }}>{l}</div>
            ))}
          </div>
        )}
        {/* Grid */}
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`, gap: 1 }}>
          {grid.map((row, r) =>
            row.map((v, c) => {
              const isSel = selected?.[0] === r && selected?.[1] === c;
              return (
                <div
                  key={`${r}-${c}`}
                  onClick={() => onClick?.([r, c])}
                  title={v.toFixed(3)}
                  style={{
                    width: cellSize, height: cellSize,
                    background: cellColor(v, mn, mx),
                    border: isSel ? "2px solid var(--cyan)" : "1px solid var(--border)",
                    cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 8, color: "rgba(255,255,255,0.7)",
                    fontFamily: "var(--font-mono)",
                    boxSizing: "border-box",
                  }}
                >
                  {v.toFixed(1)}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
