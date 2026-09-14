import type { ReactNode } from "react";
import styles from "./DocumentCard.module.css";

export type DocumentCardProps = { title: string; description?: string; status?: ReactNode; icon?: ReactNode; metadata?: ReactNode[]; actions?: ReactNode; className?: string };
export function DocumentCard({ title, description, status, icon, metadata = [], actions, className = "" }: DocumentCardProps) {
  return <article className={`${styles.card} ${className}`.trim()}>{icon && <span className={styles.icon} aria-hidden="true">{icon}</span>}<div className={styles.content}><div className={styles.heading}><h3 className={styles.title}>{title}</h3>{status}</div>{description && <p className={styles.description}>{description}</p>}{metadata.length > 0 && <div className={styles.meta}>{metadata.map((item, index) => <span key={index}>{item}</span>)}</div>}</div>{actions && <div className={styles.actions}>{actions}</div>}</article>;
}
