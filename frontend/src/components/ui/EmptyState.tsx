import type { ReactNode } from "react";

import styles from "./EmptyState.module.css";

export type EmptyStateProps = {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
};

export function EmptyState({
  title,
  description,
  icon = "◇",
  action,
}: EmptyStateProps) {
  return (
    <section className={styles.state} role="status">
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <h2>{title}</h2>
      {description && <p>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </section>
  );
}

