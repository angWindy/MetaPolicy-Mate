"use client";

import styles from "./Pagination.module.css";
export type PaginationProps = { page: number; totalPages: number; onPageChange: (page: number) => void; totalItems?: number; pageSize?: number; siblingCount?: number; className?: string };
export function Pagination({ page, totalPages, onPageChange, totalItems, pageSize = 10, siblingCount = 1, className = "" }: PaginationProps) {
  const safeTotal = Math.max(1, totalPages);
  const current = Math.min(Math.max(1, page), safeTotal);
  const start = Math.max(1, current - siblingCount);
  const end = Math.min(safeTotal, current + siblingCount);
  const pages = Array.from({ length: end - start + 1 }, (_, index) => start + index);
  const firstItem = totalItems === 0 ? 0 : (current - 1) * pageSize + 1;
  const lastItem = totalItems === undefined ? undefined : Math.min(totalItems, current * pageSize);
  return <nav className={`${styles.pagination} ${className}`.trim()} aria-label="Phân trang">{totalItems !== undefined && <p className={styles.summary}>Hiển thị {firstItem}-{lastItem} trong {totalItems}</p>}<div className={styles.controls}><button className={styles.page} type="button" disabled={current === 1} onClick={() => onPageChange(current - 1)} aria-label="Trang trước">‹</button>{start > 1 && <button className={styles.page} type="button" onClick={() => onPageChange(1)}>1</button>}{start > 2 && <span aria-hidden="true">…</span>}{pages.map((value) => <button key={value} className={`${styles.page} ${value === current ? styles.active : ""}`.trim()} type="button" aria-current={value === current ? "page" : undefined} onClick={() => onPageChange(value)}>{value}</button>)}{end < safeTotal - 1 && <span aria-hidden="true">…</span>}{end < safeTotal && <button className={styles.page} type="button" onClick={() => onPageChange(safeTotal)}>{safeTotal}</button>}<button className={styles.page} type="button" disabled={current === safeTotal} onClick={() => onPageChange(current + 1)} aria-label="Trang sau">›</button></div></nav>;
}
