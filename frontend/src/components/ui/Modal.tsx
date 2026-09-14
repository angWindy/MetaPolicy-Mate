"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./Overlay.module.css";

export type ModalProps = { open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode; footer?: ReactNode; closeLabel?: string; className?: string };
export function Modal({ open, onClose, title, description, children, footer, closeLabel = "Đóng hộp thoại", className = "" }: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
      if (focusable.length === 0) { event.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handleKeyDown); previousFocus?.focus(); };
  }, [onClose, open]);
  if (!open) return null;
  return <div className={`${styles.backdrop} ${styles.modalBackdrop}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div ref={panelRef} className={`${styles.panel} ${styles.modal} ${className}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined} tabIndex={-1}><div className={styles.header}><div className={styles.heading}><h2 className={styles.title} id={titleId}>{title}</h2>{description && <p className={styles.description} id={descriptionId}>{description}</p>}</div><button className={styles.close} type="button" aria-label={closeLabel} onClick={onClose}>×</button></div><div className={styles.body}>{children}</div>{footer && <div className={styles.footer}>{footer}</div>}</div></div>;
}
