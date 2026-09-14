"use client";

import { AlertTriangle, X } from "lucide-react";

import styles from "./AdminUsers.module.css";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  /** Bullet-list of consequences shown under the message. */
  impacts?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmModal({
  open,
  title,
  message,
  impacts,
  confirmLabel = "Xác nhận",
  cancelLabel = "Hủy",
  destructive = false,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmModalProps) {
  if (!open) return null;

  return (
    <div
      className={styles.modalBackdrop}
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <section
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <div className={styles.modalHeader}>
          <div>
            <h2 id="confirm-title">
              {destructive && (
                <AlertTriangle
                  size={18}
                  aria-hidden="true"
                  color="#c0392b"
                  style={{
                    verticalAlign: "-3px",
                    marginRight: 8,
                  }}
                />
              )}
              {title}
            </h2>
            <p>{message}</p>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            aria-label="Đóng cửa sổ"
            onClick={onClose}
            disabled={busy}
          >
            <X size={20} />
          </button>
        </div>

        <div className={styles.formBody}>
          {impacts && impacts.length > 0 && (
            <div
              style={{
                background: destructive ? "#fef2f2" : "#f7f9ff",
                border: "1px solid",
                borderColor: destructive ? "#fca5a5" : "#cbd5f5",
                borderRadius: 10,
                padding: "12px 14px",
                marginTop: 4,
              }}
            >
              <strong
                style={{
                  display: "block",
                  fontSize: 13,
                  marginBottom: 6,
                }}
              >
                Tác động
              </strong>
              <ul
                style={{
                  margin: 0,
                  paddingLeft: 18,
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              >
                {impacts.map((impact, idx) => (
                  <li key={idx}>{impact}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.cancelButton}
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={destructive ? undefined : styles.submitButton}
            style={
              destructive
                ? {
                    display: "inline-flex",
                    minHeight: 40,
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "0 16px",
                    border: "none",
                    borderRadius: 9,
                    background: "#dc2626",
                    color: "#fff",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: busy ? "not-allowed" : "pointer",
                    opacity: busy ? 0.6 : 1,
                  }
                : undefined
            }
          >
            {busy ? "Đang xử lý…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
