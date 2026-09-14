"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Edit2,
  Lock,
  LockOpen,
  Plus,
  Search,
  ShieldCheck,
  ShieldPlus,
  Trash2,
  UserCog,
  Users,
  X,
} from "lucide-react";

import {
  userService,
  type CreateUserRequest,
  type PermissionSummary,
  type RoleSummary,
  type UserResponse,
} from "@/services/userService";
import {
  organizationService,
  type DepartmentResponse,
} from "@/services/organizationService";
import { permissionService } from "@/services/permissionService";
import { StatusBadge } from "@/components/ui";
import { ConfirmModal } from "./ConfirmModal";
import { RoleCreateModal } from "./RoleCreateModal";

import styles from "./AdminUsers.module.css";

interface RoleDrawerPayload {
  kind: "roles";
  user: UserResponse;
  currentRoles: RoleSummary[];
}
interface PermissionsDrawerPayload {
  kind: "permissions";
  user: UserResponse;
}
type DrawerState =
  | { kind: "closed" }
  | RoleDrawerPayload
  | PermissionsDrawerPayload;

type UserModalState =
  | { phase: "idle" }
  | { phase: "creating" }
  | { phase: "editing"; user: UserResponse }
  | { phase: "saving" }
  | { phase: "error"; message: string };

function isModalSaving(s: UserModalState): boolean {
  return s.phase === "saving";
}
function isModalError(s: UserModalState): s is { phase: "error"; message: string } {
  return s.phase === "error";
}
function isModalEditing(s: UserModalState): s is { phase: "editing"; user: UserResponse } {
  return s.phase === "editing";
}
function isModalCreating(s: UserModalState): boolean {
  return s.phase === "creating";
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function AdminUsers() {
  const [items, setItems] = useState<UserResponse[]>([]);
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);
  const [allRoles, setAllRoles] = useState<RoleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filterActive, setFilterActive] = useState<"all" | "active" | "inactive">("all");
  const [filterDept, setFilterDept] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalUsers, setTotalUsers] = useState(0);

  const [modal, setModal] = useState<UserModalState>({ phase: "idle" });
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formName, setFormName] = useState("");
  const [formDeptId, setFormDeptId] = useState<string>("");

  const [drawer, setDrawer] = useState<DrawerState>({ kind: "closed" });
  const [roleSelections, setRoleSelections] = useState<Set<string>>(new Set());
  const [userPermissions, setUserPermissions] = useState<PermissionSummary[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerSaving, setDrawerSaving] = useState(false);

  const [toast, setToast] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserResponse | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [roleCreateOpen, setRoleCreateOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [depts, roles] = await Promise.all([
          organizationService.list(),
          permissionService.listRoles(),
        ]);
        if (cancelled) return;
        setDepartments(depts);
        setAllRoles(roles);
      } catch {
        // Non-fatal; the admin can still load users.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        setLoading(true);
        const params: {
          page: number;
          page_size: number;
          search?: string;
          is_active?: boolean;
          department_id?: string;
        } = { page, page_size: pageSize };
        if (query.trim()) params.search = query.trim();
        if (filterActive !== "all") params.is_active = filterActive === "active";
        if (filterDept !== "all") params.department_id = filterDept;
        const data = await userService.list(params);
        if (cancelled) return;
        setItems(data.items);
        setTotalUsers(data.total);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message ?? "Không tải được danh sách người dùng.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [page, filterActive, filterDept, query]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  function openCreate() {
    setFormEmail("");
    setFormPassword("");
    setFormName("");
    setFormDeptId(departments[0]?.id ?? "");
    setModal({ phase: "creating" });
  }

  function openEdit(user: UserResponse) {
    setFormEmail(user.email);
    setFormPassword("");
    setFormName(user.full_name);
    setFormDeptId(user.department_id ?? "");
    setModal({ phase: "editing", user });
  }

  function closeUserModal() {
    if (isModalSaving(modal)) return;
    setModal({ phase: "idle" });
  }

  async function handleUserSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isModalEditing(modal) && !isModalCreating(modal)) return;

    const creating = isModalCreating(modal);
    const email = formEmail.trim();
    const fullName = formName.trim();
    const departmentId = formDeptId.trim() || null;

    if (!email) {
      setModal({ phase: "error", message: "Email không được để trống." });
      return;
    }
    if (!fullName) {
      setModal({ phase: "error", message: "Họ tên không được để trống." });
      return;
    }
    if (creating && formPassword.length < 8) {
      setModal({
        phase: "error",
        message: "Mật khẩu phải có ít nhất 8 ký tự.",
      });
      return;
    }

    setModal({ phase: "saving" });

    try {
      if (creating) {
        const body: CreateUserRequest = {
          email,
          password: formPassword,
          full_name: fullName,
          department_id: departmentId,
        };
        const created = await userService.create(body);
        setItems((prev) => [created, ...prev]);
        setTotalUsers((t) => t + 1);
        showToast(`Đã tạo người dùng "${created.full_name}".`);
      } else {
        if (!isModalEditing(modal)) return;
        const updated = await userService.update(modal.user.id, {
          email,
          full_name: fullName,
          department_id: departmentId,
        });
        setItems((prev) =>
          prev.map((u) => (u.id === updated.id ? updated : u)),
        );
        showToast(`Đã cập nhật người dùng "${updated.full_name}".`);
      }
      setModal({ phase: "idle" });
    } catch (err) {
      setModal({
        phase: "error",
        message: (err as Error).message ?? "Không thể lưu thay đ�i.",
      });
    }
  }

  async function toggleLock(user: UserResponse) {
    try {
      const updated = await userService.updateStatus(user.id, {
        is_active: !user.is_active,
      });
      setItems((prev) =>
        prev.map((u) => (u.id === updated.id ? updated : u)),
      );
      showToast(
        updated.is_active
          ? `Đã mở khóa tài khoản "${updated.full_name}".`
          : `Đã khóa tài khoản "${updated.full_name}".`,
      );
    } catch (err) {
      showToast((err as Error).message ?? "Không thể thay đổi trạng thái.");
    }
  }

  async function handleDeleteUser() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await userService.delete(deleteTarget.id);
      setItems((prev) => prev.filter((u) => u.id !== deleteTarget.id));
      showToast(`Đã xóa người dùng "${deleteTarget.full_name}".`);
      setDeleteTarget(null);
    } catch (err) {
      showToast((err as Error).message ?? "Không thể xóa người dùng.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleDeleteRole(roleId: string) {
    try {
      await permissionService.deleteRole(roleId);
      setAllRoles((prev) => prev.filter((r) => r.id !== roleId));
      showToast("Đã xóa vai trò.");
    } catch (err) {
      showToast((err as Error).message ?? "Không thể xóa vai trò.");
    }
  }

  async function openRoleDrawer(user: UserResponse) {
    setDrawer({ kind: "roles", user, currentRoles: [] });
    setRoleSelections(new Set());
    setDrawerLoading(true);
    try {
      const roles = await userService.listRoles(user.id);
      setRoleSelections(new Set(roles.map((r) => r.id)));
      setDrawer({ kind: "roles", user, currentRoles: roles });
    } catch (err) {
      showToast((err as Error).message ?? "Không tải được vai trò.");
      setDrawer({ kind: "closed" });
    } finally {
      setDrawerLoading(false);
    }
  }

  function toggleRoleSelection(roleId: string) {
    setRoleSelections((prev) => {
      const next = new Set(prev);
      if (next.has(roleId)) {
        next.delete(roleId);
      } else {
        next.add(roleId);
      }
      return next;
    });
  }

  async function saveRoles() {
    if (drawer.kind !== "roles") return;
    setDrawerSaving(true);
    try {
      const updated = await userService.updateRoles(
        drawer.user.id,
        Array.from(roleSelections),
      );
      showToast(
        `Đã cập nhật vai trò cho "${drawer.user.full_name}".`,
      );
      setDrawer({ kind: "roles", user: drawer.user, currentRoles: updated });
    } catch (err) {
      showToast((err as Error).message ?? "Không thể lưu vai trò.");
    } finally {
      setDrawerSaving(false);
    }
  }

  async function openPermissionsDrawer(user: UserResponse) {
    setDrawer({ kind: "permissions", user });
    setUserPermissions([]);
    setDrawerLoading(true);
    try {
      const perms = await userService.getPermissions(user.id);
      setUserPermissions(perms);
    } catch (err) {
      showToast((err as Error).message ?? "Không tải được quyền hiệu lực.");
    } finally {
      setDrawerLoading(false);
    }
  }

  function closeDrawer() {
    if (drawerSaving) return;
    setDrawer({ kind: "closed" });
  }

  // Client-side secondary filter for fast UX even when BE paginates.
  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    return items.filter((u) => {
      const matchQ =
        !q ||
        u.email.toLowerCase().includes(q) ||
        u.full_name.toLowerCase().includes(q);
      const matchActive =
        filterActive === "all" ||
        (filterActive === "active" && u.is_active) ||
        (filterActive === "inactive" && !u.is_active);
      const matchDept =
        filterDept === "all" || u.department_id === filterDept;
      return matchQ && matchActive && matchDept;
    });
  }, [items, query, filterActive, filterDept]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  const deptNameOf = (id: string | null): string => {
    if (!id) return "—";
    return departments.find((d) => d.id === id)?.code ?? "—";
  };

  if (loading && items.length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.empty}>
          <p>Đang tải danh sách người dùng…</p>
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

  const userModalSaving = isModalSaving(modal);

  return (
    <div className={styles.page}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Quản trị hệ thống</p>
          <h2>Quản lý người dùng</h2>
          <p>
            Quản lý tài khoản, vai trò và quyền hạn của người dùng trong hệ thống.
          </p>
        </div>
        <button className={styles.addButton} type="button" onClick={openCreate}>
          <Plus size={16} aria-hidden="true" /> Thêm người dùng
        </button>
        <button
          className={styles.addButton}
          type="button"
          onClick={() => setRoleCreateOpen(true)}
          style={{ background: "#fff", color: "var(--color-primary)", border: "1px solid var(--color-primary)" }}
        >
          <ShieldPlus size={16} aria-hidden="true" /> Tạo vai trò
        </button>
      </header>

      <section className={styles.tablePanel}>
        <div className={styles.toolbar}>
          <label className={styles.search}>
            <Search size={17} aria-hidden="true" />
            <span className="sr-only">Tìm người dùng</span>
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder="Tìm theo email hoặc họ tên…"
            />
          </label>
          <label className={styles.filter}>
            <span className="sr-only">Lọc trạng thái</span>
            <select
              value={filterActive}
              onChange={(e) => {
                setFilterActive(e.target.value as typeof filterActive);
                setPage(1);
              }}
            >
              <option value="all">Tất cả</option>
              <option value="active">Đang hoạt động</option>
              <option value="inactive">Đã khóa</option>
            </select>
          </label>
          <label className={styles.filter}>
            <span className="sr-only">Lọc đơn vị</span>
            <select
              value={filterDept}
              onChange={(e) => {
                setFilterDept(e.target.value);
                setPage(1);
              }}
            >
              <option value="all">Tất cả đơn vị</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Người dùng</th>
                <th>Đơn vị</th>
                <th>Trạng thái</th>
                <th><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className={styles.emailCell}>
                      <span className={styles.avatar} aria-hidden="true">
                        {getInitials(u.full_name || u.email)}
                      </span>
                      <div className={styles.nameCell}>
                        <strong>{u.full_name || "—"}</strong>
                        <small>{u.email}</small>
                      </div>
                    </div>
                  </td>
                  <td>{deptNameOf(u.department_id)}</td>
                  <td>
                    <StatusBadge
                      tone={u.is_active ? "success" : "warning"}
                      showDot
                    >
                      {u.is_active ? "Hoạt động" : "Đã khóa"}
                    </StatusBadge>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        type="button"
                        aria-label={`Phân quyền cho ${u.full_name}`}
                        className={styles.actionBtn}
                        onClick={() => openRoleDrawer(u)}
                        title="Phân quyền"
                      >
                        <ShieldCheck size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label={`Xem quyền hiệu lực của ${u.full_name}`}
                        className={styles.actionBtn}
                        onClick={() => openPermissionsDrawer(u)}
                        title="Quyền hiệu lực"
                      >
                        <UserCog size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label={`Sửa ${u.full_name}`}
                        className={styles.actionBtn}
                        onClick={() => openEdit(u)}
                        title="Sửa"
                      >
                        <Edit2 size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label={u.is_active ? `Khóa ${u.full_name}` : `Mở khóa ${u.full_name}`}
                        className={`${styles.actionBtn} ${u.is_active ? styles.lockedButton : styles.unlockButton}`}
                        onClick={() => toggleLock(u)}
                        title={u.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản"}
                      >
                        {u.is_active ? <Lock size={16} /> : <LockOpen size={16} />}
                      </button>
                      <button
                        type="button"
                        aria-label={`Xóa ${u.full_name}`}
                        className={`${styles.actionBtn} ${styles.deleteButton}`}
                        onClick={() => setDeleteTarget(u)}
                        title="Xóa người dùng"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <div className={styles.empty}>
              <Users size={32} aria-hidden="true" />
              <strong>Không tìm thấy người dùng</strong>
              <span>
                {query || filterActive !== "all" || filterDept !== "all"
                  ? "Thử thay đổi từ khóa hoặc bộ lọc."
                  : "Chưa có người dùng nào."}
              </span>
            </div>
          )}
        </div>

        <footer className={styles.tableFooter}>
          <span>
            Hiển thị {paged.length} trong tổng số {totalUsers || filtered.length} người dùng
          </span>
          <div className={styles.pagination}>
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Trước
            </button>
            {Array.from({ length: totalPages }).map((_, i) => (
              <button
                type="button"
                key={i}
                className={page === i + 1 ? styles.current : ""}
                onClick={() => setPage(i + 1)}
              >
                {i + 1}
              </button>
            ))}
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Sau
            </button>
          </div>
        </footer>
      </section>

      {/* User Create / Edit Modal */}
      {modal.phase !== "idle" && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !userModalSaving) {
              closeUserModal();
            }
          }}
        >
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-modal-title"
          >
            <div className={styles.modalHeader}>
              <div>
                <h2 id="user-modal-title">
                  {isModalCreating(modal)
                    ? "Thêm người dùng mới"
                    : "Sửa thông tin người dùng"}
                </h2>
                <p>
                  {isModalCreating(modal)
                    ? "Tạo tài khoản mới với email và mật khẩu tạm thời."
                    : isModalEditing(modal)
                    ? `Chỉnh sửa thông tin cho ${modal.user.email}.`
                    : ""}
                </p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng cửa sổ"
                onClick={closeUserModal}
                disabled={userModalSaving}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleUserSubmit}>
              <div className={styles.formBody}>
                <label>
                  Email
                  <input
                    type="email"
                    value={formEmail}
                    onChange={(e) => setFormEmail(e.target.value)}
                    placeholder="user@example.edu.vn"
                    maxLength={255}
                    disabled={userModalSaving}
                    required
                  />
                </label>

                {isModalCreating(modal) && (
                  <label>
                    Mật khẩu (tối thiểu 8 ký tự)
                    <input
                      type="password"
                      value={formPassword}
                      onChange={(e) => setFormPassword(e.target.value)}
                      placeholder="••••••••"
                      minLength={8}
                      maxLength={128}
                      disabled={userModalSaving}
                      required
                    />
                  </label>
                )}

                <label>
                  Họ và tên
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Nguyễn Văn A"
                    maxLength={255}
                    disabled={userModalSaving}
                    required
                  />
                </label>

                <label>
                  Đơn vị
                  <select
                    value={formDeptId}
                    onChange={(e) => setFormDeptId(e.target.value)}
                    disabled={userModalSaving}
                  >
                    <option value="">— Không có —</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.code} — {d.name}
                      </option>
                    ))}
                  </select>
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
                  onClick={closeUserModal}
                  disabled={userModalSaving}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className={styles.submitButton}
                  disabled={userModalSaving}
                >
                  {userModalSaving
                    ? "Đang lưu…"
                    : isModalCreating(modal)
                    ? "Tạo người dùng"
                    : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {/* Role assignment drawer */}
      {drawer.kind === "roles" && (
        <>
          <div className={styles.drawerBackdrop} onClick={closeDrawer} />
          <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="role-drawer-title">
            <div className={styles.drawerHeader}>
              <div>
                <h2 id="role-drawer-title">Phân quyền người dùng</h2>
                <p>{drawer.user.full_name} ({drawer.user.email})</p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng drawer"
                onClick={closeDrawer}
                disabled={drawerSaving}
              >
                <X size={20} />
              </button>
            </div>
            <div className={styles.drawerBody}>
              <div className={styles.drawerSection}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <h3>Vai trò khả dụng ({allRoles.length})</h3>
                  <button
                    type="button"
                    onClick={() => setRoleCreateOpen(true)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      padding: "4px 10px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 6,
                      background: "#fff",
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    <ShieldPlus size={13} /> Tạo mới
                  </button>
                </div>
                {drawerLoading ? (
                  <p>Đang tải…</p>
                ) : allRoles.length === 0 ? (
                  <p>Hệ thống chưa có vai trò nào.</p>
                ) : (
                  <div className={styles.drawerList}>
                    {allRoles.map((role) => {
                      const checked = roleSelections.has(role.id);
                      return (
                        <label
                          key={role.id}
                          className={`${styles.drawerItem} ${checked ? styles.checked : ""}`}
                          style={{ alignItems: "flex-start" }}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleRoleSelection(role.id)}
                            disabled={drawerSaving}
                            style={{ marginTop: 3 }}
                          />
                          <div className={styles.drawerItemBody} style={{ flex: 1 }}>
                            <strong>{role.name}</strong>
                            <small>{role.code}{role.description ? ` — ${role.description}` : ""}</small>
                          </div>
                          {role.is_system ? (
                            <span className={styles.drawerItemBadge}>Hệ thống</span>
                          ) : (
                            <button
                              type="button"
                              aria-label={`Xóa vai trò ${role.name}`}
                              onClick={(e) => {
                                e.preventDefault();
                                void handleDeleteRole(role.id);
                              }}
                              style={{
                                padding: "3px 8px",
                                border: "1px solid #dc2626",
                                borderRadius: 6,
                                background: "#fff",
                                color: "#dc2626",
                                fontSize: 11,
                                cursor: "pointer",
                              }}
                            >
                              Xóa
                            </button>
                          )}
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
            <div className={styles.drawerFooter}>
              <button
                type="button"
                className={styles.cancelButton}
                onClick={closeDrawer}
                disabled={drawerSaving}
              >
                Hủy
              </button>
              <button
                type="button"
                className={styles.submitButton}
                onClick={saveRoles}
                disabled={drawerSaving || drawerLoading}
              >
                {drawerSaving ? "Đang lưu…" : "Lưu vai trò"}
              </button>
            </div>
          </aside>
        </>
      )}

      {/* Effective permissions drawer */}
      {drawer.kind === "permissions" && (
        <>
          <div className={styles.drawerBackdrop} onClick={closeDrawer} />
          <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="perm-drawer-title">
            <div className={styles.drawerHeader}>
              <div>
                <h2 id="perm-drawer-title">Quyền hiệu lực</h2>
                <p>{drawer.user.full_name} ({drawer.user.email})</p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng drawer"
                onClick={closeDrawer}
              >
                <X size={20} />
              </button>
            </div>
            <div className={styles.drawerBody}>
              <div className={styles.drawerSection}>
                <h3>Danh sách quyền ({userPermissions.length})</h3>
                {drawerLoading ? (
                  <p>Đang tải…</p>
                ) : userPermissions.length === 0 ? (
                  <p>Người dùng chưa có quyền nào.</p>
                ) : (
                  <div className={styles.drawerList}>
                    {userPermissions.map((p) => (
                      <div key={p.id} className={styles.drawerItem}>
                        <div className={styles.drawerItemBody}>
                          <strong>{p.name}</strong>
                          <small>
                            {p.code}
                            {p.description ? ` — ${p.description}` : ""}
                          </small>
                        </div>
                        <span className={styles.drawerItemBadge}>{p.module}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className={styles.drawerFooter}>
              <button
                type="button"
                className={styles.cancelButton}
                onClick={closeDrawer}
              >
                Đóng
              </button>
            </div>
          </aside>
        </>
      )}

      {toast && <p className={styles.toast} role="status">{toast}</p>}

      {/* Delete user confirmation */}
      <ConfirmModal
        open={deleteTarget !== null}
        title={`Xóa người dùng "${deleteTarget?.full_name ?? ""}"`}
        message="Hành động này sẽ xóa vĩnh viễn tài khoản người dùng và không thể hoàn tác."
        impacts={[
          "Xóa vĩnh viễn tài khoản khỏi hệ thống.",
          "Người dùng sẽ không thể đăng nhập.",
          "Xóa tất cả refresh tokens và vai trò liên quan.",
          "Xóa lịch sử chat và các bản ghi hoạt động.",
        ]}
        confirmLabel="Xóa vĩnh viễn"
        destructive
        busy={deleting}
        onConfirm={handleDeleteUser}
        onClose={() => setDeleteTarget(null)}
      />

      {/* Role create modal */}
      <RoleCreateModal
        open={roleCreateOpen}
        onClose={() => setRoleCreateOpen(false)}
        onCreated={() => {
          showToast("Đã tạo vai trò mới.");
          // Refresh the roles list so the new role appears in the drawer.
          permissionService.listRoles().then((roles) => {
            setAllRoles(roles);
          });
        }}
      />
    </div>
  );
}
