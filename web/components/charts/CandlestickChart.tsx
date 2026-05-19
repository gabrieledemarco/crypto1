"use client";
import { useEffect, useRef, useState } from "react";

interface Bar {
  ts?: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number;
}

interface Props {
  bars: Bar[];
  width?: number;
  height?: number;
  showEMA20?: boolean;
  showEMA50?: boolean;
}

function computeEMA(prices: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const ema: number[] = [prices[0]];
  for (let i = 1; i < prices.length; i++) {
    ema.push(prices[i] * k + ema[i - 1] * (1 - k));
  }
  return ema;
}

export function CandlestickChart({
  bars,
  height = 240,
  showEMA20 = true,
  showEMA50 = false,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [svgWidth, setSvgWidth] = useState(480);

  useEffect(() => {
    const ro = new ResizeObserver((es) => {
      if (es[0]) setSvgWidth(es[0].contentRect.width);
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const visible = bars.slice(-120);

  if (visible.length === 0) {
    return (
      <div ref={wrapRef} style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
          NO DATA
        </span>
      </div>
    );
  }

  const padL = 4;
  const padR = 48; // room for y-axis labels
  const padT = 8;
  const padB = 20; // room for x-axis labels

  const volHeight = Math.floor(height * 0.2);
  const priceHeight = height - padT - padB - volHeight - 4;

  const innerW = Math.max(10, svgWidth - padL - padR);
  const candleW = innerW / visible.length;
  const bodyW = Math.max(2, candleW - 1);

  // Price range
  const highs = visible.map((b) => b.h);
  const lows  = visible.map((b) => b.l);
  const priceMin = Math.min(...lows);
  const priceMax = Math.max(...highs);
  const priceRange = priceMax - priceMin || 1;

  const py = (price: number) =>
    padT + priceHeight - ((price - priceMin) / priceRange) * priceHeight;

  // Volume range
  const vols = visible.map((b) => b.v ?? 0);
  const maxVol = Math.max(...vols) || 1;

  const volY = (vol: number) => {
    const volFrac = vol / maxVol;
    return padT + priceHeight + 4 + volHeight * (1 - volFrac);
  };
  const volBarH = (vol: number) => {
    const volFrac = vol / maxVol;
    return volHeight * volFrac;
  };

  // EMA lines (computed over visible closes)
  const closes = visible.map((b) => b.c);
  const ema20 = showEMA20 && visible.length >= 20 ? computeEMA(closes, 20) : null;
  const ema50 = showEMA50 && visible.length >= 50 ? computeEMA(closes, 50) : null;

  const emaPath = (vals: number[]): string =>
    vals
      .map((v, i) => {
        const x = padL + i * candleW + candleW / 2;
        const y = py(v);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  // Y-axis labels: min, 25%, 75%, max
  const yLabelValues = [
    priceMin,
    priceMin + priceRange * 0.25,
    priceMin + priceRange * 0.75,
    priceMax,
  ];

  const formatPrice = (v: number) => {
    if (v >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (v >= 1) return v.toFixed(2);
    return v.toFixed(4);
  };

  // X-axis labels: 4 evenly spaced indices
  const xLabelIndices = [
    0,
    Math.floor(visible.length / 3),
    Math.floor((2 * visible.length) / 3),
    visible.length - 1,
  ];

  const formatDate = (ts: string | undefined): string => {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}`;
    } catch {
      return ts.slice(5, 10) ?? "";
    }
  };

  return (
    <div ref={wrapRef} style={{ width: "100%", height }}>
      <svg width={svgWidth} height={height} style={{ display: "block" }}>
        {/* Candles */}
        {visible.map((bar, i) => {
          const x = padL + i * candleW;
          const cx = x + candleW / 2;
          const isGreen = bar.c >= bar.o;
          const color = isGreen ? "#6fd17a" : "#ff7a55";

          const bodyTop = py(Math.max(bar.o, bar.c));
          const bodyBot = py(Math.min(bar.o, bar.c));
          const bodyHeight = Math.max(1, bodyBot - bodyTop);

          return (
            <g key={i}>
              {/* Wick */}
              <line
                x1={cx.toFixed(1)}
                x2={cx.toFixed(1)}
                y1={py(bar.h).toFixed(1)}
                y2={py(bar.l).toFixed(1)}
                stroke={color}
                strokeWidth={1}
              />
              {/* Body */}
              <rect
                x={(cx - bodyW / 2).toFixed(1)}
                y={bodyTop.toFixed(1)}
                width={bodyW.toFixed(1)}
                height={bodyHeight.toFixed(1)}
                fill={color}
              />
              {/* Volume bar */}
              {bar.v != null && (
                <rect
                  x={(cx - bodyW / 2).toFixed(1)}
                  y={volY(bar.v).toFixed(1)}
                  width={bodyW.toFixed(1)}
                  height={volBarH(bar.v).toFixed(1)}
                  fill={color}
                  opacity={0.4}
                />
              )}
            </g>
          );
        })}

        {/* EMA20 */}
        {ema20 && (
          <path
            d={emaPath(ema20)}
            fill="none"
            stroke="#ffb53b"
            strokeWidth={1.2}
            opacity={0.85}
          />
        )}

        {/* EMA50 */}
        {ema50 && (
          <path
            d={emaPath(ema50)}
            fill="none"
            stroke="#3dd6f5"
            strokeWidth={1.2}
            opacity={0.85}
          />
        )}

        {/* Y-axis labels */}
        {yLabelValues.map((v, i) => (
          <text
            key={i}
            x={svgWidth - padR + 4}
            y={py(v) + 4}
            fill="#7e8163"
            fontSize={9}
            fontFamily="JetBrains Mono,monospace"
            textAnchor="start"
          >
            {formatPrice(v)}
          </text>
        ))}

        {/* X-axis labels */}
        {visible[0]?.ts != null &&
          xLabelIndices.map((idx, i) => {
            const x = padL + idx * candleW + candleW / 2;
            return (
              <text
                key={i}
                x={x.toFixed(1)}
                y={height - 4}
                fill="#7e8163"
                fontSize={9}
                fontFamily="JetBrains Mono,monospace"
                textAnchor="middle"
              >
                {formatDate(visible[idx]?.ts)}
              </text>
            );
          })}

        {/* Baseline for price area */}
        <line
          x1={padL}
          x2={padL + innerW}
          y1={padT + priceHeight}
          y2={padT + priceHeight}
          stroke="#3a3c28"
          strokeWidth={0.6}
        />

        {/* EMA legend */}
        {(showEMA20 || showEMA50) && (
          <g>
            {showEMA20 && (
              <>
                <line x1={padL} x2={padL + 14} y1={padT + 8} y2={padT + 8} stroke="#ffb53b" strokeWidth={1.2} />
                <text x={padL + 18} y={padT + 12} fill="#ffb53b" fontSize={8} fontFamily="JetBrains Mono,monospace">EMA20</text>
              </>
            )}
            {showEMA50 && (
              <>
                <line x1={padL + 58} x2={padL + 72} y1={padT + 8} y2={padT + 8} stroke="#3dd6f5" strokeWidth={1.2} />
                <text x={padL + 76} y={padT + 12} fill="#3dd6f5" fontSize={8} fontFamily="JetBrains Mono,monospace">EMA50</text>
              </>
            )}
          </g>
        )}
      </svg>
    </div>
  );
}
