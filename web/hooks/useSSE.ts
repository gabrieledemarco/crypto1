"use client";
import { useEffect, useRef } from "react";

export function useSSE(url: string | null, onMessage: (data: unknown) => void) {
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;
  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data);
        cbRef.current(parsed);
      } catch (parseErr) {
        console.warn('[SSE] Failed to parse message:', e.data, parseErr);
        // do NOT rethrow — keep the stream alive
      }
    };
    return () => es.close();
  }, [url]);
}
