"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Building2, Edit2, Plus, Search, X } from "lucide-react";

import {
  organizationService,
  type DepartmentResponse,
  type UpdateDepartmentRequest,
} from "@/services/organizationService";
import { StatusBadge } from "@/components/ui";

import styles from "./AdminOrganizations.module.css";

interface IdleState { phase: "idle" }
interface CreatingState { phase: "creating" }
interface EditingState { phase: "editing"; department: DepartmentResponse }
interface SavingState { phase: "saving" }
interface ModalErrorState { phase: "error"; message: string }

type ModalState = IdleState | CreatingState | EditingState | SavingState | ModalErrorState;

type DeleteState = "idle" | "confirming" | "deleting" | "success" | "error";

function isSaving(s: ModalState): boolean {
  return s.phase === "saving";
}

function isError(s: ModalState): s is ModalErrorState {
  return s.phase === "error";
}

function isEditing(s: ModalState): s is EditingState {
  return s.phase === "editing";
}

function isCreating(s: ModalState): s is CreatingState {
  return s.phase === "creating";
}

export function AdminOrganizations() {
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filterActive, setFilterActive] = useState<"all" | "active" | "inactive">("all");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  const [modal, setModal] = useState<ModalState>({ phase: "idle" });
  const [formName, setFormName] = useState("");
  const [formCode, setFormCode] = useState("");
  const [formActive, setFormActive] = useState(true);

  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await organizationService.list();
        if (cancelled) return;
        setDepartments(data);
      } catch (e) {
        if (!cancelled) setError((e as Error).message ?? "Không tải được danh sách đơn vị.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    return departments.filter((d) => {
      const matchQ =
        !q ||
        d.code.toLowerCase().includes(q) ||
        d.name.toLowerCase().includes(q);
      const matchActive =
        filterActive === "all" ||
        (filterActive === "active" && d.is_active) ||
        (filterActive === "inactive" && !d.is_active);
      return matchQ && matchActive;
    });
  }, [departments, query, filterActive]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  // Reset page when filter changes
  useEffect(() => {
    setPage(1);
  }, [query, filterActive]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  function openCreate() {
    setFormCode("");
    setFormName("");
    setFormActive(true);
    setModal({ phase: "creating" });
  }

  function openEdit(dept: DepartmentResponse) {
    setFormCode(dept.code);
    setFormName(dept.name);
    setFormActive(dept.is_active);
    setModal({ phase: "editing", department: dept });
  }

  function closeModal() {
    if (isSaving(modal)) return;
    setModal({ phase: "idle" });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const name = formName.trim();
    if (!name) {
      setModal({ phase: "error", message: "Tên đơn vị không được để trống." });
      return;
    }

    setModal({ phase: "saving" });

    try {
      if (isCreating(modal)) {
        const code = formCode.trim().toUpperCase();
        if (!code) {
          setModal({ phase: "error", message: "Mã đơn vị không được để trống." });
          return;
        }
        await organizationService.create({ code, name });
        showToast(`Đã tạo đơn vị "${name}".`);
      } else if (isEditing(modal)) {
        const update: UpdateDepartmentRequest = { name, is_active: formActive };
        const updated = await organizationService.update(modal.department.id, update);
        setDepartments((prev) =>
          prev.map((d) => (d.id === updated.id ? updated : d)),
        );
        showToast(`Đã cập nhật đơn vị "${name}".`);
      }

      // Refresh full list to ensure consistency
      const refreshed = await organizationService.list();
      setDepartments(refreshed);

      setModal({ phase: "idle" });
    } catch (err) {
      setModal({
        phase: "error",
        message:
          (err as Error).message ?? "Không thể lưu thay đổi. Vui lòng thử lại.",
      });
    }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.empty}>
          <p>Đang tải danh sách đơn vị…</p>
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

  const modalSaving = isSaving(modal);

  return (
    <div className={styles.page}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Quản trị hệ thống</p>
          <h2>Quản lý đơn vị</h2>
          <p>
            Quản lý thông tin các đơn vị (trường, khoa, phòng ban) trong hệ thống.
          </p>
        </div>
        <button className={styles.addButton} type="button" onClick={openCreate}>
          <Plus size={16} aria-hidden="true" /> Thêm đơn vị
        </button>
      </header>

      <section className={styles.tablePanel}>
        <div className={styles.toolbar}>
          <label className={styles.search}>
            <Search size={17} aria-hidden="true" />
            <span className="sr-only">Tìm đơn vị</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm theo mã hoặc tên đơn vị…"
            />
          </label>
          <label className={styles.filter}>
            <span className="sr-only">Lọc trạng thái</span>
            <select
              value={filterActive}
              onChange={(e) => setFilterActive(e.target.value as typeof filterActive)}
            >
              <option value="all">Tất cả</option>
              <option value="active">Đang hoạt động</option>
              <option value="inactive">Không hoạt động</option>
            </select>
          </label>
        </div>

        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Mã đơn vị</th>
                <th>Tên đơn vị</th>
                <th>Trạng thái</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((dept) => (
                <tr key={dept.id}>
                  <td>
                    <span className={styles.codeCell}>{dept.code}</span>
                  </td>
                  <td className={styles.nameCell}>
                    <strong>{dept.name}</strong>
                  </td>
                  <td>
                    <StatusBadge
                      tone={dept.is_active ? "success" : "neutral"}
                      showDot
                    >
                      {dept.is_active ? "Hoạt động" : "Không hoạt động"}
                    </StatusBadge>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        type="button"
                        aria-label={`Sửa ${dept.name}`}
                        className={styles.actionBtn}
                        onClick={() => openEdit(dept)}
                      >
                        <Edit2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <div className={styles.empty}>
              <Building2 size={32} aria-hidden="true" />
              <strong>Không tìm thấy đơn vị</strong>
              <span>
                {query || filterActive !== "all"
                  ? "Thử thay đổi từ khóa hoặc bộ lọc."
                  : "Chưa có đơn vị nào. Nhấn 'Thêm đơn vị' để bắt đầu."}
              </span>
            </div>
          )}
        </div>

        <footer className={styles.tableFooter}>
          <span>
            Hiển thị {paged.length} trong tổng số {filtered.length} đơn vị
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

      {/* Create / Edit Modal */}
      {modal.phase !== "idle" && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !modalSaving) {
              closeModal();
            }
          }}
        >
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="dept-modal-title"
          >
            <div className={styles.modalHeader}>
              <div>
                <h2 id="dept-modal-title">
                  {isCreating(modal) ? "Thêm đơn vị mới" : "Sửa thông tin đơn vị"}
                </h2>
                <p>
                  {isCreating(modal)
                    ? "Tạo một đơn vị mới trong hệ thống."
                    : `Chỉnh sửa thông tin cho ${isEditing(modal) ? modal.department.code : ""}.`}
                </p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng cửa sổ"
                onClick={closeModal}
                disabled={modalSaving}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className={styles.formBody}>
                {isCreating(modal) && (
                  <label>
                    Mã đơn vị
                    <input
                      value={formCode}
                      onChange={(e) => setFormCode(e.target.value)}
                      placeholder="Ví dụ: HUST, HUCE"
                      maxLength={20}
                      disabled={modalSaving}
                      required
                    />
                  </label>
                )}

                {isEditing(modal) && (
                  <label>
                    Mã đơn vị
                    <input
                      value={formCode}
                      disabled
                      readOnly
                      title="Mã đơn vị không thể thay đổi."
                    />
                  </label>
                )}

                <label>
                  Tên đơn vị
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Ví dụ: Đại học Bách khoa Hà Nội"
                    maxLength={255}
                    disabled={modalSaving}
                    required
                  />
                </label>

                {isEditing(modal) && (
                  <div className={styles.checkboxRow}>
                    <input
                      type="checkbox"
                      id="is-active-checkbox"
                      checked={formActive}
                      onChange={(e) => setFormActive(e.target.checked)}
                      disabled={modalSaving}
                    />
                    <label htmlFor="is-active-checkbox">Đơn vị đang hoạt động</label>
                  </div>
                )}

                {isError(modal) && (
                  <p className={styles.formError} role="alert">
                    {modal.message}
                  </p>
                )}
              </div>

              <div className={styles.modalActions}>
                <button
                  type="button"
                  className={styles.cancelButton}
                  onClick={closeModal}
                  disabled={modalSaving}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className={styles.submitButton}
                  disabled={modalSaving}
                >
                  {modalSaving
                    ? "Đang lưu…"
                    : isCreating(modal)
                    ? "Tạo đơn vị"
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
