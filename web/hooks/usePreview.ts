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
}

export function usePreview(params: Record<string, unknown> | null, delay = 80) {
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!params) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.post<PreviewResult>("/runs/preview", params);
        setResult(data);
      } catch {
        // API not available — silently skip
      } finally {
        setLoading(false);
      }
    }, delay);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [JSON.stringify(params), delay]);

  return { result, loading };
}
