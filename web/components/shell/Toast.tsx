"use client";
import styles from "./Toast.module.css";

interface Props {
  msg: string | null;
}

export function Toast({ msg }: Props) {
  if (!msg) return null;
  return <div className={styles.toast}>{msg}</div>;
}
