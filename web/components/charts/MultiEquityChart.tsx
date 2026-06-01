"use client";
import { useEffect, useMemo, useRef } from "react";
import { useQueries } from "@tanstack/react-query";
import { createChart, LineStyle, Time } from "lightweight-charts";
import { api } from "@/lib/api";
import type { ApiEquityPoint } from "@/lib/api-types";

interface SeriesInput {
  id: string;
  name: string;
  color: string;
  localEquity?: ApiEquityPoint[];
}

interface Props {
  runs: SeriesInput[];
  height?: number;
}

const palette = ["#ffb53b", "#75d7ff", "#6fd17a", "#ff6b6b", "#b08cff", "#f4d35e", "#8bd3dd", "#f582ae"];

function downsample<T>(pts: T[], max = 420): T[] {
  if (pts.length <= max) return pts;
  const step = (pts.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, i) => pts[Math.round(i * step)]);
}

function normalizeEquity(points: ApiEquityPoint[]) {
  const cleaned = points.filter((p) => Number.isFinite(Number(p.v)));
  if (!cleaned.length) return [];
  const base = Number(cleaned[0].v) || 1;
  return downsample(cleaned).map((p, i) => ({ i, value: ((Number(p.v) / base) - 1) * 100 }));
}

export function MultiEquityChart({ runs, height = 260 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const queries = useQueries({
    queries: runs.map((run) => ({
      queryKey: ["run-equity", run.id],
      queryFn: () => api.get<ApiEquityPoint[]>(`/runs/${run.id}/equity`),
      staleTime: Infinity,
      retry: false,
      enabled: !!run.id && !run.localEquity,
    })),
  });

  const series = useMemo(() => runs.map((run, idx) => ({
    ...run,
    color: run.color || palette[idx % palette.length],
    data: normalizeEquity(run.localEquity ?? (queries[idx]?.data as ApiEquityPoint[] | undefined) ?? []),
    loading: queries[idx]?.isLoading,
    error: queries[idx]?.isError,
  })), [runs, queries]);

  const average = useMemo(() => {
    const available = series.filter((s) => s.data.length > 0);
    if (!available.length) return [];
    const maxLen = Math.max(...available.map((s) => s.data.length));
    return Array.from({ length: maxLen }, (_, i) => {
      const vals = available
        .map((s) => s.data[Math.min(i, s.data.length - 1)]?.value)
        .filter((v): v is number => Number.isFinite(Number(v)));
      const avg = vals.reduce((a, b) => a + b, 0) / Math.max(vals.length, 1);
      return { i, value: avg };
    });
  }, [series]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      autoSize: true,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: "#a3a78c",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#3a3c28", style: LineStyle.Dashed },
        horzLines: { color: "#3a3c28", style: LineStyle.Dashed },
      },
      rightPriceScale: { borderColor: "#3a3c28", scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: "#3a3c28", timeVisible: false },
      crosshair: { mode: 1 },
    });

    series.forEach((item) => {
      if (!item.data.length) return;
      const line = chart.addLineSeries({
        color: item.color,
        lineWidth: 1,
        priceFormat: { type: "percent" },
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(item.data.map((p) => ({ time: (p.i + 1000000) as Time, value: p.value })));
    });

    if (average.length) {
      const avgLine = chart.addLineSeries({
        color: "#ffffff",
        lineWidth: 3,
        priceFormat: { type: "percent" },
        title: "AVG",
      });
      avgLine.setData(average.map((p) => ({ time: (p.i + 1000000) as Time, value: p.value })));
      avgLine.createPriceLine({ price: 0, color: "#5a5d3a", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "" });
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [series, average, height]);

  const loading = series.some((s) => s.loading);
  const ready = series.some((s) => s.data.length > 0);

  return (
    <div>
      <div ref={containerRef} style={{ height, minHeight: height }} />
      {!ready && (
        <div style={{ height, marginTop: -height, display: "grid", placeItems: "center", color: "var(--faint)", fontFamily: "var(--font-mono)", fontSize: 10, pointerEvents: "none" }}>
          {loading ? "LOADING EQUITY…" : "SELECT RUNS WITH EQUITY"}
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        <span style={{ color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 10 }}>━━ AVG</span>
        {series.map((s) => (
          <span key={s.id} style={{ color: s.error ? "var(--coral)" : s.color, fontFamily: "var(--font-mono)", fontSize: 10 }}>
            ━ {s.name.slice(0, 22)}{s.name.length > 22 ? "…" : ""}
          </span>
        ))}
      </div>
    </div>
  );
}
