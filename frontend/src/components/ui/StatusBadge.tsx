import type { ReactNode } from "react";
import styles from "./StatusBadge.module.css";

export type StatusBadgeProps = { children: ReactNode; tone?: "neutral" | "info" | "success" | "warning" | "danger"; showDot?: boolean; className?: string };
export function StatusBadge({ children, tone = "neutral", showDot = false, className = "" }: StatusBadgeProps) {
  return <span className={`${styles.badge} ${styles[tone]} ${className}`.trim()}>{showDot && <span className={styles.dot} aria-hidden="true" />}{children}</span>;
}
