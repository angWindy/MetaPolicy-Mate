"use client";

import { useId, type InputHTMLAttributes, type ReactNode } from "react";
import styles from "./SearchInput.module.css";

export type SearchInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: string; hideLabel?: boolean; leadingIcon?: ReactNode; onClear?: () => void };
export function SearchInput({ id, label = "Tìm kiếm", hideLabel = true, leadingIcon, onClear, className = "", value, disabled, ...props }: SearchInputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hasValue = typeof value === "string" && value.length > 0;
  return (
    <label className={`${styles.wrapper} ${disabled ? styles.disabled : ""} ${className}`.trim()} htmlFor={inputId}>
      <span className={hideLabel ? "sr-only" : ""}>{label}</span>
      {leadingIcon && <span className={styles.icon} aria-hidden="true">{leadingIcon}</span>}
      <input id={inputId} className={styles.input} type="search" value={value} disabled={disabled} {...props} />
      {onClear && hasValue && <button className={styles.clear} type="button" aria-label="Xóa tìm kiếm" onClick={onClear}>×</button>}
    </label>
  );
}
