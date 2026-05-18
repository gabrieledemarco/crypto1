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
        cbRef.current(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
    };
    return () => es.close();
  }, [url]);
}
