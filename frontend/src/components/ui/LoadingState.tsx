import styles from "./LoadingState.module.css";

export type LoadingStateProps = {
  label?: string;
  count?: number;
  variant?: "list" | "cards";
};

export function LoadingState({
  label = "Đang tải dữ liệu",
  count = 3,
  variant = "list",
}: LoadingStateProps) {
  const safeCount = Math.min(8, Math.max(1, count));

  return (
    <section className={styles.state} role="status" aria-live="polite" aria-busy="true">
      <span className={styles.srOnly}>{label}</span>
      <div
        className={`${styles.items} ${styles[variant]}`}
        aria-hidden="true"
      >
        {Array.from({ length: safeCount }, (_, index) => (
          <div className={styles.item} key={index}>
            <span className={styles.icon} />
            <span className={styles.content}>
              <span className={styles.title} />
              <span className={styles.description} />
              <span className={styles.metadata} />
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

