"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface AssetListItem {
  ticker: string;
  source: string;
  start: string;
  end: string;
  bars: number;
}

interface Bar {
  i: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  r: number;
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

// OHLCV bars for a single ticker
export function useAssetBars(ticker: string | null) {
  return useQuery({
    queryKey: ["asset-bars", ticker],
    queryFn: () => api.get<Bar[]>(`/assets/${ticker}/bars`),
    enabled: !!ticker,
    staleTime: 60_000,
    retry: false,
  });
}

// Quant stats for a single ticker
export function useAssetStats(ticker: string | null) {
  return useQuery({
    queryKey: ["asset-stats", ticker],
    queryFn: () => api.get<AssetStatsApi>(`/assets/${ticker}/stats`),
    enabled: !!ticker,
    staleTime: 60_000,
    retry: false,
  });
}
