"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiRequest } from "../../../lib/api";
import { ApiClientError } from "../../../lib/api";
import { DocumentDetail } from "../../../components/documents/DocumentDetail";
import { AppLayout, AuthGate, AuthLoading } from "../../../components/layout";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import type {
  DocumentContentSection,
  PolicyDocument,
} from "../../../types/documents";

const LEGAL_STATUS_TO_LIBRARY: Record<
  string,
  {
    status: PolicyDocument["status"];
    statusLabel: string;
  }
> = {
  DANG_HIEU_LUC: {
    status: "current",
    statusLabel: "Đang hiệu lực",
  },
  CHO_XU_LY_NOI_DUNG: {
    status: "current",
    statusLabel: "Chờ duyệt",
  },
  BI_THAY_THE: {
    status: "superseded",
    statusLabel: "Bị thay thế",
  },
  HET_HIEU_LUC: {
    status: "expired",
    statusLabel: "Hết hiệu lực",
  },
  BAN_NHAP: {
    status: "current",
    statusLabel: "Bản nháp",
  },
};

type ApiDocument = {
  id: string;
  document_number: string;
  title: string;
  issued_by?: string;
  issued_date?: string;
  effective_date?: string | null;
  legal_status?: string;
  created_at?: string;
  updated_at?: string | null;
};

function mapApiDocument(payload: ApiDocument): PolicyDocument {
  const mapping =
    LEGAL_STATUS_TO_LIBRARY[
      payload.legal_status ?? "DANG_HIEU_LUC"
    ] ?? LEGAL_STATUS_TO_LIBRARY.DANG_HIEU_LUC;
  return {
    id: payload.id,
    title: payload.title,
    documentNumber: payload.document_number,
    category: "quy-dinh",
    categoryLabel: payload.issued_by ?? "Văn bản",
    version: "1",
    effectiveDate:
      payload.effective_date ?? payload.issued_date ?? "",
    effectiveDateLabel:
      payload.effective_date ?? payload.issued_date ?? "—",
    status: mapping.status,
    statusLabel: mapping.statusLabel,
    href: `/documents/${payload.id}`,
  };
}

function fallbackSections(
  document: PolicyDocument,
): DocumentContentSection[] {
  return [
    {
      id: "overview",
      heading: "Thông tin văn bản",
      paragraphs: [
        `${document.title} (${document.documentNumber}) thuộc nhóm ${document.categoryLabel}.`,
        "Sử dụng khung xem PDF nguồn bên dưới để đọc nội dung đầy đủ từ tệp do hệ thống quản lý văn bản trả về.",
      ],
    },
  ];
}

type FetchState =
  | { kind: "loading" }
  | { kind: "missing" }
  | {
      kind: "ready";
      document: PolicyDocument;
      sections: DocumentContentSection[];
    }
  | { kind: "error"; message: string };

async function fetchDocument(
  documentId: string,
): Promise<ApiDocument> {
  return apiRequest<ApiDocument>(
    `/api/v1/regulatory-documents/${documentId}`,
  );
}

export default function DocumentDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const router = useRouter();
  const currentUser = useCurrentUser();
  const [state, setState] = useState<FetchState>({
    kind: "loading",
  });

  useEffect(() => {
    // Wait for useCurrentUser to finish reading localStorage before
    // deciding whether to redirect (avoids bouncing freshly-auth'd users).
    if (!currentUser.isLoaded) return;
    if (!currentUser.isAuthenticated) {
      router.replace(
        `/login?next=${encodeURIComponent(
          `/documents/${slug}`,
        )}`,
      );
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const payload = await fetchDocument(slug);
        if (cancelled) return;
        const document = mapApiDocument(payload);
        setState({
          kind: "ready",
          document,
          sections: fallbackSections(document),
        });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiClientError && err.status === 404) {
          setState({ kind: "missing" });
        } else {
          const message =
            err instanceof Error
              ? err.message
              : "Không tải được văn bản.";
          setState({
            kind: "error",
            message,
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [slug, currentUser.isLoaded, currentUser.isAuthenticated, router]);

  if (state.kind === "loading") {
    return (
      <AuthGate
        loginPath="/login"
        loadingFallback={<AuthLoading title="Đang tải văn bản…" />}
      >
        <AppLayout
          title="Chi tiết Văn bản"
          user={currentUser}
          notificationCount={0}
        >
          <p style={{ padding: 24 }}>Đang tải văn bản…</p>
        </AppLayout>
      </AuthGate>
    );
  }
  if (state.kind === "missing") {
    return (
      <AuthGate
        loginPath="/login"
        loadingFallback={<AuthLoading title="Đang tải văn bản…" />}
      >
        <AppLayout
          title="Chi tiết Văn bản"
          user={currentUser}
          notificationCount={0}
        >
          <div style={{ padding: 24 }}>
            <h2>Không tìm thấy văn bản</h2>
            <p>
              Văn bản {slug} không tồn tại trong hệ thống hoặc
              bạn không có quyền truy cập.
            </p>
            <Link href="/documents">← Quay lại thư viện</Link>
          </div>
        </AppLayout>
      </AuthGate>
    );
  }
  if (state.kind === "error") {
    return (
      <AuthGate
        loginPath="/login"
        loadingFallback={<AuthLoading title="Đang tải văn bản…" />}
      >
        <AppLayout
          title="Chi tiết Văn bản"
          user={currentUser}
          notificationCount={0}
        >
          <div style={{ padding: 24 }}>
            <h2>Không tải được văn bản</h2>
            <p style={{ color: "crimson" }}>{state.message}</p>
            <Link href="/documents">← Quay lại thư viện</Link>
          </div>
        </AppLayout>
      </AuthGate>
    );
  }

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải văn bản…" />}
    >
      <AppLayout
        title="Chi tiết Văn bản"
        user={currentUser}
        notificationCount={0}
      >
        <DocumentDetail
          document={state.document}
          sections={state.sections}
        />
      </AppLayout>
    </AuthGate>
  );
}