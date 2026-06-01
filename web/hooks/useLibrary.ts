"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface LibraryEntryApi {
  id: string;
  name: string;
  strategy: string;
  author: string;
  created: string;
  tags: string[];
  starred: boolean;
  status: "live" | "research" | "archived";
  metrics: {
    sharpe: number;
    cagr: number;
    maxDD: number;
    pf: number;
    trades: number;
  };
  desc: string;
  runRef?: string;
  sparkline?: number[];
}

// List all strategies from the backend
export function useLibrary() {
  return useQuery({
    queryKey: ["library"],
    queryFn: () => api.get<LibraryEntryApi[]>("/strategies"),
    staleTime: 30_000,
    retry: false,
  });
}

// Fetch full strategy metadata/config by id
export function useStrategy(id: string | null) {
  return useQuery({
    queryKey: ["strategy", id],
    queryFn: () => api.get<Record<string, unknown>>(`/strategies/${id}`),
    enabled: !!id,
    staleTime: 30_000,
    retry: false,
  });
}

// Toggle star on a strategy
export function useStarStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      fetch(`/api/strategies/${id}/star`, { method: "PUT" }).then((r) => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });
}
