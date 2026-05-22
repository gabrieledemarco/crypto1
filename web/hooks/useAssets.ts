"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface AssetListItem {
  ticker: string;
  source: string;
  interval: string;
  start: string;
  end: string;
  bars: number;
}

interface Bar {
  ts?: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

interface AssetStatsApi {
  ticker: string;
  bars: number;
  cagr: number;
  ann_vol: number;
  sharpe: number;
  max_dd: number;
  skew: number;
  kurt: number;
  sortino?: number;
  var95?: number;
  cvar95?: number;
  best_day?: number;
  worst_day?: number;
}

// List assets stored in DuckDB
export function useAssets() {
  return useQuery({
    queryKey: ["assets"],
    queryFn: () => api.get<AssetListItem[]>("/assets"),
    staleTime: 30_000,
    retry: false,
  });
}

// OHLCV bars for a single ticker (optionally filtered by interval)
export function useAssetBars(ticker: string | null, interval = "1d") {
  return useQuery({
    queryKey: ["asset-bars", ticker, interval],
    queryFn: () => api.get<Bar[]>(`/assets/${ticker}/bars?interval=${interval}&limit=2000`),
    enabled: !!ticker,
    staleTime: 60_000,
    retry: false,
  });
}

// Quant stats for a single ticker (optionally for a specific interval)
export function useAssetStats(ticker: string | null, interval = "1d") {
  return useQuery({
    queryKey: ["asset-stats", ticker, interval],
    queryFn: () => api.get<AssetStatsApi>(`/assets/${ticker}/stats?interval=${interval}`),
    enabled: !!ticker,
    staleTime: 60_000,
    retry: false,
  });
}

interface GarchForecast {
  ticker: string;
  interval: string;
  n_bars: number;
  params: {
    omega: number;
    alpha: number;
    beta: number;
    persistence: number;
    half_life_bars: number | null;
  };
  current_vol_pct: number;
  forecast_vol_pct: { h1: number; h5: number; h22: number };
  ann_vol_pct: number;
  ljung_box: {
    returns: { stat: number; pvalue: number; significant: boolean };
    sq_returns: { stat: number; pvalue: number; significant: boolean };
  };
}

export function useGarchForecast(ticker: string | null, interval = "1h") {
  return useQuery({
    queryKey: ["garch-forecast", ticker, interval],
    queryFn: () => api.get<GarchForecast>(`/assets/${ticker}/garch-forecast?interval=${interval}`),
    enabled: !!ticker,
    staleTime: 300_000,
    retry: false,
  });
}

export type { AssetListItem, AssetStatsApi, Bar, GarchForecast };
