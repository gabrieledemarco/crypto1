"use client";
import { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { Trade } from "@/lib/fixtures";
import type { ApiRunListItem, ApiTrade } from "@/lib/api-types";

// Re-export for backwards compatibility with existing imports
export type RunListItem = ApiRunListItem;

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

// List runs with full metrics + date range, optionally filtered by strategy
export function useRunList(strategyId?: string | null) {
  const path = strategyId
    ? `/runs?strategy_id=${encodeURIComponent(strategyId)}`
    : "/runs";
  return useQuery({
    queryKey: ["run-list", strategyId ?? null],
    queryFn: () => api.get<RunListItem[]>(path),
    enabled: strategyId !== undefined,
    staleTime: 15_000,
    retry: false,
  });
}

// Fetch all runs unconditionally (for logic-group view)
export function useAllRuns() {
  return useQuery({
    queryKey: ["run-list-all"],
    queryFn: () => api.get<RunListItem[]>("/runs"),
    staleTime: 15_000,
    retry: false,
  });
}

// Delete a single run by id
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

// Delete all runs with no strategy_id
export function useDeleteUnlinkedRuns() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.delete<{ deleted: number; ids: string[] }>("/runs"),
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

const _MAX_EQUITY_POINTS = 500;

function downsampleEquity<T>(pts: T[]): T[] {
  if (pts.length <= _MAX_EQUITY_POINTS) return pts;
  const step = (pts.length - 1) / (_MAX_EQUITY_POINTS - 1);
  const out: T[] = [pts[0]]; // always include first
  for (let i = 1; i < _MAX_EQUITY_POINTS - 1; i++) {
    out.push(pts[Math.round(i * step)]);
  }
  out.push(pts[pts.length - 1]); // always include last
  return out;
}

// Equity series  [{i, ts, v, dd}]
export function useRunEquity(runId: string | null) {
  return useQuery({
    queryKey: ["run-equity", runId],
    queryFn: () =>
      api.get<{ i: number; ts: string; v: number; dd: number }[]>(
        `/runs/${runId}/equity`
      ),
    select: downsampleEquity,
    enabled: isRealRunId(runId),
    staleTime: Infinity,   // run results never change — cache forever, but invalidated on new run
    refetchOnMount: false, // cached result is sufficient on screen switch; invalidated on new run
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
    staleTime: Infinity,   // run results never change — cache forever, but invalidated on new run
    refetchOnMount: false, // cached result is sufficient on screen switch; invalidated on new run
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

interface BootstrapCI {
  run_id: string;
  n_returns: number;
  sharpe: { point: number; ci_low: number; ci_high: number };
  cagr_pct: { point: number; ci_low: number; ci_high: number };
}

export function useRunBootstrapCI(runId: string | null) {
  return useQuery({
    queryKey: ["run-bootstrap-ci", runId],
    queryFn: () => api.get<BootstrapCI>(`/runs/${runId}/bootstrap-ci`),
    enabled: !!runId && isRealRunId(runId),
    staleTime: 300_000,
    retry: false,
  });
}

// Call this on any screen that shows a run. If the server returns 404 (run was
// deleted externally), clears activeRunId so the UI falls back to fixture data.
export function useValidateActiveRun(
  runId: string | null,
  clearRun: () => void
): void {
  const query = useRun(runId);
  useEffect(() => {
    if (
      query.isError &&
      query.error instanceof ApiError &&
      query.error.status === 404
    ) {
      clearRun();
    }
  }, [query.isError, query.error, clearRun]);
}
