"use client";
import { useStore } from "@/store";
import { useState, useEffect } from "react";
import styles from "./StatusBar.module.css";

export function StatusBar() {
  const { runs, activeRunId, screen, gPrefix } = useStore();
  const [time, setTime] = useState("");

  const run = runs.find((r) => r.id === activeRunId);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(
        now.toUTCString().slice(17, 25) + " UTC"
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <footer className={styles.statusbar}>
      <div className={styles.section}>
        <span className={styles.label}>user</span>
        <span className={styles.value}>@</span>
        <span className={styles.value}>local</span>
      </div>

      <span className={styles.sep}>│</span>

      <div className={styles.section}>
        <span className={styles.label}>run:</span>
        <span className={styles.value}>{run?.name ?? "—"}</span>
      </div>

      <span className={styles.sep}>│</span>

      <div className={styles.section}>
        <span className={styles.label}>view:</span>
        <span className={styles.value}>{screen.toUpperCase()}</span>
      </div>

      <span className={styles.sep}>│</span>

      <div className={styles.section}>
        <span className={styles.live}>live</span>
        <span className={styles.dot}>●</span>
        <span className={styles.value}>connected</span>
      </div>

      {gPrefix && (
        <>
          <span className={styles.sep}>│</span>
          <span className={styles.gPrefix}>G— waiting...</span>
        </>
      )}

      <div className={styles.spacer} />

      <span className={styles.version}>v0.1.0 · {time}</span>
    </footer>
  );
}
