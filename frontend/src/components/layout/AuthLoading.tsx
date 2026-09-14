"use client";

import type { ReactNode } from "react";

import styles from "./AuthLoading.module.css";

export type AuthLoadingProps = {
  /** Optional override for the headline copy. */
  title?: string;
  /** Optional override for the body copy. */
  subtitle?: string;
  /** Show full skeleton (sidebar + content). Defaults to `true`. */
  withShell?: boolean;
};

/**
 * Skeleton loader rendered by `AuthGate` while the JWT-derived session
 * is still being resolved on the client.
 *
 * Without this fallback, gated pages return `null` while `isLoaded`
 * is false and the user sees a blank screen for the brief window
 * between hydration and the redirect decision. We render a stable
 * shell-shaped placeholder so the layout does not flash.
 */
export function AuthLoading({
  title = "Đang tải phiên đăng nhập…",
  subtitle = "Vui lòng chờ trong giây lát.",
  withShell = true,
}: AuthLoadingProps): ReactNode {
  return (
    <div
      className={
        withShell ? styles.shell : styles.compact
      }
      role="status"
      aria-live="polite"
      aria-busy="true"
      data-testid="auth-loading"
    >
      {withShell ? (
        <>
          <header className={styles.topbar} aria-hidden="true">
            <div className={styles.brandMark} />
            <div className={styles.titleBar} />
            <div className={styles.accountBlock} />
          </header>
          <main className={styles.content}>
            <div className={styles.message}>
              <div
                className={
                  styles.spinner
                }
                aria-hidden="true"
              />
              <div className={styles.messageText}>
                <strong className={styles.messageTitle}>
                  {title}
                </strong>
                <span className={styles.messageSubtitle}>
                  {subtitle}
                </span>
              </div>
            </div>
          </main>
        </>
      ) : (
        <div className={styles.message}>
          <div
            className={styles.spinner}
            aria-hidden="true"
          />
          <div className={styles.messageText}>
            <strong className={styles.messageTitle}>
              {title}
            </strong>
            <span className={styles.messageSubtitle}>
              {subtitle}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
