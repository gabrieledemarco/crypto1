"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";

export interface PreviewResult {
  sharpe: number;
  cagr: number;
  max_dd: number;
  trades: number;
  win_rate: number;
  exposure: number;
  equity?: number[];
}

export function usePreview(params: Record<string, unknown> | null, delay = 80) {
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!params) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.post<PreviewResult>("/runs/preview", params);
        setResult(data);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        console.error('[usePreview]', msg);
      } finally {
        setLoading(false);
      }
    }, delay);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [JSON.stringify(params), delay]);

  return { result, loading, error };
}
