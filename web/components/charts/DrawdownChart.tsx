"use client";
import { useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, LineStyle } from "lightweight-charts";
import styles from "./DrawdownChart.module.css";

interface EquityPoint {
  i: number;
  v: number;
  dd: number;
  ts?: string;
}

interface Props {
  equity: EquityPoint[];
  height?: number;
  color?: string;
  sharedHoverIndex?: number | null;
}

export function DrawdownChart({
  equity,
  height = 64,
  color = "#ff7a55",
  sharedHoverIndex,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: "transparent" },
        textColor: "#a3a78c",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "transparent" },
        horzLines: { color: "#3a3c28", style: LineStyle.Dashed },
      },
      rightPriceScale: {
        borderColor: "#3a3c28",
        scaleMargins: { top: 0, bottom: 0 },
      },
      timeScale: { borderColor: "#3a3c28", visible: false },
      crosshair: { mode: 1 },
      handleScale: false,
      handleScroll: false,
    });

    const area = chart.addAreaSeries({
      topColor: color + "2e", // ~18% opacity
      bottomColor: color + "00",
      lineColor: color,
      lineWidth: 1,
      priceFormat: { type: "percent" },
      lastValueVisible: false,
    });

    area.setData(
      equity.map((_e, i) => ({
        time: (i + 1000000) as unknown as import("lightweight-charts").Time,
        value: _e.dd * 100,
      }))
    );

    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(containerRef.current);
    seriesRef.current = area;
    chartRef.current = chart;
    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [equity, height, color]);

  // Sync crosshair position from shared hover
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current || sharedHoverIndex == null) return;
    try {
      chartRef.current.setCrosshairPosition(
        0,
        {
          time: (sharedHoverIndex + 1000000) as unknown as import("lightweight-charts").Time,
        } as unknown as Parameters<typeof chartRef.current.setCrosshairPosition>[1],
        seriesRef.current
      );
    } catch {
      // silent — API varies by lw-charts version
    }
  }, [sharedHoverIndex]);

  return <div ref={containerRef} className={styles.root} style={{ height }} />;
}
