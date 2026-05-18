"use client";
import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineStyle,
} from "lightweight-charts";
import styles from "./EquityChart.module.css";

interface EquityPoint {
  i: number;
  v: number;
  dd: number;
  ts?: string;
  bench?: number;
  oos?: boolean;
}

interface Props {
  equity: EquityPoint[];
  oosStart?: number | null;
  height?: number;
  color?: string;
  showBench?: boolean;
  logScale?: boolean;
  onHoverIndex?: (i: number | null) => void;
}

export function EquityChart({
  equity,
  oosStart,
  height = 220,
  color = "#ffb53b",
  showBench = true,
  logScale = false,
  onHoverIndex,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const benchRef = useRef<ISeriesApi<"Line"> | null>(null);

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
      rightPriceScale: {
        borderColor: "#3a3c28",
        scaleMargins: { top: 0.05, bottom: 0.05 },
        mode: logScale ? 1 : 0, // 1 = logarithmic
      },
      timeScale: { borderColor: "#3a3c28", timeVisible: true },
      crosshair: { mode: 1 },
      handleScale: { axisPressedMouseMove: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
    });

    const mainSeries = chart.addLineSeries({
      color,
      lineWidth: 2,
      priceFormat: { type: "percent" },
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
    });

    // Convert equity points to lightweight-charts data (time = index as unix seconds for simplicity)
    const baseVal = equity[0]?.v ?? 1;
    const data = equity.map((_e, i) => ({
      time: (i + 1000000) as unknown as import("lightweight-charts").Time,
      value: ((_e.v / baseVal) - 1) * 100, // percent return
    }));
    mainSeries.setData(data);

    // Benchmark (dashed)
    benchRef.current = null;
    if (showBench && equity[0]?.bench != null) {
      const benchSeries = chart.addLineSeries({
        color: "#5a5d3a",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceFormat: { type: "percent" },
        crosshairMarkerVisible: false,
        lastValueVisible: false,
      });
      const benchBase = equity[0].bench;
      benchSeries.setData(
        equity.map((_e, i) => ({
          time: (i + 1000000) as unknown as import("lightweight-charts").Time,
          value: ((_e.bench ?? benchBase) / benchBase - 1) * 100,
        }))
      );
      benchRef.current = benchSeries;
    }

    // OOS shading via background band — use a histogram series at low opacity
    if (oosStart != null && oosStart > 0 && oosStart < equity.length) {
      const oosSeries = chart.addHistogramSeries({
        color: color + "0d", // ~5% opacity
        priceFormat: { type: "percent" },
        lastValueVisible: false,
        priceScaleId: "",
      });
      oosSeries.priceScale().applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
      oosSeries.setData(
        equity.slice(oosStart).map((_e, i) => ({
          time: (i + oosStart + 1000000) as unknown as import("lightweight-charts").Time,
          value: 100,
          color: color + "1a",
        }))
      );
    }

    // Crosshair hover
    if (onHoverIndex) {
      chart.subscribeCrosshairMove((param) => {
        if (!param.point || !param.time) {
          onHoverIndex(null);
          return;
        }
        const idx = (param.time as number) - 1000000;
        onHoverIndex(idx);
      });
    }

    chartRef.current = chart;
    seriesRef.current = mainSeries;

    return () => {
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equity, oosStart, height, color, showBench, logScale]);

  return <div ref={containerRef} className={styles.root} style={{ height }} />;
}
