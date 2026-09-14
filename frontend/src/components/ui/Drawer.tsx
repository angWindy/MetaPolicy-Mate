"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./Overlay.module.css";

export type DrawerProps = { open: boolean; onClose: () => void; title: string; description?: string; children: ReactNode; footer?: ReactNode; side?: "left" | "right"; closeLabel?: string; className?: string };
export function Drawer({ open, onClose, title, description, children, footer, side = "right", closeLabel = "Đóng ngăn nội dung", className = "" }: DrawerProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    function handleEscape(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    document.addEventListener("keydown", handleEscape);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener("keydown", handleEscape); previousFocus?.focus(); };
  }, [onClose, open]);
  if (!open) return null;
  return <div className={`${styles.backdrop} ${styles.drawerBackdrop}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div ref={panelRef} className={`${styles.panel} ${styles.drawer} ${styles[side]} ${className}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}><div className={styles.header}><div className={styles.heading}><h2 className={styles.title} id={titleId}>{title}</h2>{description && <p className={styles.description}>{description}</p>}</div><button className={styles.close} type="button" aria-label={closeLabel} onClick={onClose}>×</button></div><div className={styles.body}>{children}</div>{footer && <div className={styles.footer}>{footer}</div>}</div></div>;
}
