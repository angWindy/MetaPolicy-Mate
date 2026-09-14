"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Edit2, KeyRound, Link2, Plus, Search, Shield, X } from "lucide-react";

import {
  permissionService,
  type CreateRoleRequest,
} from "@/services/permissionService";
import type {
  PermissionSummary,
  RoleSummary,
} from "@/services/userService";
import { StatusBadge } from "@/components/ui";

import styles from "./AdminPermissions.module.css";

type TabKey = "roles" | "permissions" | "mapping";

type RoleModalState =
  | { phase: "idle" }
  | { phase: "creating" }
  | { phase: "editing"; role: RoleSummary }
  | { phase: "saving" }
  | { phase: "error"; message: string };

function isModalSaving(s: RoleModalState): boolean {
  return s.phase === "saving";
}
function isModalError(s: RoleModalState): s is { phase: "error"; message: string } {
  return s.phase === "error";
}
function isModalCreating(s: RoleModalState): boolean {
  return s.phase === "creating";
}
function isModalEditing(s: RoleModalState): s is { phase: "editing"; role: RoleSummary } {
  return s.phase === "editing";
}

export function AdminPermissions() {
  const [tab, setTab] = useState<TabKey>("roles");

  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [permissions, setPermissions] = useState<PermissionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [filterModule, setFilterModule] = useState<string>("all");

  const [modal, setModal] = useState<RoleModalState>({ phase: "idle" });
  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");

  // Mapping tab state
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [rolePermissions, setRolePermissions] = useState<PermissionSummary[]>([]);
  const [permSelections, setPermSelections] = useState<Set<string>>(new Set());
  const [mappingLoading, setMappingLoading] = useState(false);
  const [mappingSaving, setMappingSaving] = useState(false);

  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [r, p] = await Promise.all([
          permissionService.listRoles(),
          permissionService.listPermissions(),
        ]);
        if (cancelled) return;
        setRoles(r);
        setPermissions(p);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message ?? "Không tải được dữ liệu.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredRoles = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return roles;
    return roles.filter(
      (r) =>
        r.code.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q),
    );
  }, [roles, query]);

  const modules = useMemo(() => {
    const seen = new Set<string>();
    permissions.forEach((p) => seen.add(p.module));
    return Array.from(seen).sort();
  }, [permissions]);

  const filteredPermissions = useMemo(() => {
    const q = query.toLowerCase().trim();
    return permissions.filter((p) => {
      const matchQ =
        !q ||
        p.code.toLowerCase().includes(q) ||
        p.name.toLowerCase().includes(q);
      const matchModule = filterModule === "all" || p.module === filterModule;
      return matchQ && matchModule;
    });
  }, [permissions, query, filterModule]);

  const permsByModule = useMemo(() => {
    const grouped = new Map<string, PermissionSummary[]>();
    for (const p of filteredPermissions) {
      const arr = grouped.get(p.module) ?? [];
      arr.push(p);
      grouped.set(p.module, arr);
    }
    return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filteredPermissions]);

  // Group ALL permissions by module for the mapping tab
  const allPermsByModule = useMemo(() => {
    const grouped = new Map<string, PermissionSummary[]>();
    for (const p of permissions) {
      const arr = grouped.get(p.module) ?? [];
      arr.push(p);
      grouped.set(p.module, arr);
    }
    return Array.from(grouped.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [permissions]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  function openCreate() {
    setFormCode("");
    setFormName("");
    setFormDescription("");
    setModal({ phase: "creating" });
  }

  function openEditRole(role: RoleSummary) {
    setFormCode(role.code);
    setFormName(role.name);
    setFormDescription(role.description ?? "");
    setModal({ phase: "editing", role });
  }

  function closeRoleModal() {
    if (isModalSaving(modal)) return;
    setModal({ phase: "idle" });
  }

  async function handleRoleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isModalCreating(modal) && !isModalEditing(modal)) return;

    const creating = isModalCreating(modal);
    const code = formCode.trim().toUpperCase();
    const name = formName.trim();

    if (!code) {
      setModal({ phase: "error", message: "Mã vai trò không được để trống." });
      return;
    }
    if (!name) {
      setModal({ phase: "error", message: "Tên vai trò không được để trống." });
      return;
    }

    setModal({ phase: "saving" });

    try {
      if (creating) {
        const body: CreateRoleRequest = {
          code,
          name,
          description: formDescription.trim() || null,
        };
        const created = await permissionService.createRole(body);
        setRoles((prev) => [...prev, created]);
        showToast(`Đã tạo vai trò "${created.name}".`);
      } else if (isModalEditing(modal)) {
        const updated = await permissionService.updateRole(modal.role.id, {
          name,
          description: formDescription.trim() || null,
        });
        setRoles((prev) =>
          prev.map((r) => (r.id === updated.id ? updated : r)),
        );
        showToast(`Đã cập nhật vai trò "${updated.name}".`);
      }
      setModal({ phase: "idle" });
    } catch (err) {
      setModal({
        phase: "error",
        message: (err as Error).message ?? "Không thể lưu thay đổi.",
      });
    }
  }

  async function loadRolePermissions(roleId: string) {
    setMappingLoading(true);
    try {
      const perms = await permissionService.getRolePermissions(roleId);
      setRolePermissions(perms);
      setPermSelections(new Set(perms.map((p) => p.id)));
    } catch (err) {
      showToast((err as Error).message ?? "Không tải được quyền của vai trò.");
    } finally {
      setMappingLoading(false);
    }
  }

  function selectRole(roleId: string) {
    setSelectedRoleId(roleId);
    void loadRolePermissions(roleId);
  }

  function togglePerm(permId: string) {
    setPermSelections((prev) => {
      const next = new Set(prev);
      if (next.has(permId)) {
        next.delete(permId);
      } else {
        next.add(permId);
      }
      return next;
    });
  }

  async function saveMapping() {
    if (!selectedRoleId) return;
    setMappingSaving(true);
    try {
      const updated = await permissionService.updateRolePermissions(
        selectedRoleId,
        Array.from(permSelections),
      );
      setRolePermissions(updated);
      showToast("Đã lưu phân quyền cho vai trò.");
    } catch (err) {
      showToast((err as Error).message ?? "Không thể lưu phân quyền.");
    } finally {
      setMappingSaving(false);
    }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.empty}>
          <p>Đang tải dữ liệu…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.page}>
        <div className={styles.empty}>
          <strong>Lỗi</strong>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  const selectedRole = roles.find((r) => r.id === selectedRoleId);

  return (
    <div className={styles.page}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Quản trị hệ thống</p>
          <h2>Phân quyền</h2>
          <p>
            Quản lý vai trò và ánh xạ vai trò ↔ quyền trong hệ thống.
          </p>
        </div>
      </header>

      <div className={styles.tabs} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "roles"}
          className={`${styles.tab} ${tab === "roles" ? styles.tabActive : ""}`}
          onClick={() => setTab("roles")}
        >
          <Shield size={15} aria-hidden="true" /> Vai trò ({roles.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "permissions"}
          className={`${styles.tab} ${tab === "permissions" ? styles.tabActive : ""}`}
          onClick={() => setTab("permissions")}
        >
          <KeyRound size={15} aria-hidden="true" /> Quyền ({permissions.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "mapping"}
          className={`${styles.tab} ${tab === "mapping" ? styles.tabActive : ""}`}
          onClick={() => setTab("mapping")}
        >
          <Link2 size={15} aria-hidden="true" /> Vai trò ↔ Quyền
        </button>
      </div>

      {tab === "roles" && (
        <section className={styles.panel}>
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              <label className={styles.search}>
                <Search size={17} aria-hidden="true" />
                <span className="sr-only">Tìm vai trò</span>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm theo mã hoặc tên vai trò…"
                />
              </label>
            </div>
            <button className={styles.addButton} type="button" onClick={openCreate}>
              <Plus size={16} aria-hidden="true" /> Thêm vai trò
            </button>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Mã vai trò</th>
                  <th>Tên vai trò</th>
                  <th>Loại</th>
                  <th>Mô tả</th>
                  <th><span className="sr-only">Thao tác</span></th>
                </tr>
              </thead>
              <tbody>
                {filteredRoles.map((role) => (
                  <tr key={role.id}>
                    <td>
                      <span className={styles.codeCell}>{role.code}</span>
                    </td>
                    <td className={styles.nameCell}>
                      <strong>{role.name}</strong>
                    </td>
                    <td>
                      {role.is_system ? (
                        <StatusBadge tone="warning" showDot>
                          Hệ thống
                        </StatusBadge>
                      ) : (
                        <StatusBadge tone="info" showDot>
                          Tùy chỉnh
                        </StatusBadge>
                      )}
                    </td>
                    <td>{role.description || "—"}</td>
                    <td>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          aria-label={`Sửa ${role.name}`}
                          className={styles.actionBtn}
                          onClick={() => openEditRole(role)}
                          disabled={role.is_system}
                          title={role.is_system ? "Vai trò hệ thống không thể sửa" : "Sửa"}
                        >
                          <Edit2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredRoles.length === 0 && (
              <div className={styles.empty}>
                <Shield size={32} aria-hidden="true" />
                <strong>Không tìm thấy vai trò</strong>
                <span>Thử thay đổi từ khóa hoặc tạo vai trò mới.</span>
              </div>
            )}
          </div>
        </section>
      )}

      {tab === "permissions" && (
        <section className={styles.panel}>
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              <label className={styles.search}>
                <Search size={17} aria-hidden="true" />
                <span className="sr-only">Tìm quyền</span>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Tìm theo mã hoặc tên quyền…"
                />
              </label>
              <label className={styles.search}>
                <span className="sr-only">Lọc module</span>
                <select
                  value={filterModule}
                  onChange={(e) => setFilterModule(e.target.value)}
                  style={{
                    border: "none",
                    background: "transparent",
                    padding: "10px 0",
                    fontSize: 13,
                    color: "var(--color-text)",
                    outline: "none",
                    minWidth: 180,
                  }}
                >
                  <option value="all">Tất cả module</option>
                  {modules.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Mã quyền</th>
                  <th>Tên quyền</th>
                  <th>Module</th>
                  <th>Mô tả</th>
                </tr>
              </thead>
              <tbody>
                {filteredPermissions.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className={styles.codeCell}>{p.code}</span>
                    </td>
                    <td className={styles.nameCell}>
                      <strong>{p.name}</strong>
                    </td>
                    <td>
                      <StatusBadge tone="info">{p.module}</StatusBadge>
                    </td>
                    <td>{p.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filteredPermissions.length === 0 && (
              <div className={styles.empty}>
                <KeyRound size={32} aria-hidden="true" />
                <strong>Không tìm thấy quyền</strong>
                <span>Thử thay đổi từ khóa hoặc bộ lọc module.</span>
              </div>
            )}
          </div>
        </section>
      )}

      {tab === "mapping" && (
        <section className={styles.panel}>
          <div className={styles.mappingLayout}>
            <aside className={styles.mappingSidebar}>
              <h3>Vai trò ({roles.length})</h3>
              <div className={styles.roleList}>
                {roles.map((role) => (
                  <button
                    type="button"
                    key={role.id}
                    className={`${styles.roleItem} ${
                      selectedRoleId === role.id ? styles.roleItemActive : ""
                    }`}
                    onClick={() => selectRole(role.id)}
                  >
                    <strong>{role.name}</strong>
                    <small>{role.code}</small>
                    {role.is_system && (
                      <span className={styles.roleItemBadge}>Hệ thống</span>
                    )}
                  </button>
                ))}
              </div>
            </aside>
            <div className={styles.mappingBody}>
              {selectedRole ? (
                <>
                  <div className={styles.mappingHeader}>
                    <div>
                      <h3>{selectedRole.name}</h3>
                      <p>
                        {selectedRole.code} · đã chọn {permSelections.size}/{permissions.length} quyền
                      </p>
                    </div>
                    <button
                      type="button"
                      className={styles.submitButton}
                      onClick={saveMapping}
                      disabled={mappingSaving || mappingLoading}
                    >
                      {mappingSaving ? "Đang lưu…" : "Lưu phân quyền"}
                    </button>
                  </div>
                  {mappingLoading ? (
                    <p>Đang tải…</p>
                  ) : (
                    allPermsByModule.map(([module, perms]) => (
                      <div key={module} className={styles.moduleGroup}>
                        <div className={styles.moduleHeader}>
                          <h4>{module}</h4>
                          <small>{perms.length} quyền</small>
                        </div>
                        <div className={styles.permList}>
                          {perms.map((p) => {
                            const checked = permSelections.has(p.id);
                            return (
                              <label
                                key={p.id}
                                className={styles.permItem}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => togglePerm(p.id)}
                                  disabled={mappingSaving}
                                />
                                <div className={styles.permItemBody}>
                                  <strong>{p.name}</strong>
                                  <small>{p.code}{p.description ? ` — ${p.description}` : ""}</small>
                                </div>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))
                  )}
                </>
              ) : (
                <div className={styles.empty}>
                  <Link2 size={32} aria-hidden="true" />
                  <strong>Chọn một vai trò</strong>
                  <span>Chọn vai trò bên trái để xem và chỉnh phân quyền.</span>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Role Create / Edit Modal */}
      {modal.phase !== "idle" && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !isModalSaving(modal)) {
              closeRoleModal();
            }
          }}
        >
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="role-modal-title"
          >
            <div className={styles.modalHeader}>
              <div>
                <h2 id="role-modal-title">
                  {isModalCreating(modal)
                    ? "Thêm vai trò mới"
                    : "Sửa vai trò"}
                </h2>
                <p>
                  {isModalCreating(modal)
                    ? "Tạo vai trò tùy chỉnh cho hệ thống."
                    : `Chỉnh sửa vai trò ${isModalEditing(modal) ? modal.role.code : ""}.`}
                </p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng cửa sổ"
                onClick={closeRoleModal}
                disabled={isModalSaving(modal)}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleRoleSubmit}>
              <div className={styles.formBody}>
                <label>
                  Mã vai trò
                  <input
                    value={formCode}
                    onChange={(e) => setFormCode(e.target.value)}
                    placeholder="Ví dụ: STAFF_VIEWER"
                    maxLength={100}
                    disabled={isModalSaving(modal) || isModalEditing(modal)}
                    required
                  />
                </label>

                <label>
                  Tên vai trò
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Tên hiển thị"
                    maxLength={255}
                    disabled={isModalSaving(modal)}
                    required
                  />
                </label>

                <label>
                  Mô tả
                  <textarea
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    placeholder="Mô tả ngắn về vai trò (tùy chọn)"
                    maxLength={500}
                    rows={3}
                    disabled={isModalSaving(modal)}
                  />
                </label>

                {isModalError(modal) && (
                  <p className={styles.formError} role="alert">
                    {modal.message}
                  </p>
                )}
              </div>

              <div className={styles.modalActions}>
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={closeRoleModal}
                  disabled={isModalSaving(modal)}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className={styles.submitButton}
                  disabled={isModalSaving(modal)}
                >
                  {isModalSaving(modal)
                    ? "Đang lưu…"
                    : isModalCreating(modal)
                    ? "Tạo vai trò"
                    : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {toast && <p className={styles.toast} role="status">{toast}</p>}
    </div>
  );
}
