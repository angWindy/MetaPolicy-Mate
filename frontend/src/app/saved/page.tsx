"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AuthenticatedLayout, AuthGate, AuthLoading } from "@/components/layout";
import { apiRequest } from "@/lib/api";
import type { PolicyDocument } from "@/types/documents";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { savedDocumentService } from "@/services/savedDocumentService";

type SavedDoc = {
  id: string;
  title: string;
  documentNumber: string;
  href: string;
};

export default function SavedPage() {
  const currentUser = useCurrentUser();
  const [items, setItems] = useState<SavedDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const saved = await savedDocumentService.list(1, 100);
        if (saved.items.length === 0) {
          if (!cancelled) {
            setItems([]);
            setLoading(false);
          }
          return;
        }
        const ids = saved.items.map((s) => s.document_id);
        const res = await apiRequest<{ items: PolicyDocument[] }>(
          "/api/v1/regulatory-documents?page=1&page_size=100",
        );
        const byId = new Map(res.items.map((d) => [d.id, d]));
        const resolved = ids
          .map((id) => byId.get(id))
          .filter((d): d is PolicyDocument => Boolean(d))
          .map((d) => ({
            id: d.id,
            title: d.title,
            documentNumber: d.documentNumber,
            href: `/documents/${d.id}`,
          }));
        if (!cancelled) {
          setItems(resolved);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setError("Không thể tải danh sách tài liệu đã lưu.");
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const isAuthed = currentUser.isAuthenticated;

  async function handleUnsave(documentId: string) {
    try {
      await savedDocumentService.unsave(documentId);
      setItems((prev) => prev.filter((i) => i.id !== documentId));
    } catch {
      setError("Không thể bỏ lưu tài liệu.");
    }
  }

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải tài liệu đã lưu…" />}
    >
      <AuthenticatedLayout title="Tài liệu đã lưu" notificationCount={0}>
        <section className="mx-auto max-w-3xl px-4 py-8">
          <header className="mb-6">
            <h1 className="text-xl font-semibold text-[var(--color-text)]">
              Tài liệu đã lưu
            </h1>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Danh sách các văn bản bạn đã đánh dấu sao.
            </p>
          </header>

          {loading && (
            <p className="text-sm text-slate-500">Đang tải…</p>
          )}

          {error && (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
              <h2 className="text-base font-semibold text-slate-700">
                {isAuthed ? "Chưa có tài liệu đã lưu" : "Bạn chưa đăng nhập"}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                {isAuthed
                  ? "Mở một văn bản bất kỳ và nhấn nút \"Lưu\" để thêm vào danh sách này."
                  : "Vui lòng đăng nhập để sử dụng tính năng này."}
              </p>
              <Link
                href={isAuthed ? "/documents" : "/login"}
                className="mt-4 inline-flex items-center justify-center rounded-lg bg-[#b5121b] px-4 py-2 text-sm font-medium text-white hover:bg-[#930f16]"
              >
                {isAuthed ? "Mở thư viện" : "Đăng nhập"}
              </Link>
            </div>
          )}

          {!loading && items.length > 0 && (
            <ul className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
                >
                  <Link
                    href={item.href}
                    className="flex flex-1 flex-col gap-1"
                  >
                    <span className="text-sm font-semibold text-slate-900">
                      {item.title}
                    </span>
                    <span className="text-xs text-slate-500">
                      Số hiệu: {item.documentNumber || "—"}
                    </span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => handleUnsave(item.id)}
                    className="ml-4 rounded-lg px-3 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50"
                  >
                    Bỏ lưu
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </AuthenticatedLayout>
    </AuthGate>
  );
}
