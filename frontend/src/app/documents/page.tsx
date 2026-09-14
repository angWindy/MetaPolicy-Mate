"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiRequest } from "../../lib/api";
import type {
  AdminDocument,
  AdminDocumentStatus,
} from "../../types/admin";
import { DocumentLibrary } from "../../components/documents/DocumentLibrary";
import type { PolicyDocument } from "../../types/documents";
import { AuthenticatedLayout, AuthGate, AuthLoading } from "../../components/layout";
import { useCurrentUser } from "../../hooks/useCurrentUser";

const STATUS_LABEL: Record<AdminDocumentStatus, string> = {
  DANG_HIEU_LUC: "Đang hiệu lực",
  CHO_XU_LY_NOI_DUNG: "Chờ duyệt",
  BI_THAY_THE: "Bị thay thế",
  HET_HIEU_LUC: "Hết hiệu lực",
  BAN_NHAP: "Bản nháp",
};

const STATUS_LIBRARY: Record<
  AdminDocumentStatus,
  PolicyDocument["status"]
> = {
  DANG_HIEU_LUC: "current",
  CHO_XU_LY_NOI_DUNG: "current",
  BI_THAY_THE: "superseded",
  HET_HIEU_LUC: "expired",
  BAN_NHAP: "current",
};

function mapItem(item: AdminDocument): PolicyDocument {
  const status = STATUS_LIBRARY[item.status] ?? "current";
  const statusLabel = STATUS_LABEL[item.status] ?? "—";
  return {
    id: item.id,
    title: item.title,
    documentNumber: item.documentNumber,
    category: "quy-dinh",
    categoryLabel: item.documentType || "Văn bản",
    version: item.version || "1",
    effectiveDate: item.effectiveDate || "",
    effectiveDateLabel: item.effectiveDate || "—",
    status,
    statusLabel,
    href: `/documents/${item.id}`,
  };
}

export default function DocumentsPage() {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const [docs, setDocs] = useState<PolicyDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Wait for useCurrentUser to finish reading localStorage before
    // deciding whether to redirect. Starting with isAuthenticated=false would
    // bounce a freshly-logged-in user back to /login.
    if (!currentUser.isLoaded) return;
    if (!currentUser.isAuthenticated) {
      router.replace(
        `/login?next=${encodeURIComponent("/documents")}`,
      );
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await apiRequest<{
          items: AdminDocument[];
          total: number;
        }>(
          "/api/v1/regulatory-documents?page=1&page_size=100",
        );
        if (cancelled) return;
        setDocs((res.items ?? []).map(mapItem));
      } catch (e) {
        if (cancelled) return;
        setError(
          (e as Error).message ?? "Không tải được danh sách văn bản",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentUser.isLoaded, currentUser.isAuthenticated, router]);

  if (!currentUser.isLoaded) {
    return (
      <AuthGate
        loginPath="/login"
        loadingFallback={<AuthLoading title="Đang tải thư viện…" />}
      >
        <AuthenticatedLayout
          title="Thư viện Quy chế"
          notificationCount={0}
        >
          <p style={{ padding: 24 }}>Đang tải phiên đăng nhập…</p>
        </AuthenticatedLayout>
      </AuthGate>
    );
  }
  if (!currentUser.isAuthenticated) {
    return (
      <AuthGate
        loginPath="/login"
        loadingFallback={<AuthLoading title="Đang tải thư viện…" />}
      >
        <AuthenticatedLayout
          title="Thư viện Quy chế"
          notificationCount={0}
        >
          <p style={{ padding: 24 }}>
            Đang chuyển hướng tới trang đăng nhập…
          </p>
        </AuthenticatedLayout>
      </AuthGate>
    );
  }

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải thư viện…" />}
    >
      <AuthenticatedLayout
        title="Thư viện Quy chế"
        notificationCount={0}
      >
      {loading && (
        <p style={{ padding: 16 }}>Đang tải…</p>
      )}
      {error && (
        <p style={{ color: "crimson", padding: 16 }}>
          {error}
        </p>
      )}
      {!loading && !error && docs.length === 0 && (
        <div style={{ padding: 24 }}>
          <h2>Thư viện trống</h2>
          <p>
            Hiện chưa có văn bản nào trong hệ thống. Vui lòng upload từ
            trang quản trị hoặc kiểm tra lại kết nối backend.
          </p>
          <Link href="/admin/documents">
            → Đi tới trang quản trị
          </Link>
        </div>
      )}
      {!loading && !error && docs.length > 0 && (
        <DocumentLibrary documents={docs} />
      )}
    </AuthenticatedLayout>
    </AuthGate>
  );
}