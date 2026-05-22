/* PARETO — chart primitives */
const { useState, useRef, useEffect, useMemo, useCallback } = React;

// Color tokens (terminal palette)
const C = {
  bg: "#0c0d0a",
  panel: "#16170f",
  panel2: "#1d1f15",
  border: "#3a3c28",
  borderL: "#5a5d3a",
  text: "#d8dac2",
  dim: "#a3a78c",
  faint: "#7e8163",
  amber: "#ffb53b",
  amberD: "#d18f1f",
  coral: "#ff7a55",
  green: "#6fd17a",
  cyan: "#5cc1ff",
  yellow: "#ffd84a",
  red: "#ff5a48"
};

window.PARETO_C = C;

function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

function lineFromPoints(pts) {
  if (!pts.length) return "";
  return "M" + pts.map(p => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" L");
}

function EquityChart({ equity, oosStart, height = 200, showBench = true, log = false, showCrosshair = true, color = C.amber, onHover }) {
  const wrap = useRef(null);
  const [hover, setHover] = useState(null);
  const [w, setW] = useState(800);

  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const h = height;
  const padL = 44, padR = 12, padT = 8, padB = 18;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = h - padT - padB;

  const transformY = useCallback((v, min, max) => {
    if (log) {
      const lv = Math.log(Math.max(1e-6, v));
      const lmn = Math.log(Math.max(1e-6, min));
      const lmx = Math.log(Math.max(1e-6, max));
      return padT + innerH - ((lv - lmn) / (lmx - lmn)) * innerH;
    }
    return padT + innerH - ((v - min) / (max - min)) * innerH;
  }, [log, innerH]);

  const { min, max, pts, bpts } = useMemo(() => {
    const vs = equity.map(e => e.v);
    const bs = equity.map(e => e.bench);
    const all = showBench ? vs.concat(bs) : vs;
    let mn = Math.min(...all), mx = Math.max(...all);
    const pad = (mx - mn) * 0.08;
    mn = mn - pad; mx = mx + pad;
    const xStep = innerW / (equity.length - 1);
    const pts = equity.map((e, i) => [padL + i * xStep, 0]); // y set below
    const bpts = equity.map((e, i) => [padL + i * xStep, 0]);
    equity.forEach((e, i) => {
      pts[i][1] = transformY(e.v, mn, mx);
      bpts[i][1] = transformY(e.bench, mn, mx);
    });
    return { min: mn, max: mx, pts, bpts };
  }, [equity, showBench, transformY, innerW]);

  const oosX = oosStart != null ? padL + (oosStart / (equity.length - 1)) * innerW : null;

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const i = clamp(Math.round((x - padL) / (innerW / (equity.length - 1))), 0, equity.length - 1);
    const pt = pts[i];
    const bpt = bpts[i];
    const point = equity[i];
    setHover({ i, x: pt[0], y: pt[1], bx: bpt[0], by: bpt[1], point });
    onHover && onHover(i, point);
  };
  const handleLeave = () => { setHover(null); onHover && onHover(null, null); };

  // y-axis ticks
  const ticks = useMemo(() => {
    const arr = [];
    for (let q = 0; q <= 4; q++) {
      const t = min + (max - min) * (q / 4);
      arr.push({ y: transformY(t, min, max), label: ((t - 1) * 100).toFixed(0) + "%" });
    }
    return arr;
  }, [min, max, transformY]);

  return (
    <div ref={wrap} className="chart-wrap" style={{ position: "relative", width: "100%", height: h }}>
      <svg width={w} height={h} onMouseMove={handleMove} onMouseLeave={handleLeave}
        style={{ display: "block", cursor: showCrosshair ? "crosshair" : "default" }}>
        {/* OOS shading */}
        {oosX != null && (
          <rect x={oosX} y={padT} width={padL + innerW - oosX} height={innerH} fill={C.amber} opacity="0.05" />
        )}
        {/* grid */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={padL + innerW} y1={t.y} y2={t.y} stroke={C.border} strokeDasharray="2 4" />
            <text x={padL - 6} y={t.y + 3} fill={C.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{t.label}</text>
          </g>
        ))}
        {/* OOS label */}
        {oosX != null && (
          <text x={oosX + 6} y={padT + 12} fill={C.amber} fontSize="10" fontFamily="JetBrains Mono" fontWeight="700">OOS</text>
        )}
        {/* benchmark */}
        {showBench && (
          <path d={lineFromPoints(bpts)} fill="none" stroke={C.dim} strokeWidth="1.2" strokeDasharray="4 4" opacity="0.8" />
        )}
        {/* equity line */}
        <path d={lineFromPoints(pts)} fill="none" stroke={color} strokeWidth="1.8" />
        {/* crosshair */}
        {hover && showCrosshair && (
          <g pointerEvents="none">
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + innerH} stroke={C.borderL} strokeDasharray="3 3" />
            <line x1={padL} x2={padL + innerW} y1={hover.y} y2={hover.y} stroke={C.borderL} strokeDasharray="3 3" />
            <circle cx={hover.x} cy={hover.y} r="3" fill={color} stroke={C.bg} strokeWidth="1.5" />
            {showBench && <circle cx={hover.bx} cy={hover.by} r="2.5" fill={C.dim} stroke={C.bg} strokeWidth="1.2" />}
          </g>
        )}
      </svg>
      {hover && (
        <div className="crosshair-tip" style={{
          position: "absolute", left: clamp(hover.x + 10, 8, w - 180), top: clamp(hover.y - 50, 8, h - 70),
          background: C.panel2, border: `1px solid ${C.borderL}`, padding: "6px 8px",
          font: "11px JetBrains Mono", color: C.text, pointerEvents: "none", lineHeight: 1.4, whiteSpace: "nowrap"
        }}>
          <div style={{ color: C.faint }}>t = {hover.i}{hover.point.oos ? " · OOS" : " · IS"}</div>
          <div style={{ color }}>strat&nbsp;&nbsp;<b>{((hover.point.v - 1) * 100).toFixed(2)}%</b></div>
          {showBench && <div style={{ color: C.dim }}>bench&nbsp;<b>{((hover.point.bench - 1) * 100).toFixed(2)}%</b></div>}
          <div style={{ color: hover.point.dd < -0.01 ? C.coral : C.faint }}>dd&nbsp;&nbsp;&nbsp;&nbsp;<b>{(hover.point.dd * 100).toFixed(2)}%</b></div>
        </div>
      )}
    </div>
  );
}

function DrawdownChart({ equity, height = 80, sharedHover = null, onHover, color = C.coral }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const h = height;
  const padL = 44, padR = 12, padT = 6, padB = 14;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = h - padT - padB;
  const minDD = Math.min(...equity.map(e => e.dd));
  const pts = equity.map((e, i) => {
    const x = padL + (i / (equity.length - 1)) * innerW;
    const y = padT + (Math.abs(e.dd) / Math.abs(minDD || 1)) * innerH;
    return [x, y];
  });
  const areaPath = "M" + pts[0][0] + "," + padT + " L" +
    pts.map(p => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" L") +
    ` L${pts[pts.length - 1][0]},${padT} Z`;

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const i = clamp(Math.round((x - padL) / (innerW / (equity.length - 1))), 0, equity.length - 1);
    setHover({ i, x: pts[i][0], y: pts[i][1], v: equity[i].dd });
    onHover && onHover(i, equity[i]);
  };
  const handleLeave = () => { setHover(null); onHover && onHover(null, null); };

  const sharedX = sharedHover != null ? padL + (sharedHover / (equity.length - 1)) * innerW : null;

  return (
    <div ref={wrap} style={{ position: "relative", width: "100%", height: h }}>
      <svg width={w} height={h} onMouseMove={handleMove} onMouseLeave={handleLeave}
        style={{ display: "block", cursor: "crosshair" }}>
        <line x1={padL} x2={padL + innerW} y1={padT} y2={padT} stroke={C.border} />
        <text x={padL - 6} y={padT + 4} fill={C.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">0%</text>
        <text x={padL - 6} y={padT + innerH} fill={C.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{(minDD * 100).toFixed(0)}%</text>
        <path d={areaPath} fill={color} fillOpacity="0.18" />
        <path d={lineFromPoints(pts)} fill="none" stroke={color} strokeWidth="1.5" />
        {sharedX != null && (
          <line x1={sharedX} x2={sharedX} y1={padT} y2={padT + innerH} stroke={C.borderL} strokeDasharray="3 3" pointerEvents="none" />
        )}
        {hover && (
          <g pointerEvents="none">
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + innerH} stroke={C.borderL} strokeDasharray="3 3" />
            <circle cx={hover.x} cy={hover.y} r="2.5" fill={color} stroke={C.bg} strokeWidth="1.2" />
          </g>
        )}
      </svg>
    </div>
  );
}

function HeatmapGrid({ grid, cellSize, onHover, onClick, selected, palette = "perf", labelsX, labelsY, label }) {
  const [hov, setHov] = useState(null);
  const flat = grid.flat();
  const min = Math.min(...flat), max = Math.max(...flat);
  const colorFor = (v) => {
    if (palette === "perf") {
      const t = (v - min) / (max - min || 1);
      if (v < 0) {
        const a = Math.min(1, Math.abs(v) / Math.max(0.5, Math.abs(min)));
        return `rgba(255, 122, 85, ${0.18 + a * 0.7})`;
      }
      return `rgba(255, 181, 59, ${0.18 + t * 0.75})`;
    }
    return C.amber;
  };
  return (
    <div style={{ position: "relative" }}>
      <div style={{
        display: "grid",
        gridTemplateColumns: `repeat(${grid[0].length}, ${cellSize}px)`,
        gap: 2, padding: 2, background: C.border,
        border: `1px solid ${C.border}`, width: "fit-content"
      }}>
        {grid.map((row, r) => row.map((v, c) => {
          const isSel = selected && selected[0] === r && selected[1] === c;
          return (
            <div key={`${r}-${c}`}
              onMouseEnter={() => { setHov([r, c, v]); onHover && onHover([r, c, v]); }}
              onMouseLeave={() => { setHov(null); onHover && onHover(null); }}
              onClick={() => onClick && onClick([r, c, v])}
              style={{
                width: cellSize, height: cellSize,
                background: colorFor(v),
                outline: isSel ? `2px solid ${C.cyan}` : "none",
                outlineOffset: -2,
                cursor: "pointer", position: "relative",
                transition: "transform .08s ease"
              }} />
          );
        }))}
      </div>
      {hov && (
        <div style={{
          position: "absolute",
          left: 8 + hov[1] * (cellSize + 2),
          top: -34 + hov[0] * (cellSize + 2),
          background: C.panel2, border: `1px solid ${C.borderL}`,
          padding: "3px 6px", font: "10px JetBrains Mono",
          color: C.amber, pointerEvents: "none", zIndex: 5
        }}>
          {label || "v"} {hov[2].toFixed(2)} · [{hov[0]},{hov[1]}]
        </div>
      )}
    </div>
  );
}

function FanChart({ mc, height = 200, color = C.amber }) {
  const wrap = useRef(null);
  const [w, setW] = useState(800);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const h = height;
  const padL = 44, padR = 12, padT = 10, padB = 18;
  const innerW = Math.max(50, w - padL - padR);
  const innerH = h - padT - padB;
  const all = [].concat(mc.percentiles.p5, mc.percentiles.p95);
  const mn = Math.min(...all) * 0.98;
  const mx = Math.max(...all) * 1.02;
  const xy = (i, v, len) => [padL + (i / (len - 1)) * innerW, padT + innerH - ((v - mn) / (mx - mn)) * innerH];
  const band = (lo, hi) => {
    const len = lo.length;
    const top = lo.map((v, i) => xy(i, v, len));
    const bot = hi.map((v, i) => xy(i, v, len));
    return "M" + top.map(p => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" L") +
      " L" + bot.slice().reverse().map(p => `${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(" L") + " Z";
  };
  const linePts = (arr) => arr.map((v, i) => xy(i, v, arr.length));

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const i = clamp(Math.round((x - padL) / (innerW / (mc.percentiles.p50.length - 1))), 0, mc.percentiles.p50.length - 1);
    setHover({ i, x: padL + (i / (mc.percentiles.p50.length - 1)) * innerW });
  };

  return (
    <div ref={wrap} style={{ position: "relative", width: "100%", height: h }}>
      <svg width={w} height={h} onMouseMove={handleMove} onMouseLeave={() => setHover(null)}
        style={{ display: "block", cursor: "crosshair" }}>
        {[0.25, 0.5, 0.75, 1].map((q, i) => {
          const v = mn + (mx - mn) * q;
          const y = padT + innerH - q * innerH;
          return (
            <g key={i}>
              <line x1={padL} x2={padL + innerW} y1={y} y2={y} stroke={C.border} strokeDasharray="2 4" />
              <text x={padL - 6} y={y + 3} fill={C.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{((v - 1) * 100).toFixed(0)}%</text>
            </g>
          );
        })}
        <path d={band(mc.percentiles.p5, mc.percentiles.p95)} fill={color} fillOpacity="0.12" />
        <path d={band(mc.percentiles.p25, mc.percentiles.p75)} fill={color} fillOpacity="0.22" />
        <path d={lineFromPoints(linePts(mc.percentiles.p50))} fill="none" stroke={color} strokeWidth="1.8" />
        {/* a couple of sample paths for texture */}
        {mc.paths.slice(0, 18).map((p, i) => (
          <path key={i} d={lineFromPoints(linePts(p))} fill="none" stroke={color} strokeWidth="0.6" opacity="0.15" />
        ))}
        {hover && (
          <g pointerEvents="none">
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + innerH} stroke={C.borderL} strokeDasharray="3 3" />
            {[
              { v: mc.percentiles.p95[hover.i], lbl: "p95", c: color, op: 0.5 },
              { v: mc.percentiles.p50[hover.i], lbl: "p50", c: color, op: 1 },
              { v: mc.percentiles.p5[hover.i], lbl: "p5", c: color, op: 0.5 }
            ].map((s, i) => {
              const y = xy(hover.i, s.v, mc.percentiles.p50.length)[1];
              return <circle key={i} cx={hover.x} cy={y} r="2.5" fill={s.c} opacity={s.op} stroke={C.bg} strokeWidth="1" />;
            })}
          </g>
        )}
      </svg>
      {hover && (
        <div style={{
          position: "absolute", left: clamp(hover.x + 10, 8, w - 130), top: padT + 8,
          background: C.panel2, border: `1px solid ${C.borderL}`,
          padding: "4px 8px", font: "11px JetBrains Mono", color: C.text, pointerEvents: "none", lineHeight: 1.4
        }}>
          <div style={{ color: C.faint }}>t = {hover.i}</div>
          <div>p95 <b style={{ color: C.amber }}>{((mc.percentiles.p95[hover.i] - 1) * 100).toFixed(1)}%</b></div>
          <div>p50 <b style={{ color: C.amber }}>{((mc.percentiles.p50[hover.i] - 1) * 100).toFixed(1)}%</b></div>
          <div>p5&nbsp; <b style={{ color: C.amber }}>{((mc.percentiles.p5[hover.i] - 1) * 100).toFixed(1)}%</b></div>
        </div>
      )}
    </div>
  );
}

function Histogram({ data, height = 100, bins = 24, color = C.amber, fmt = (v) => v.toFixed(2), domain }) {
  const wrap = useRef(null);
  const [w, setW] = useState(400);
  useEffect(() => {
    const ro = new ResizeObserver(es => { if (es[0]) setW(es[0].contentRect.width); });
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const h = height;
  const padL = 6, padR = 6, padT = 6, padB = 14;
  const innerW = Math.max(40, w - padL - padR);
  const innerH = h - padT - padB;
  const [mn, mx] = domain || [Math.min(...data), Math.max(...data)];
  const buckets = new Array(bins).fill(0);
  data.forEach(v => {
    const t = clamp(Math.floor(((v - mn) / (mx - mn || 1)) * bins), 0, bins - 1);
    buckets[t]++;
  });
  const maxC = Math.max(...buckets);
  const bw = innerW / bins;
  return (
    <div ref={wrap} style={{ width: "100%", height: h }}>
      <svg width={w} height={h} style={{ display: "block" }}>
        {buckets.map((c, i) => {
          const bh = (c / maxC) * innerH;
          return <rect key={i} x={padL + i * bw + 0.5} y={padT + innerH - bh}
            width={bw - 1} height={bh} fill={color} opacity={0.4 + (c / maxC) * 0.6} />;
        })}
        <text x={padL} y={h - 2} fill={C.faint} fontSize="9.5" fontFamily="JetBrains Mono">{fmt(mn)}</text>
        <text x={padL + innerW} y={h - 2} fill={C.faint} fontSize="9.5" textAnchor="end" fontFamily="JetBrains Mono">{fmt(mx)}</text>
      </svg>
    </div>
  );
}

function Sparkline({ data, width = 60, height = 14, color = C.green }) {
  if (!data || !data.length) return null;
  const mn = Math.min(...data), mx = Math.max(...data);
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * width,
    height - ((v - mn) / (mx - mn || 1)) * (height - 2) - 1
  ]);
  return (
    <svg width={width} height={height} style={{ display: "inline-block", verticalAlign: "middle" }}>
      <path d={lineFromPoints(pts)} fill="none" stroke={color} strokeWidth="1.2" />
    </svg>
  );
}

function MonthlyHeat({ monthly, cellSize = 16 }) {
  const cols = 12;
  const min = Math.min(...monthly.map(m => m.pnl));
  const max = Math.max(...monthly.map(m => m.pnl));
  const colorFor = (v) => {
    if (v >= 0) {
      const t = v / (max || 1);
      return `rgba(111, 209, 122, ${0.18 + t * 0.7})`;
    } else {
      const t = Math.abs(v) / Math.abs(min || 1);
      return `rgba(255, 122, 85, ${0.18 + t * 0.7})`;
    }
  };
  const [hov, setHov] = useState(null);
  return (
    <div style={{ position: "relative" }}>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, ${cellSize}px)`, gap: 2 }}>
        {monthly.map((m, i) => (
          <div key={i}
            onMouseEnter={() => setHov(m)} onMouseLeave={() => setHov(null)}
            style={{
              width: cellSize, height: cellSize, background: colorFor(m.pnl),
              border: `1px solid ${C.border}`, cursor: "pointer"
            }} />
        ))}
      </div>
      {hov && (
        <div style={{
          position: "absolute", right: 0, top: -22,
          background: C.panel2, border: `1px solid ${C.borderL}`,
          padding: "2px 6px", font: "10px JetBrains Mono", color: hov.pnl >= 0 ? C.green : C.coral
        }}>
          M{hov.idx + 1} · {hov.pnl >= 0 ? "+" : ""}{hov.pnl.toFixed(2)}%
        </div>
      )}
    </div>
  );
}

Object.assign(window, {
  EquityChart, DrawdownChart, HeatmapGrid, FanChart, Histogram, Sparkline, MonthlyHeat,
  lineFromPoints, clamp
});
