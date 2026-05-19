"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// List all runs
export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<{ id: string; name: string; status: string }[]>("/runs"),
    staleTime: 30_000,
  });
}

// Fixture run IDs (run-NNN) don't exist in the database — skip API calls for them
function isRealRunId(id: string | null): boolean {
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
    queryFn: () =>
      api.get<{ total: number; trades: unknown[] }>(
        `/runs/${runId}/trades?${qs}`
      ),
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
