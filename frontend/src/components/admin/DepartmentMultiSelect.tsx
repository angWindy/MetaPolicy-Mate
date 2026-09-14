"use client";

import { useMemo } from "react";

import type { DepartmentResponse } from "@/services/organizationService";

import styles from "./AdminUsers.module.css";

interface DepartmentMultiSelectProps {
  departments: DepartmentResponse[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  emptyMessage?: string;
}

export function DepartmentMultiSelect({
  departments,
  selectedIds,
  onChange,
  disabled = false,
  emptyMessage = "Chưa có đơn vị nào.",
}: DepartmentMultiSelectProps) {
  const selectedSet = useMemo(
    () => new Set(selectedIds),
    [selectedIds],
  );

  function toggle(id: string) {
    if (disabled) return;
    const next = new Set(selectedSet);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(Array.from(next));
  }

  function selectAll() {
    if (disabled) return;
    onChange(
      departments
        .filter((d) => d.is_active)
        .map((d) => d.id),
    );
  }

  function clearAll() {
    if (disabled) return;
    onChange([]);
  }

  if (departments.length === 0) {
    return (
      <p
        style={{
          fontSize: 13,
          color: "var(--color-text-muted)",
          padding: "12px 0",
        }}
      >
        {emptyMessage}
      </p>
    );
  }

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: 10,
        padding: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
          paddingBottom: 8,
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <small
          style={{
            color: "var(--color-text-muted)",
            fontSize: 12,
          }}
        >
          Đã chọn {selectedIds.length}/{departments.length}
        </small>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            onClick={selectAll}
            disabled={disabled}
            style={{
              fontSize: 11,
              padding: "3px 8px",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              background: "#fff",
              color: "var(--color-text)",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.6 : 1,
            }}
          >
            Chọn tất cả
          </button>
          <button
            type="button"
            onClick={clearAll}
            disabled={disabled}
            style={{
              fontSize: 11,
              padding: "3px 8px",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              background: "#fff",
              color: "var(--color-text)",
              cursor: disabled ? "not-allowed" : "pointer",
              opacity: disabled ? 0.6 : 1,
            }}
          >
            Bỏ chọn
          </button>
        </div>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fill, minmax(220px, 1fr))",
          gap: 6,
        }}
      >
        {departments.map((dept) => {
          const checked = selectedSet.has(dept.id);
          return (
            <label
              key={dept.id}
              className={`${styles.drawerItem} ${checked ? styles.checked : ""}`}
              style={{
                margin: 0,
                padding: "8px 10px",
                opacity: dept.is_active ? 1 : 0.5,
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(dept.id)}
                disabled={disabled || !dept.is_active}
                style={{ marginTop: 2 }}
              />
              <div className={styles.drawerItemBody}>
                <strong style={{ fontSize: 13 }}>{dept.code}</strong>
                <small
                  style={{
                    color: "var(--color-text-muted)",
                    fontSize: 11,
                  }}
                >
                  {dept.name}
                </small>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
