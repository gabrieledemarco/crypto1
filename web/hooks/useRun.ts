"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/fixtures";

export interface RunListItem {
  id: string;
  name: string;
  ticker: string;
  timeframe: string;
  status: string;
  params: Record<string, unknown>;
  created_at: string;
  start_date?: string | null;
  end_date?: string | null;
  sharpe?: number | null;
  cagr?: number | null;
  max_dd?: number | null;
  pf?: number | null;
}

// API trade shape from the engine serializer
interface ApiTrade {
  entry_time: string;
  exit_time: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  exit_price: number;
  qty: number;
  pnl: number;
  exit_reason?: string;
}

// Map the API trade shape to the frontend Trade type so all components work uniformly
function normalizeApiTrade(t: ApiTrade, n: number): Trade {
  const entryMs = new Date(t.entry_time).getTime();
  const exitMs  = new Date(t.exit_time).getTime();
  const durH = Number.isFinite(entryMs) && Number.isFinite(exitMs)
    ? Math.round((exitMs - entryMs) / 3_600_000)
    : 0;
  const r = t.entry_price > 0 ? Math.round((t.pnl / t.entry_price) * 1000) / 10 : 0;
  return {
    n,
    idx: n,
    date: entryMs || 0,
    side: t.direction === "LONG" ? "L" : "S",
    entry: t.entry_price,
    exit: t.exit_price,
    r,
    durH,
    pnl: Math.round(t.pnl * 100) / 100,
    equity: 0,
  };
}

// List all runs (basic)
export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<{ id: string; name: string; status: string }[]>("/runs"),
    staleTime: 30_000,
  });
}

// List all runs with full metrics + date range
export function useRunList() {
  return useQuery({
    queryKey: ["run-list"],
    queryFn: () => api.get<RunListItem[]>("/runs"),
    staleTime: 15_000,
    retry: false,
  });
}

// Delete a run by id
export function useDeleteRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      api.delete<{ deleted: string }>(`/runs/${runId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run-list"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

// Fixture run IDs (run-NNN) don't exist in the database — skip API calls for them
export function isRealRunId(id: string | null): boolean {
  return !!id && !/^run-\d+$/.test(id);
}

// Run metadata + metrics
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.get<Record<string, unknown>>(`/runs/${runId}`),
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}

// Equity series  [{i, ts, v, dd}]
export function useRunEquity(runId: string | null) {
  return useQuery({
    queryKey: ["run-equity", runId],
    queryFn: () =>
      api.get<{ i: number; ts: string; v: number; dd: number }[]>(
        `/runs/${runId}/equity`
      ),
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}

// Trades (paginated)
export function useRunTrades(
  runId: string | null,
  params?: { side?: string; pnl?: string; offset?: number; limit?: number }
) {
  const qs = new URLSearchParams();
  if (params?.side) qs.set("side", params.side);
  if (params?.pnl) qs.set("pnl", params.pnl);
  if (params?.offset) qs.set("offset", String(params.offset));
  if (params?.limit) qs.set("limit", String(params.limit ?? 100));
  return useQuery({
    queryKey: ["run-trades", runId, params],
    queryFn: async () => {
      const res = await api.get<{ total: number; trades: ApiTrade[] }>(
        `/runs/${runId}/trades?${qs}`
      );
      return {
        total: res.total,
        trades: res.trades.map((t, i) => normalizeApiTrade(t, i + 1)),
      };
    },
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}

// WFO fold results
export function useRunWFO(runId: string | null) {
  return useQuery({
    queryKey: ["run-wfo", runId],
    queryFn: () => api.get<unknown[]>(`/runs/${runId}/wfo`),
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}

// Param sweep grid
export function useRunSweep(runId: string | null) {
  return useQuery({
    queryKey: ["run-sweep", runId],
    queryFn: () => api.get<unknown[]>(`/runs/${runId}/sweep`),
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}

// Monte Carlo paths + percentiles
export function useRunMC(runId: string | null) {
  return useQuery({
    queryKey: ["run-mc", runId],
    queryFn: () => api.get<Record<string, unknown>>(`/runs/${runId}/mc`),
    enabled: isRealRunId(runId),
    staleTime: 60_000,
  });
}
