"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ShieldPlus, X } from "lucide-react";

import { permissionService } from "@/services/permissionService";
import type { PermissionSummary } from "@/services/userService";

import styles from "./AdminUsers.module.css";

interface RoleCreateModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

type SubmitState =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "error"; message: string };

function validateCode(code: string): string | null {
  const trimmed = code.trim();
  if (!trimmed) return "Mã vai trò không được để trống.";
  if (!/^[A-Z0-9_]+$/.test(trimmed)) {
    return "Mã vai trò chỉ gồm chữ IN HOA, số và dấu gạch dưới.";
  }
  return null;
}

export function RoleCreateModal({
  open,
  onClose,
  onCreated,
}: RoleCreateModalProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissions, setPermissions] = useState<PermissionSummary[]>([]);
  const [selectedPermissions, setSelectedPermissions] = useState<Set<string>>(
    new Set(),
  );
  const [loadingPerms, setLoadingPerms] = useState(false);
  const [submitState, setSubmitState] = useState<SubmitState>({
    phase: "idle",
  });

  // Reset form on open + load permissions.
  useEffect(() => {
    if (!open) return;
    setCode("");
    setName("");
    setDescription("");
    setSelectedPermissions(new Set());
    setSubmitState({ phase: "idle" });

    let cancelled = false;
    (async () => {
      try {
        setLoadingPerms(true);
        const all = await permissionService.listPermissions();
        if (cancelled) return;
        setPermissions(all);
      } catch (e) {
        if (!cancelled) {
          setSubmitState({
            phase: "error",
            message:
              (e as Error).message ?? "Không tải được danh sách quyền.",
          });
        }
      } finally {
        if (!cancelled) setLoadingPerms(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  function togglePermission(id: string) {
    setSelectedPermissions((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function permissionsByModule(): Map<string, PermissionSummary[]> {
    const grouped = new Map<string, PermissionSummary[]>();
    for (const perm of permissions) {
      const list = grouped.get(perm.module) ?? [];
      list.push(perm);
      grouped.set(perm.module, list);
    }
    return grouped;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const codeError = validateCode(code);
    if (codeError) {
      setSubmitState({ phase: "error", message: codeError });
      return;
    }
    const trimmedName = name.trim();
    if (!trimmedName) {
      setSubmitState({
        phase: "error",
        message: "Tên hiển thị không được để trống.",
      });
      return;
    }

    setSubmitState({ phase: "saving" });

    try {
      const created = await permissionService.createRole({
        code: code.trim(),
        name: trimmedName,
        description: description.trim() || null,
      });

      // If the role came back with id and we have permission selections,
      // sync the permission set via PUT /rbac/roles/{id}/permissions.
      if (selectedPermissions.size > 0) {
        await permissionService.updateRolePermissions(
          created.id,
          Array.from(selectedPermissions),
        );
      }

      onCreated();
      onClose();
    } catch (e) {
      setSubmitState({
        phase: "error",
        message: (e as Error).message ?? "Không thể tạo vai trò.",
      });
    }
  }

  const saving = submitState.phase === "saving";
  const groupedPerms = permissionsByModule();

  if (!open) return null;

  return (
    <div
      className={styles.modalBackdrop}
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
    >
      <section
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="role-create-title"
        style={{ maxWidth: 640 }}
      >
        <div className={styles.modalHeader}>
          <div>
            <h2 id="role-create-title">
              <ShieldPlus
                size={18}
                aria-hidden="true"
                style={{ verticalAlign: "-3px", marginRight: 8 }}
              />
              Tạo vai trò mới
            </h2>
            <p>
              Mã vai trò chỉ gồm chữ IN HOA, số và dấu gạch dưới. Sau khi tạo,
              có thể gán cho người dùng từ drawer "Phân quyền".
            </p>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            aria-label="Đóng cửa sổ"
            onClick={onClose}
            disabled={saving}
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className={styles.formBody}>
            <label>
              Mã vai trò (code)
              <input
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="VD: TCCB_STAFF"
                maxLength={100}
                disabled={saving}
                required
              />
            </label>

            <label>
              Tên hiển thị
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nhân viên phòng TCCB"
                maxLength={255}
                disabled={saving}
                required
              />
            </label>

            <label>
              Mô tả
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Mô tả ngắn về vai trò (không bắt buộc)"
                maxLength={500}
                disabled={saving}
                rows={2}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  fontFamily: "inherit",
                  fontSize: 13,
                  resize: "vertical",
                }}
              />
            </label>

            <div>
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 8,
                }}
              >
                Gán quyền ({selectedPermissions.size}/{permissions.length})
              </label>
              {loadingPerms ? (
                <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                  Đang tải danh sách quyền…
                </p>
              ) : (
                <div
                  style={{
                    maxHeight: 240,
                    overflowY: "auto",
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    padding: 10,
                  }}
                >
                  {Array.from(groupedPerms.entries()).map(
                    ([module, perms]) => (
                      <div key={module} style={{ marginBottom: 12 }}>
                        <div
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: "var(--color-text-muted)",
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            marginBottom: 4,
                          }}
                        >
                          {module}
                        </div>
                        {perms.map((perm) => (
                          <label
                            key={perm.id}
                            style={{
                              display: "flex",
                              alignItems: "flex-start",
                              gap: 8,
                              padding: "6px 8px",
                              borderRadius: 6,
                              cursor: "pointer",
                              fontSize: 13,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={selectedPermissions.has(perm.id)}
                              onChange={() => togglePermission(perm.id)}
                              disabled={saving}
                              style={{ marginTop: 2 }}
                            />
                            <div>
                              <div style={{ fontWeight: 500 }}>{perm.name}</div>
                              <small
                                style={{
                                  color: "var(--color-text-muted)",
                                  fontSize: 11,
                                }}
                              >
                                {perm.code}
                              </small>
                            </div>
                          </label>
                        ))}
                      </div>
                    ),
                  )}
                </div>
              )}
            </div>

            {submitState.phase === "error" && (
              <p className={styles.formError} role="alert">
                {submitState.message}
              </p>
            )}
          </div>

          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.cancelButton}
              onClick={onClose}
              disabled={saving}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={saving}
            >
              {saving ? "Đang tạo…" : "Tạo vai trò"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
