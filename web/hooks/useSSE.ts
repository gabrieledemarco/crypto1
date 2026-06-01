"use client";
import { useEffect, useRef } from "react";

const _MAX_RECONNECTS = 3;

export function useSSE(url: string | null, onMessage: (data: unknown) => void) {
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;

  useEffect(() => {
    if (!url) return;
    let attempts = 0;
    let es: EventSource;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let done = false;

    function connect() {
      es = new EventSource(url!);
      es.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data) as { phase?: string; msg?: string };
          cbRef.current(parsed);
          // Reconnect on any server-side error during a live run
          if (parsed.phase === "error" && !done) {
            if (attempts < _MAX_RECONNECTS) {
              attempts++;
              es.close();
              reconnectTimer = setTimeout(connect, 1500 * attempts);
            }
          }
          if (parsed.phase === "done") {
            done = true;
          }
        } catch {
          // do NOT rethrow — keep the stream alive
        }
      };
      es.onerror = () => {
        if (done) return;
        es.close();
        if (attempts < _MAX_RECONNECTS) {
          attempts++;
          reconnectTimer = setTimeout(connect, 1500 * attempts);
        }
      };
    }

    connect();
    return () => {
      done = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      es?.close();
    };
  }, [url]);
}
