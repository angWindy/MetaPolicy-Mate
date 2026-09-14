"use client";

import Link from "next/link";
import { useEffect, useState, useCallback } from "react";
import {
  CheckCircle2,
  FileText,
  RefreshCw,
  XCircle,
} from "lucide-react";

import { apiRequest } from "@/lib/api";
import { adminSidebarItems } from "@/components/admin/navigation";
import { ProcessingStatusBadge } from "@/components/documents/StatusBadge";
import { AuthenticatedLayout, AuthGate, AuthLoading, RequireRole } from "@/components/layout";

type VersionSummary = {
  id: string;
  document_id: string;
  version_number: number;
  processing_status: string;
  source_filename: string;
  size_bytes: number;
  object_key: string;
  created_at: string | null;
};

type DocumentWithVersion = {
  id: string;
  title: string;
  document_number: string;
  issued_by: string;
  issued_date: string;
  versions: VersionSummary[];
};

type ReviewTab = "pending_review" | "pending_approval" | "approved" | "rejected";

const TAB_LABELS: Record<ReviewTab, string> = {
  pending_review: "Chờ xem xét",
  pending_approval: "Chờ duyệt cuối",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
};

const TAB_STATUSES: Record<ReviewTab, string[]> = {
  pending_review: ["pending_review"],
  pending_approval: ["pending_approval"],
  approved: ["approved", "indexed", "published"],
  rejected: ["rejected"],
};

const PAGE_SIZE = 50;

export default function AdminReviewPage() {
  const [activeTab, setActiveTab] = useState<ReviewTab>("pending_review");
  const [documents, setDocuments] = useState<DocumentWithVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch all documents (paginated) and filter client-side for now.
      // TODO: add dedicated admin list-by-status endpoint.
      const res = await apiRequest<{ items: PolicyDocument[] }>(
        `/api/v1/regulatory-documents?page=1&page_size=${PAGE_SIZE}`,
      );
      // Fetch versions in batches to limit N+1 concurrency (5 at a time).
      // For 50 docs that's 10 sequential batches of 5 parallel fetches
      // instead of 50 simultaneous requests overwhelming the server.
      const CONCURRENCY = 5;
      const withVersions: (DocumentWithVersion | null)[] = [];
      for (let i = 0; i < res.items.length; i += CONCURRENCY) {
        const batch = res.items.slice(i, i + CONCURRENCY);
        const batchResults = await Promise.all(
          batch.map(async (doc) => {
            try {
              const verRes = await apiRequest<VersionSummary[]>(
                `/api/v1/admin/documents/${doc.id}/versions`,
              );
              return {
                id: doc.id,
                title: doc.title,
                document_number: doc.documentNumber,
                issued_by: doc.issuedBy ?? "",
                issued_date: doc.issuedDate ?? "",
                versions: verRes,
              };
            } catch {
              return null;
            }
          }),
        );
        withVersions.push(...batchResults);
      }
      const filtered = withVersions
        .filter((d): d is DocumentWithVersion => {
          if (!d) return false;
          const tabStatuses = TAB_STATUSES[activeTab];
          return d.versions.some((v) =>
            tabStatuses.includes(v.processing_status)
          );
        })
        .sort((a, b) => {
          const aTime = a.versions[0]?.created_at ?? "";
          const bTime = b.versions[0]?.created_at ?? "";
          return bTime.localeCompare(aTime);
        });
      setDocuments(filtered);
    } catch (e) {
      setError("Không thể tải danh sách tài liệu.");
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  async function handleAction(
    versionId: string,
    action: "complete-review" | "reject" | "approve" | "republish",
  ) {
    setActionLoading(versionId);
    try {
      await apiRequest(`/api/v1/admin/documents/${versionId}/${action}`, {
        method: "POST",
      });
      await fetchDocuments();
    } catch {
      setError(`Không thể thực hiện thao tác '${action}'.`);
    } finally {
      setActionLoading(null);
    }
  }

  const tabCounts = {
    pending_review: documents.filter((d) =>
      d.versions.some((v) => v.processing_status === "pending_review")
    ).length,
    pending_approval: documents.filter((d) =>
      d.versions.some((v) => v.processing_status === "pending_approval")
    ).length,
    approved: documents.filter((d) =>
      d.versions.some((v) =>
        ["approved", "indexed", "published"].includes(v.processing_status)
      )
    ).length,
    rejected: documents.filter((d) =>
      d.versions.some((v) => v.processing_status === "rejected")
    ).length,
  };

  return (
    <AuthGate
      loginPath="/admin/review"
      loadingFallback={<AuthLoading title="Đang tải trang duyệt tài liệu…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Duyệt tài liệu"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h1 className="text-xl font-semibold">Duyệt tài liệu</h1>
              <button
                type="button"
                onClick={() => void fetchDocuments()}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
              >
                <RefreshCw size={14} />
                Làm mới
              </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 mb-6 border-b border-slate-200">
              {(Object.keys(TAB_LABELS) as ReviewTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                    activeTab === tab
                      ? "border-[#b5121b] text-[#b5121b]"
                      : "border-transparent text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {TAB_LABELS[tab]}
                  {tabCounts[tab] > 0 && (
                    <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs">
                      {tabCounts[tab]}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {error && (
              <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </p>
            )}

            {loading && (
              <p className="text-sm text-slate-500">Đang tải…</p>
            )}

            {!loading && documents.length === 0 && (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
                <FileText size={32} className="mx-auto mb-3 text-slate-300" />
                <p className="text-sm font-medium text-slate-600">
                  Không có tài liệu nào
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Không có tài liệu nào ở trạng thái "{TAB_LABELS[activeTab]}".
                </p>
              </div>
            )}

            {!loading && documents.length > 0 && (
              <div className="space-y-3">
                {documents.map((doc) => {
                  const relevantVersions = doc.versions.filter((v) =>
                    TAB_STATUSES[activeTab].includes(v.processing_status)
                  );
                  return (
                    <div
                      key={doc.id}
                      className="rounded-xl border border-slate-200 bg-white p-4"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <Link
                            href={`/admin/documents/${doc.id}`}
                            className="text-sm font-semibold text-slate-900 hover:text-[#b5121b] truncate block"
                          >
                            {doc.title || doc.document_number || doc.id}
                          </Link>
                          <p className="mt-0.5 text-xs text-slate-500">
                            Số hiệu: {doc.document_number || "—"} · {doc.issued_by || "—"} ·{" "}
                            {doc.issued_date
                              ? new Date(doc.issued_date).toLocaleDateString("vi-VN")
                              : "—"}
                          </p>
                        </div>
                        <div className="flex-shrink-0">
                          {relevantVersions[0] && (
                            <ProcessingStatusBadge
                              status={relevantVersions[0].processing_status}
                            />
                          )}
                        </div>
                      </div>

                      {/* Version actions */}
                      {relevantVersions.map((v) => (
                        <div
                          key={v.id}
                          className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                        >
                          <div className="text-xs text-slate-500">
                            <span className="font-medium">
                              Phiên bản {v.version_number}
                            </span>
                            {v.source_filename && (
                              <span className="ml-2 text-slate-400">
                                · {v.source_filename}
                              </span>
                            )}
                          </div>
                          <div className="flex gap-2">
                            {activeTab === "pending_review" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleAction(v.id, "complete-review")
                                  }
                                  disabled={actionLoading === v.id}
                                  className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                                >
                                  {actionLoading === v.id ? (
                                    <RefreshCw size={12} className="animate-spin" />
                                  ) : (
                                    <CheckCircle2 size={12} />
                                  )}
                                  Hoàn thành xem xét
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleAction(v.id, "reject")}
                                  disabled={actionLoading === v.id}
                                  className="flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                                >
                                  <XCircle size={12} />
                                  Từ chối
                                </button>
                              </>
                            )}
                            {activeTab === "pending_approval" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => void handleAction(v.id, "approve")}
                                  disabled={actionLoading === v.id}
                                  className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                                >
                                  {actionLoading === v.id ? (
                                    <RefreshCw size={12} className="animate-spin" />
                                  ) : (
                                    <CheckCircle2 size={12} />
                                  )}
                                  Duyệt
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleAction(v.id, "reject")}
                                  disabled={actionLoading === v.id}
                                  className="flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                                >
                                  <XCircle size={12} />
                                  Từ chối
                                </button>
                              </>
                            )}
                            {activeTab === "rejected" && (
                              <button
                                type="button"
                                onClick={() => void handleAction(v.id, "republish")}
                                disabled={actionLoading === v.id}
                                className="flex items-center gap-1 rounded-lg border border-[#fcd5d6] bg-white px-3 py-1.5 text-xs font-medium text-[#b5121b] hover:bg-[#fff1f2] disabled:opacity-50"
                              >
                                <RefreshCw size={12} />
                                Xuất bản lại
                              </button>
                            )}
                            <Link
                              href={`/documents/${doc.id}`}
                              className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
                            >
                              Xem chi tiết
                            </Link>
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}

// Type for the API response
interface PolicyDocument {
  id: string;
  title: string;
  documentNumber: string;
  issuedBy: string | null;
  issuedDate: string | null;
}
