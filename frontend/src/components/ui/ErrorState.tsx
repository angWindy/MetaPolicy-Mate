"use client";

import styles from "./ErrorState.module.css";

export type ErrorStateProps = {
  title?: string;
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
};

export function ErrorState({
  title = "Không thể tải nội dung",
  message = "Đã có sự cố tạm thời. Vui lòng thử lại sau ít phút.",
  retryLabel = "Thử lại",
  onRetry,
}: ErrorStateProps) {
  return (
    <section className={styles.state} role="alert">
      <span className={styles.icon} aria-hidden="true">
        !
      </span>
      <h2>{title}</h2>
      <p>{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </section>
  );
}

