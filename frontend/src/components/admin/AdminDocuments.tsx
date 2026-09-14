"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  CheckCircle2,
  Edit2,
  Eye,
  FileText,
  MoreVertical,
  Search,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import {
  adminService,
  type AdminDocumentDetail,
  type AdminDocumentVersion,
  type UpdateDocumentMetadataRequest,
  type DocumentAccess,
} from "@/services/adminService";
import type { AdminDocument, AdminDocumentStatus, AdminStats } from "@/types/admin";
import { organizationService, type DepartmentResponse } from "@/services/organizationService";
import { StatusBadge } from "@/components/ui";
import { DepartmentMultiSelect } from "./DepartmentMultiSelect";

import styles from "./AdminDocuments.module.css";

const statusMap: Record<
  AdminDocumentStatus,
  { label: string; tone: "neutral" | "success" | "warning" | "danger" }
> = {
  DANG_HIEU_LUC: { label: "Đang hiệu lực", tone: "success" },
  CHO_XU_LY_NOI_DUNG: { label: "Chờ xử lý nội dung", tone: "warning" },
  HET_HIEU_LUC: { label: "Hết hiệu lực", tone: "danger" },
  BI_THAY_THE: { label: "Bị thay thế", tone: "neutral" },
  BAN_NHAP: { label: "Bản nháp", tone: "neutral" },
};

const LEGAL_STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "draft", label: "Bản nháp" },
  { value: "scheduled", label: "Đã lên lịch" },
  { value: "effective", label: "Đang hiệu lực" },
  { value: "superseded", label: "Bị thay thế" },
  { value: "expired", label: "Hết hiệu lực" },
  { value: "revoked", label: "Đã thu hồi" },
];

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "success"; message: string }
  | { phase: "error"; message: string };

type DrawerState =
  | { phase: "idle" }
  | { phase: "loading"; documentId: string }
  | { phase: "ready"; documentId: string; detail: AdminDocumentDetail; versions: AdminDocumentVersion[]; errorMessage: string | null }
  | { phase: "saving"; documentId: string; detail: AdminDocumentDetail; versions: AdminDocumentVersion[]; errorMessage: string | null };

function isDrawerReady(
  d: DrawerState,
): d is { phase: "ready" | "saving"; documentId: string; detail: AdminDocumentDetail; versions: AdminDocumentVersion[]; errorMessage: string | null } {
  return d.phase === "ready" || d.phase === "saving";
}

async function refreshList(setDocs: (value: AdminDocument[]) => void) {
  const list = await adminService.listDocuments();
  setDocs(list.items);
}

/** Read JWT roles from localStorage; mirrors AdminDocuments legacy logic. */
function readRolesFromBrowser(): Set<string> {
  const next = new Set<string>();
  const devRoles = process.env.NEXT_PUBLIC_DEV_ROLES;
  if (devRoles) {
    devRoles.split(",").map((r) => r.trim()).filter(Boolean).forEach((r) => next.add(r));
  }
  if (typeof window !== "undefined") {
    try {
      const token = window.localStorage.getItem("policymate_access_token");
      if (token) {
        const parts = token.split(".");
        if (parts.length >= 2) {
          const payload = JSON.parse(
            atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")),
          );
          if (typeof payload.role === "string") next.add(payload.role);
          if (typeof payload.Role === "string") next.add(payload.Role);
        }
      }
    } catch {
      // ignore malformed tokens
    }
  }
  return next;
}

function useCurrentRoles(): Set<string> {
  return useState<Set<string>>(readRolesFromBrowser)[0];
}

export function AdminDocuments() {
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | AdminDocumentStatus>("all");
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(20);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadState, setUploadState] = useState<UploadState>({ phase: "idle" });
  const [pendingDelete, setPendingDelete] = useState<AdminDocument | null>(null);
  const [deleteState, setDeleteState] = useState<"idle" | "loading" | "error">("idle");
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const [drawer, setDrawer] = useState<DrawerState>({ phase: "idle" });
  const [formTitle, setFormTitle] = useState("");
  const [formIssuer, setFormIssuer] = useState("");
  const [formIssuedDate, setFormIssuedDate] = useState("");
  const [formEffectiveDate, setFormEffectiveDate] = useState("");
  const [formLegalStatus, setFormLegalStatus] = useState("");

  // Access scope state (managed separately from metadata save).
  const [accessScope, setAccessScope] = useState<"PUBLIC" | "DEPARTMENT">("PUBLIC");
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<string[]>([]);
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);
  const [accessSaving, setAccessSaving] = useState(false);

  const [actionInFlight, setActionInFlight] = useState<string | null>(null);

  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [list, st] = await Promise.all([
          adminService.listDocuments(),
          adminService.stats(),
        ]);
        if (cancelled) return;
        setDocs(list.items);
        setStats(st);
      } catch (e) {
        if (!cancelled) setError((e as Error).message ?? "Không tải được danh sách");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    return docs.filter((item) => {
      const haystack = `${item.title} ${item.documentNumber} ${item.issuer}`.toLowerCase();
      const matchQuery = !query || haystack.includes(query.toLowerCase());
      const matchStatus = status === "all" || item.status === status;
      return matchQuery && matchStatus;
    });
  }, [docs, query, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  const currentRoles = useCurrentRoles();
  const canDelete = currentRoles.has("ADMIN");
  const canUpload =
    currentRoles.has("ADMIN") || currentRoles.has("USER");
  const canEditMetadata = currentRoles.has("ADMIN");
  const canWorkflow = currentRoles.has("ADMIN") || currentRoles.has("USER");

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    setDeleteState("loading");
    setDeleteMessage(null);
    try {
      await adminService.deleteDocument(pendingDelete.id);
      setDeleteState("idle");
      setDeleteMessage(
        `Đã xóa ${pendingDelete.documentNumber || pendingDelete.title}.`,
      );
      setDocs((prev) =>
        prev.filter((doc) => doc.id !== pendingDelete.id),
      );
      setPendingDelete(null);
    } catch (err) {
      setDeleteState("error");
      setDeleteMessage((err as Error).message ?? "Không thể xóa văn bản.");
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setUploadState({ phase: "error", message: "Vui lòng chọn file PDF trước khi gửi." });
      return;
    }
    setUploadState({ phase: "uploading" });
    try {
      const body = new FormData();
      ["document_number", "title", "issued_by", "issued_date", "effective_date"].forEach(
        (key) => body.append(key, String(form.get(key) ?? "")),
      );
      body.append("file", file);
      await adminService.uploadDocument(body);
      setUploadState({
        phase: "success",
        message: "Đã gửi tài liệu. Tài liệu đã được lưu trong hệ thống.",
      });
      formElement.reset();
      await refreshList(setDocs);
    } catch (err) {
      setUploadState({
        phase: "error",
        message: (err as Error).message ?? "Không thể tải tài liệu. Kiểm tra quyền và kết nối backend.",
      });
    }
  }

  async function openMetadataDrawer(doc: AdminDocument) {
    setDrawer({ phase: "loading", documentId: doc.id });
    try {
      const [detail, versions, access, depts] = await Promise.all([
        adminService.getDocument(doc.id),
        adminService.listDocumentVersions(doc.id).catch(() => []),
        adminService.getDocumentAccess(doc.id).catch(() => null as DocumentAccess | null),
        organizationService.list().catch(() => [] as DepartmentResponse[]),
      ]);
      setFormTitle(detail.title);
      setFormIssuer(detail.issued_by);
      setFormIssuedDate(detail.issued_date);
      setFormEffectiveDate(detail.effective_date);
      setFormLegalStatus(detail.legal_status ?? "");
      setDepartments(depts);
      // Initialise access scope from the live config.
      setAccessScope(
        (access?.access_scope as "PUBLIC" | "DEPARTMENT") ?? "PUBLIC",
      );
      setSelectedDepartmentIds(
        access?.department_ids ?? [],
      );
      setDrawer({
        phase: "ready",
        documentId: doc.id,
        detail,
        versions,
        errorMessage: null,
      });
    } catch (err) {
      setDrawer({
        phase: "ready",
        documentId: doc.id,
        detail: {
          id: doc.id,
          document_number: doc.documentNumber,
          title: doc.title,
          issued_by: "",
          issued_date: "",
          effective_date: "",
          legal_status: "",
          access_scope: "PUBLIC",
          status: "draft",
          updated_by: "—",
          created_at: null,
          updated_at: null,
        },
        versions: [],
        errorMessage: (err as Error).message ?? "Không tải được metadata.",
      });
    }
  }

  function closeDrawer() {
    if (drawer.phase === "saving") return;
    setDrawer({ phase: "idle" });
  }

  async function saveMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (drawer.phase !== "ready") return;
    if (!formTitle.trim() || !formIssuer.trim() || !formIssuedDate || !formEffectiveDate) {
      setDrawer({
        ...drawer,
        errorMessage: "Vui lòng điền đầy đủ các trường bắt buộc.",
      });
      return;
    }
    setDrawer({ ...drawer, phase: "saving", errorMessage: null });
    try {
      const body: UpdateDocumentMetadataRequest = {
        document_number: drawer.detail.document_number,
        title: formTitle.trim(),
        issued_by: formIssuer.trim(),
        issued_date: formIssuedDate,
        effective_date: formEffectiveDate,
        legal_status: formLegalStatus || null,
      };
      const updated = await adminService.updateDocument(drawer.documentId, body);
      // Refresh list to reflect changes
      await refreshList(setDocs);
      showToast(`Đã cập nhật metadata cho "${updated.title}".`);
      setDrawer({
        phase: "ready",
        documentId: drawer.documentId,
        detail: updated,
        versions: drawer.versions,
        errorMessage: null,
      });
    } catch (err) {
      setDrawer({
        ...drawer,
        phase: "ready",
        errorMessage: (err as Error).message ?? "Không thể lưu metadata.",
      });
    }
  }

  async function runWorkflow(
    versionId: string,
    kind: "approve" | "index" | "publish",
  ) {
    const key = `${versionId}:${kind}`;
    setActionInFlight(key);
    try {
      if (kind === "approve") await adminService.approveVersion(versionId);
      if (kind === "index") await adminService.indexVersion(versionId);
      if (kind === "publish") await adminService.publishVersion(versionId);
      // Reload versions to reflect new status
      if (drawer.phase === "ready") {
        const versions = await adminService.listDocumentVersions(drawer.documentId);
        setDrawer({ ...drawer, versions });
      }
      const label =
        kind === "approve" ? "Duyệt" : kind === "index" ? "Index" : "Publish";
      showToast(`${label} phiên bản thành công.`);
    } catch (err) {
      showToast((err as Error).message ?? `Không thể ${kind} phiên bản.`);
    } finally {
      setActionInFlight(null);
    }
  }

  const total = stats?.totalDocuments ?? docs.length;
  const active = stats?.activeDocuments ?? docs.filter((d) => d.status === "DANG_HIEU_LUC").length;
  const pending = stats?.pendingDocuments ?? docs.filter((d) => d.status === "CHO_XU_LY_NOI_DUNG").length;
  const expired = stats?.expiredDocuments ?? docs.filter((d) => d.status === "HET_HIEU_LUC").length;

  const drawerSaving = drawer.phase === "saving";

  async function handleSaveAccess() {
    if (!isDrawerReady(drawer)) return;
    setAccessSaving(true);
    try {
      await adminService.updateDocumentAccess(drawer.documentId, {
        access_scope: accessScope,
        department_ids:
          accessScope === "DEPARTMENT"
            ? selectedDepartmentIds
            : [],
      });
      showToast("Đã cập nhật phân quyền tài liệu.");
    } catch (err) {
      showToast((err as Error).message ?? "Không thể lưu phân quyền.");
    } finally {
      setAccessSaving(false);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>Quản lý dữ liệu</p>
          <h2>Quản lý tài liệu</h2>
          <p>Quản lý quy chế, phiên bản và trạng thái tài liệu trong hệ thống.</p>
        </div>
        <div className={styles.headingActions}>
          {canUpload && (
            <button className={styles.uploadButton} type="button" onClick={() => { setUploadOpen(true); setUploadState({ phase: "idle" }); }}>
              <UploadCloud size={17} aria-hidden="true" /> Tải tài liệu lên
            </button>
          )}
        </div>
      </header>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <section className={styles.summary}>
        <Summary label="Tổng tài liệu" value={String(total)} tone="blue" />
        <Summary label="Đang hiệu lực" value={String(active)} tone="green" />
        <Summary label="Chờ duyệt" value={String(pending)} tone="orange" />
        <Summary label="Hết hiệu lực" value={String(expired)} tone="red" />
      </section>

      <section className={styles.tablePanel} aria-label="Danh sách tài liệu">
        <div className={styles.toolbar}>
          <label className={styles.search}>
            <Search size={18} aria-hidden="true" />
            <span className="sr-only">Tìm tài liệu</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm theo tên, số hiệu hoặc đơn vị ban hành..."
            />
          </label>
          <label className={styles.filter}>
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span className="sr-only">Lọc trạng thái</span>
            <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
              <option value="all">Tất cả trạng thái</option>
              <option value="DANG_HIEU_LUC">Đang hiệu lực</option>
              <option value="CHO_XU_LY_NOI_DUNG">Chờ duyệt</option>
              <option value="HET_HIEU_LUC">Hết hiệu lực</option>
              <option value="BI_THAY_THE">Bị thay thế</option>
              <option value="BAN_NHAP">Bản nháp</option>
            </select>
          </label>
        </div>
        <div className={styles.tableWrap}>
          <table>
            <thead>
              <tr>
                <th>Tên tài liệu</th>
                <th>Loại</th>
                <th>Trạng thái</th>
                <th>Phiên bản</th>
                <th>Ngày hiệu lực</th>
                <th>Cập nhật gần nhất</th>
                <th><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((item) => {
                const state = statusMap[item.status] ?? statusMap.BAN_NHAP;
                return (
                  <tr key={item.id}>
                    <td data-label="Tên tài liệu">
                      <a href={`/documents/${item.id}`} className={styles.titleCell}>
                        <span className={styles.pdf}><FileText size={18} aria-hidden="true" /></span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>{item.documentNumber}</small>
                        </span>
                      </a>
                    </td>
                    <td data-label="Loại"><span className={styles.type}>{item.documentType || "—"}</span></td>
                    <td data-label="Trạng thái"><StatusBadge tone={state.tone} showDot>{state.label}</StatusBadge></td>
                    <td data-label="Phiên bản">{item.version}</td>
                    <td data-label="Ngày hiệu lực">{item.effectiveDate || "—"}</td>
                    <td data-label="Cập nhật gần nhất">
                      <span className={styles.updated}>
                        {item.updatedAt}
                        <small>bởi {item.updatedBy}</small>
                      </span>
                    </td>
                    <td className={styles.actions}>
                      <Link
                        href={`/admin/documents/${item.id}`}
                        className={styles.actionBtn}
                        title="Xem chi tiết"
                        style={{ display: "inline-flex", alignItems: "center" }}
                      >
                        <Eye size={16} />
                      </Link>
                      {canEditMetadata && (
                        <button
                          type="button"
                          aria-label={`Sửa metadata ${item.title}`}
                          className={styles.actionBtn}
                          onClick={() => openMetadataDrawer(item)}
                          title="Sửa metadata"
                        >
                          <Edit2 size={16} />
                        </button>
                      )}
                      {canDelete && (
                        <button
                          type="button"
                          aria-label={`Xóa ${item.title}`}
                          onClick={() => {
                            setPendingDelete(item);
                            setDeleteState("idle");
                            setDeleteMessage(null);
                          }}
                          className={`${styles.actionBtn} ${styles.deleteButton}`}
                          title="Xóa"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!loading && filtered.length === 0 && (
            <div className={styles.empty}>
              <FileText size={28} aria-hidden="true" />
              <strong>Không tìm thấy tài liệu</strong>
              <span>Thử đổi từ khóa hoặc bộ lọc trạng thái.</span>
            </div>
          )}
        </div>
        <footer className={styles.tableFooter}>
          <span>Hiển thị {paged.length} trong tổng số {filtered.length} tài liệu</span>
          <div className={styles.pagination}>
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Trước</button>
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
            <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Sau</button>
          </div>
        </footer>
      </section>

      {uploadOpen && (
        <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && uploadState.phase !== "uploading") setUploadOpen(false); }}>
          <section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <div className={styles.modalHeader}>
              <div>
                <h2 id="upload-title">Tải văn bản mới</h2>
                <p>Metadata sẽ được gửi cùng file PDF đến backend.</p>
              </div>
              <button type="button" className={styles.closeButton} aria-label="Đóng cửa sổ tải tài liệu" onClick={() => setUploadOpen(false)} disabled={uploadState.phase === "uploading"}>×</button>
            </div>
            <form onSubmit={handleUpload} className={styles.uploadForm}>
              <label>Số hiệu văn bản<input name="document_number" required placeholder="Ví dụ: 128/QĐ-ĐH" disabled={uploadState.phase === "uploading"} /></label>
              <label>Tên tài liệu<input name="title" required placeholder="Tên đầy đủ của văn bản" disabled={uploadState.phase === "uploading"} /></label>
              <label>Cơ quan ban hành<input name="issued_by" required placeholder="Ví dụ: BGH / Phòng Đào tạo" disabled={uploadState.phase === "uploading"} /></label>
              <div className={styles.formGrid}>
                <label>Ngày ban hành<input name="issued_date" type="date" required disabled={uploadState.phase === "uploading"} /></label>
                <label>Ngày hiệu lực<input name="effective_date" type="date" required disabled={uploadState.phase === "uploading"} /></label>
              </div>
              <label>File nguồn<input name="file" type="file" accept=".pdf,application/pdf" required disabled={uploadState.phase === "uploading"} /></label>
              {uploadState.phase === "error" && (
                <p className={styles.formError} role="alert">{uploadState.message}</p>
              )}
              {uploadState.phase === "success" && (
                <p className={styles.formSuccess} role="status">{uploadState.message}</p>
              )}
              <div className={styles.modalActions}>
                <button type="button" className={styles.cancelButton} onClick={() => setUploadOpen(false)} disabled={uploadState.phase === "uploading"}>Hủy</button>
                <button type="submit" className={styles.uploadButton} disabled={uploadState.phase === "uploading"}>
                  {uploadState.phase === "uploading" ? "Đang tải lên..." : "Gửi tài liệu"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {pendingDelete && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              deleteState !== "loading"
            ) {
              setPendingDelete(null);
            }
          }}
        >
          <section
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
          >
            <div className={styles.modalHeader}>
              <div>
                <h2 id="delete-title">Xóa văn bản</h2>
                <p>Hành động này không thể hoàn tác. Vui lòng xác nhận trước khi xóa.</p>
              </div>
              <button
                type="button"
                className={styles.closeButton}
                aria-label="Đóng hộp thoại xác nhận xóa"
                onClick={() => setPendingDelete(null)}
                disabled={deleteState === "loading"}
              >
                ×
              </button>
            </div>
            <div className={styles.deleteConfirmBody}>
              <strong>{pendingDelete.title}</strong>
              <small>{pendingDelete.documentNumber}</small>
              <div className={styles.deleteImpact}>
                <h4>Tác động</h4>
                <ul>
                  <li>Xóa v�nh viễn văn bản và các phiên bản liên quan khỏi cơ sở dữ liệu.</li>
                  <li>Xóa toàn bộ chunks tương ứng trong vector database (Qdrant).</li>
                  <li>Xóa file nguồn PDF trong object storage (R2).</li>
                  <li>Xóa relations, application-scopes và changelog liên quan.</li>
                </ul>
              </div>
            </div>
            {deleteState === "error" && deleteMessage && (
              <p className={styles.formError} role="alert">
                {deleteMessage}
              </p>
            )}
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => setPendingDelete(null)}
                disabled={deleteState === "loading"}
              >
                Hủy
              </button>
              <button
                type="button"
                className={styles.deleteConfirmButton}
                onClick={handleConfirmDelete}
                disabled={deleteState === "loading"}
              >
                {deleteState === "loading" ? "Đang xóa..." : "Xóa vĩnh viễn"}
              </button>
            </div>
          </section>
        </div>
      )}

      {/* Metadata edit drawer */}
      {drawer.phase !== "idle" && (
        <>
          <div className={styles.drawerBackdrop} onClick={closeDrawer} />
          <aside className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby="meta-drawer-title">
            <div className={styles.drawerHeader}>
              <div>
                <h2 id="meta-drawer-title">Sửa metadata tài liệu</h2>
                <p>
                  {isDrawerReady(drawer)
                    ? drawer.detail.document_number
                    : "Đang tải…"}
                </p>
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

            {drawer.phase === "loading" && (
              <div className={styles.drawerBody}><p>Đang tải metadata…</p></div>
            )}

            {isDrawerReady(drawer) && (
              <form onSubmit={saveMetadata}>
                <div className={styles.drawerBody}>
                  <label>
                    Số hiệu văn bản (chỉ đọc)
                    <input value={drawer.detail.document_number} disabled readOnly />
                  </label>
                  <label>
                    Tiêu đề
                    <input
                      value={formTitle}
                      onChange={(e) => setFormTitle(e.target.value)}
                      disabled={drawerSaving}
                      maxLength={500}
                      required
                    />
                  </label>
                  <label>
                    Cơ quan ban hành
                    <input
                      value={formIssuer}
                      onChange={(e) => setFormIssuer(e.target.value)}
                      disabled={drawerSaving}
                      maxLength={255}
                      required
                    />
                  </label>
                  <div className={styles.formGrid}>
                    <label>
                      Ngày ban hành
                      <input
                        type="date"
                        value={formIssuedDate}
                        onChange={(e) => setFormIssuedDate(e.target.value)}
                        disabled={drawerSaving}
                        required
                      />
                    </label>
                    <label>
                      Ngày hiệu lực
                      <input
                        type="date"
                        value={formEffectiveDate}
                        onChange={(e) => setFormEffectiveDate(e.target.value)}
                        disabled={drawerSaving}
                        required
                      />
                    </label>
                  </div>
                  <label>
                    Trạng thái pháp lý
                    <select
                      value={formLegalStatus}
                      onChange={(e) => setFormLegalStatus(e.target.value)}
                      disabled={drawerSaving}
                    >
                      <option value="">— Giữ nguyên —</option>
                      {LEGAL_STATUS_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  {/* Access scope management */}
                  <div
                    style={{
                      padding: "16px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 10,
                      marginTop: 4,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        marginBottom: 12,
                      }}
                    >
                      Phân quyền tài liệu
                    </div>

                    <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
                      <label
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 8,
                          flex: 1,
                          padding: "12px 14px",
                          border: `2px solid ${accessScope === "PUBLIC" ? "var(--color-primary)" : "var(--color-border)"}`,
                          borderRadius: 10,
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="radio"
                          name="accessScope"
                          value="PUBLIC"
                          checked={accessScope === "PUBLIC"}
                          onChange={() => setAccessScope("PUBLIC")}
                          style={{ marginTop: 3 }}
                        />
                        <div>
                          <strong style={{ fontSize: 13 }}>Công khai</strong>
                          <small
                            style={{
                              display: "block",
                              color: "var(--color-text-muted)",
                              fontSize: 12,
                              marginTop: 2,
                            }}
                          >
                            Mọi người dùng đều có thể xem
                          </small>
                        </div>
                      </label>

                      <label
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 8,
                          flex: 1,
                          padding: "12px 14px",
                          border: `2px solid ${accessScope === "DEPARTMENT" ? "var(--color-primary)" : "var(--color-border)"}`,
                          borderRadius: 10,
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="radio"
                          name="accessScope"
                          value="DEPARTMENT"
                          checked={accessScope === "DEPARTMENT"}
                          onChange={() => setAccessScope("DEPARTMENT")}
                          style={{ marginTop: 3 }}
                        />
                        <div>
                          <strong style={{ fontSize: 13 }}>Nội bộ theo đơn vị</strong>
                          <small
                            style={{
                              display: "block",
                              color: "var(--color-text-muted)",
                              fontSize: 12,
                              marginTop: 2,
                            }}
                          >
                            Chỉ đơn vị được chọn mới xem được
                          </small>
                        </div>
                      </label>
                    </div>

                    {accessScope === "DEPARTMENT" && (
                      <div style={{ marginBottom: 14 }}>
                        <div
                          style={{
                            fontSize: 12,
                            fontWeight: 600,
                            color: "var(--color-text-muted)",
                            marginBottom: 8,
                          }}
                        >
                          Đơn vị được truy cập
                        </div>
                        <DepartmentMultiSelect
                          departments={departments}
                          selectedIds={selectedDepartmentIds}
                          onChange={setSelectedDepartmentIds}
                          emptyMessage="Chưa có đơn vị nào."
                        />
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={handleSaveAccess}
                      disabled={accessSaving}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        padding: "8px 16px",
                        border: "none",
                        borderRadius: 8,
                        background: "var(--color-primary)",
                        color: "#fff",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: accessSaving ? "not-allowed" : "pointer",
                        opacity: accessSaving ? 0.6 : 1,
                      }}
                    >
                      {accessSaving ? "Đang lưu…" : "Lưu phân quyền"}
                    </button>
                  </div>

                  {drawer.versions.length > 0 && (
                    <div>
                      <label style={{ marginBottom: 8 }}>
                        Phiên bản ({drawer.versions.length})
                      </label>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {drawer.versions.map((v) => {
                          const status = v.processing_status;
                          return (
                            <div
                              key={v.id}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                padding: "10px 12px",
                                border: "1px solid var(--color-border)",
                                borderRadius: 9,
                              }}
                            >
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <strong style={{ fontSize: 13 }}>
                                  v{v.version_number} · {v.source_filename}
                                </strong>
                                <small style={{ display: "block", color: "var(--color-text-muted)", fontSize: 11, marginTop: 2 }}>
                                  Trạng thái: <code>{status}</code> · {(v.size_bytes / 1024).toFixed(1)} KB
                                </small>
                              </div>
                              {canWorkflow && (
                                <div className={styles.workflowRow}>
                                  <button
                                    type="button"
                                    className={`${styles.workflowBtn} ${styles.approve}`}
                                    onClick={() => runWorkflow(v.id, "approve")}
                                    disabled={
                                      actionInFlight !== null ||
                                      status === "indexed"
                                    }
                                    title="Duyệt phiên bản"
                                  >
                                    <CheckCircle2 size={12} /> Duyệt
                                  </button>
                                  <button
                                    type="button"
                                    className={`${styles.workflowBtn} ${styles.index}`}
                                    onClick={() => runWorkflow(v.id, "index")}
                                    disabled={
                                      actionInFlight !== null ||
                                      !(status === "approved" || status === "parsed" || status === "indexed")
                                    }
                                    title="Index phiên bản vào Qdrant"
                                  >
                                    Index
                                  </button>
                                  <button
                                    type="button"
                                    className={`${styles.workflowBtn} ${styles.publish}`}
                                    onClick={() => runWorkflow(v.id, "publish")}
                                    disabled={
                                      actionInFlight !== null ||
                                      status !== "indexed"
                                    }
                                    title="Publish phiên bản"
                                  >
                                    Publish
                                  </button>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {drawer.errorMessage && (
                    <p className={styles.formError} role="alert">
                      {drawer.errorMessage}
                    </p>
                  )}
                </div>

                <div className={styles.drawerFooter}>
                  <button
                    type="button"
                    className={styles.cancelButton}
                    onClick={closeDrawer}
                    disabled={drawerSaving}
                  >
                    Đóng
                  </button>
                  <button
                    type="submit"
                    className={styles.submitButton}
                    disabled={drawerSaving}
                  >
                    {drawerSaving ? "Đang lưu…" : "Lưu metadata"}
                  </button>
                </div>
              </form>
            )}
          </aside>
        </>
      )}

      {deleteMessage && !pendingDelete && (
        <p className={styles.toast} role="status">
          {deleteMessage}
        </p>
      )}
      {toast && <p className={styles.toast} role="status">{toast}</p>}
    </div>
  );
}

function Summary({ label, value, tone }: { label: string; value: string; tone: "blue" | "green" | "orange" | "red" }) {
  return <article className={styles.summaryCard}><span className={`${styles.summaryIcon} ${styles[tone]}`}><FileText size={19} aria-hidden="true" /></span><span>{label}</span><strong>{value}</strong></article>;
}
