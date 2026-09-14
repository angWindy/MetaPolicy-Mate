"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  Globe,
  Lock,
  Users,
} from "lucide-react";

import { adminService, type DocumentAccess, type DocumentSection } from "@/services/adminService";
import { organizationService, type DepartmentResponse } from "@/services/organizationService";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";
import { DepartmentMultiSelect } from "@/components/admin/DepartmentMultiSelect";
import { DocumentPdfViewer } from "@/components/admin/DocumentPdfViewer";
import { adminSidebarItems } from "@/components/admin/navigation";
import { StatusBadge } from "@/components/ui";
import styles from "./page.module.css";

type Tab = "overview" | "content" | "metadata" | "access";

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; data: AdminDocumentData }
  | { kind: "error"; message: string };

interface AdminDocumentData {
  id: string;
  document_number: string;
  title: string;
  issued_by: string;
  issued_date: string;
  effective_date: string;
  legal_status: string;
  access_scope: "PUBLIC" | "DEPARTMENT";
  source_filename?: string;
  versions: import("@/services/adminService").AdminDocumentVersion[];
  access: DocumentAccess | null;
  sections: DocumentSection[];
}

const LEGAL_STATUS_LABELS: Record<string, string> = {
  draft: "Bản nháp",
  scheduled: "Đã lên lịch",
  effective: "Đang hiệu lực",
  superseded: "Bị thay thế",
  expired: "Hết hiệu lực",
  revoked: "Đã thu hồi",
};

const LEGAL_STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  draft: "neutral",
  scheduled: "warning",
  effective: "success",
  superseded: "neutral",
  expired: "danger",
  revoked: "danger",
};

export default function AdminDocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [tab, setTab] = useState<Tab>("overview");
  const [accessSaving, setAccessSaving] = useState(false);
  const [accessScope, setAccessScope] = useState<"PUBLIC" | "DEPARTMENT">("PUBLIC");
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<string[]>([]);
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [doc, depts] = await Promise.all([
          adminService.getDocument(id).catch(() => null),
          organizationService.list().catch(() => [] as DepartmentResponse[]),
        ]);

        if (!doc) {
          setState({ kind: "error", message: "Không tìm thấy tài liệu." });
          return;
        }

        const [access, sections] = await Promise.all([
          adminService.getDocumentAccess(id).catch(() => null as DocumentAccess | null),
          adminService.getDocumentSections(id).catch(() => [] as DocumentSection[]),
        ]);

        // Also fetch versions for the versions list in Overview tab.
        const versions = await adminService.listDocumentVersions(id).catch(
          () => [] as import("@/services/adminService").AdminDocumentVersion[],
        );

        if (cancelled) return;

        const initialScope = 
          (access?.access_scope === "PUBLIC" || access?.access_scope === "DEPARTMENT")
            ? access.access_scope
            : "PUBLIC";
        setAccessScope(initialScope);
        setSelectedDepartmentIds(access?.department_ids ?? []);
        setDepartments(depts);

        setState({
          kind: "ready",
          data: {
            ...doc,
            versions,
            access,
            sections,
            source_filename: versions[0]?.source_filename,
          },
        });
      } catch (e) {
        if (!cancelled) {
          setState({
            kind: "error",
            message: (e as Error).message ?? "Không tải được tài liệu.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  }

  async function handleSaveAccess() {
    setAccessSaving(true);
    try {
      await adminService.updateDocumentAccess(id, {
        access_scope: accessScope,
        department_ids:
          accessScope === "DEPARTMENT" ? selectedDepartmentIds : [],
      });
      // Refresh access state.
      const access = await adminService.getDocumentAccess(id);
      if (state.kind === "ready") {
        setState({
          kind: "ready",
          data: { ...state.data, access },
        });
      }
      showToast("Đã cập nhật phân quyền tài liệu.");
    } catch (e) {
      showToast((e as Error).message ?? "Không thể lưu phân quyền.");
    } finally {
      setAccessSaving(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <AuthGate
        loginPath="/admin/documents"
        loadingFallback={<AuthLoading title="Đang tải chi tiết tài liệu…" />}
      >
        <RequireRole roles={["ADMIN"]}>
          <AuthenticatedLayout
            title="Chi tiết tài liệu"
            sidebarItems={adminSidebarItems}
            notificationCount={0}
          >
            <div className={styles.loadingState}>
              <FileText size={32} aria-hidden="true" />
              <p>Đang tải thông tin tài liệu…</p>
            </div>
          </AuthenticatedLayout>
        </RequireRole>
      </AuthGate>
    );
  }

  if (state.kind === "error") {
    return (
      <AuthGate
        loginPath="/admin/documents"
        loadingFallback={<AuthLoading title="Đang tải chi tiết tài liệu…" />}
      >
        <RequireRole roles={["ADMIN"]}>
          <AuthenticatedLayout
            title="Chi tiết tài liệu"
            sidebarItems={adminSidebarItems}
            notificationCount={0}
          >
            <div className={styles.errorState}>
              <strong>Không tải được tài liệu</strong>
              <span>{state.message}</span>
              <Link href="/admin/documents" className={styles.backLink}>
                ← Quay lại danh sách
              </Link>
            </div>
          </AuthenticatedLayout>
        </RequireRole>
      </AuthGate>
    );
  }

  const { data } = state;
  const statusLabel = LEGAL_STATUS_LABELS[data.legal_status] ?? data.legal_status;
  const statusTone = LEGAL_STATUS_TONE[data.legal_status] ?? "neutral";

  return (
    <AuthGate
      loginPath="/admin/documents"
      loadingFallback={<AuthLoading title="Đang tải chi tiết tài liệu…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title={`Tài liệu: ${data.document_number}`}
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
        <div className={styles.page}>
          {/* Breadcrumb */}
          <div className={styles.breadcrumb}>
            <Link href="/admin/documents" className={styles.backLink}>
              <ArrowLeft size={16} aria-hidden="true" />
              Quản lý tài liệu
            </Link>
            <span className={styles.breadcrumbSep}>/</span>
            <span>{data.document_number}</span>
          </div>

          {/* Document header */}
          <div className={styles.docHeader}>
            <div className={styles.docHeaderLeft}>
              <div className={styles.docMeta}>
                <span className={styles.docNumber}>{data.document_number}</span>
                <StatusBadge tone={statusTone} showDot>
                  {statusLabel}
                </StatusBadge>
                {data.access_scope === "PUBLIC" ? (
                  <span className={styles.accessBadge} style={{ background: "#dcfce7", color: "#15803d" }}>
                    <Globe size={13} aria-hidden="true" />
                    Công khai
                  </span>
                ) : (
                  <span className={styles.accessBadge} style={{ background: "#fef9c3", color: "#a16207" }}>
                    <Lock size={13} aria-hidden="true" />
                    Nội bộ
                  </span>
                )}
              </div>
              <h1 className={styles.docTitle}>{data.title}</h1>
              <p className={styles.docIssuer}>{data.issued_by}</p>
            </div>
          </div>

          {/* Tabs */}
          <div className={styles.tabs} role="tablist">
            {(["overview", "content", "metadata", "access"] as Tab[]).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={tab === t}
                className={`${styles.tab} ${tab === t ? styles.tabActive : ""}`}
                onClick={() => setTab(t)}
              >
                {t === "overview" ? "Tổng quan" :
                 t === "content" ? "Nội dung" :
                 t === "metadata" ? "Metadata" : "Phân quyền"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className={styles.tabContent} role="tabpanel">

            {/* ── Tab: Tổng quan ── */}
            {tab === "overview" && (
              <div className={styles.overviewGrid}>
                <section className={styles.card}>
                  <h2 className={styles.cardTitle}>Thông tin tài liệu</h2>
                  <dl className={styles.infoList}>
                    <div className={styles.infoRow}>
                      <dt>Số hiệu</dt>
                      <dd><code>{data.document_number}</code></dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Tên tài liệu</dt>
                      <dd>{data.title}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Cơ quan ban hành</dt>
                      <dd>{data.issued_by}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Ngày ban hành</dt>
                      <dd>{data.issued_date || "—"}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Ngày hiệu lực</dt>
                      <dd>{data.effective_date || "—"}</dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Trạng thái pháp lý</dt>
                      <dd>
                        <StatusBadge tone={statusTone} showDot>
                          {statusLabel}
                        </StatusBadge>
                      </dd>
                    </div>
                    <div className={styles.infoRow}>
                      <dt>Phạm vi truy cập</dt>
                      <dd>
                        {data.access_scope === "PUBLIC"
                          ? "Công khai"
                          : `Nội bộ (${data.access?.department_codes?.join(", ") ?? (data.access?.department_ids?.length ? data.access.department_ids.length + " đơn vị" : "—")})`}
                      </dd>
                    </div>
                  </dl>
                </section>

                {data.versions.length > 0 && (
                  <section className={styles.card}>
                    <h2 className={styles.cardTitle}>Phiên bản ({data.versions.length})</h2>
                    <div className={styles.versionList}>
                      {data.versions.map((v) => (
                        <div key={v.id} className={styles.versionRow}>
                          <div className={styles.versionInfo}>
                            <strong>v{v.version_number}</strong>
                            <span>{v.source_filename}</span>
                            <small>{(v.size_bytes / 1024).toFixed(1)} KB</small>
                          </div>
                          <StatusBadge
                            tone={
                              v.processing_status === "indexed" ? "success" :
                              v.processing_status === "approved" ? "info" :
                              v.processing_status === "failed" ? "danger" : "warning"
                            }
                          >
                            {v.processing_status}
                          </StatusBadge>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}

            {/* ── Tab: Nội dung ── */}
            {tab === "content" && (
              <div className={styles.contentTab}>
                <div className={styles.contentGrid}>
                  {/* PDF viewer */}
                  <div className={styles.pdfSection}>
                    <DocumentPdfViewer
                      documentId={id}
                      documentTitle={data.title}
                      sourceFilename={data.source_filename}
                    />
                  </div>

                  {/* Sections list */}
                  {data.sections.length > 0 && (
                    <div className={styles.sectionsPanel}>
                      <h3 className={styles.sectionsTitle}>
                        Cấu trúc tài liệu ({data.sections.length})
                      </h3>
                      <div className={styles.sectionsList}>
                        {data.sections.map((section) => (
                          <details key={section.id} className={styles.sectionItem}>
                            <summary className={styles.sectionSummary}>
                              <span className={styles.sectionType}>
                                {section.section_type ?? "Mục"}
                              </span>
                              {section.section_number && (
                                <span className={styles.sectionNumber}>
                                  {section.section_number}
                                </span>
                              )}
                              <span className={styles.sectionHeading}>
                                {section.heading ?? ""}
                              </span>
                              {section.page && (
                                <span className={styles.sectionPage}>
                                  Trang {section.page}
                                </span>
                              )}
                            </summary>
                            <div
                              className={styles.sectionContent}
                              style={{
                                fontSize: 13,
                                color: "var(--color-text-muted)",
                                padding: "8px 12px",
                                lineHeight: 1.6,
                              }}
                            >
                              {section.heading_path?.length > 0 && (
                                <div style={{ marginBottom: 4 }}>
                                  <small>
                                    <em>Path: {section.heading_path.join(" › ")}</em>
                                  </small>
                                </div>
                              )}
                              Xem nội dung chi tiết trong tệp PDF bên trái.
                            </div>
                          </details>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Tab: Metadata ── */}
            {tab === "metadata" && (
              <div className={styles.card} style={{ maxWidth: 640 }}>
                <h2 className={styles.cardTitle}>Metadata</h2>
                <dl className={styles.infoList}>
                  <div className={styles.infoRow}>
                    <dt>ID</dt>
                    <dd><code>{id}</code></dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Số hiệu văn bản</dt>
                    <dd>{data.document_number}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Tên tài liệu</dt>
                    <dd>{data.title}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Cơ quan ban hành</dt>
                    <dd>{data.issued_by}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Ngày ban hành</dt>
                    <dd>{data.issued_date || "—"}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Ngày hiệu lực</dt>
                    <dd>{data.effective_date || "—"}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Trạng thái pháp lý</dt>
                    <dd>{statusLabel}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>File nguồn</dt>
                    <dd>{data.source_filename ?? "—"}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Số phiên bản</dt>
                    <dd>{data.versions.length}</dd>
                  </div>
                  <div className={styles.infoRow}>
                    <dt>Số sections</dt>
                    <dd>{data.sections.length}</dd>
                  </div>
                </dl>
              </div>
            )}

            {/* ── Tab: Phân quyền ── */}
            {tab === "access" && (
              <div className={styles.accessTab}>
                <section className={styles.card}>
                  <h2 className={styles.cardTitle}>Phân quyền tài liệu</h2>
                  <p className={styles.cardDesc}>
                    Thiết lập ai được phép xem tài liệu này.
                  </p>

                  <div className={styles.accessOptions}>
                    <label
                      className={`${styles.accessOption} ${accessScope === "PUBLIC" ? styles.accessOptionActive : ""}`}
                    >
                      <input
                        type="radio"
                        name="accessScope"
                        value="PUBLIC"
                        checked={accessScope === "PUBLIC"}
                        onChange={() => setAccessScope("PUBLIC")}
                      />
                      <div className={styles.accessOptionContent}>
                        <div className={styles.accessOptionHeader}>
                          <Globe size={18} aria-hidden="true" />
                          <strong>Công khai</strong>
                        </div>
                        <small>Mọi người dùng đã đăng nhập đều có thể xem tài liệu này.</small>
                      </div>
                    </label>

                    <label
                      className={`${styles.accessOption} ${accessScope === "DEPARTMENT" ? styles.accessOptionActive : ""}`}
                    >
                      <input
                        type="radio"
                        name="accessScope"
                        value="DEPARTMENT"
                        checked={accessScope === "DEPARTMENT"}
                        onChange={() => setAccessScope("DEPARTMENT")}
                      />
                      <div className={styles.accessOptionContent}>
                        <div className={styles.accessOptionHeader}>
                          <Lock size={18} aria-hidden="true" />
                          <strong>Nội bộ theo đơn vị</strong>
                        </div>
                        <small>Chỉ người dùng thuộc đơn vị được chọn mới xem được.</small>
                      </div>
                    </label>
                  </div>

                  {accessScope === "DEPARTMENT" && (
                    <div className={styles.departmentSelect}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          marginBottom: 10,
                        }}
                      >
                        <Users size={16} aria-hidden="true" />
                        <strong style={{ fontSize: 14 }}>Đơn vị được truy cập</strong>
                      </div>
                      <DepartmentMultiSelect
                        departments={departments}
                        selectedIds={selectedDepartmentIds}
                        onChange={setSelectedDepartmentIds}
                      />
                    </div>
                  )}

                  <div className={styles.accessActions}>
                    <button
                      type="button"
                      className={styles.saveButton}
                      onClick={handleSaveAccess}
                      disabled={accessSaving}
                    >
                      {accessSaving ? "Đang lưu…" : "Lưu phân quyền"}
                    </button>
                  </div>
                </section>
              </div>
            )}
          </div>
        </div>

        {toast && <p className={styles.toast} role="status">{toast}</p>}
      </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
