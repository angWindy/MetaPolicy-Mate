import type { ReactNode } from "react";
import styles from "./StatCard.module.css";

export type StatCardProps = { label: string; value: ReactNode; icon?: ReactNode; trend?: string; trendTone?: "positive" | "negative" | "neutral"; description?: string; className?: string };
export function StatCard({ label, value, icon, trend, trendTone = "neutral", description, className = "" }: StatCardProps) {
  return <article className={`${styles.card} ${className}`.trim()}><div className={styles.header}><p className={styles.label}>{label}</p>{icon && <span className={styles.icon} aria-hidden="true">{icon}</span>}</div><p className={styles.value}>{value}</p>{(trend || description) && <div className={styles.footer}>{trend && <span className={`${styles.trend} ${styles[trendTone]}`}>{trend}</span>}{description && <span>{description}</span>}</div>}</article>;
}
