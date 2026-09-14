"use client";

import { useEffect } from "react";
import Link from "next/link";

import { AuthenticatedLayout, AuthGate, AuthLoading } from "@/components/layout";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useNotifications } from "@/hooks/useNotifications";

export default function NotificationsPage() {
  const currentUser = useCurrentUser();
  const { items, loading, error, list, markRead, markAllRead, unreadCount } =
    useNotifications();

  // Initial load — fetch notifications once when the page mounts.
  // Doing this in the render body (the previous implementation) would
  // risk infinite re-render loops if the API returns an empty list.
  useEffect(() => {
    void list(1, false);
  }, [list]);

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải thông báo…" />}
    >
      <AuthenticatedLayout
        title="Thông báo"
        notificationCount={unreadCount}
      >
        <section className="mx-auto max-w-3xl px-4 py-8">
          <header className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold text-[var(--color-text)]">
                Thông báo
              </h1>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                Các cập nhật quan trọng về tài liệu và phê duyệt.
              </p>
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="rounded-lg border border-[#fcd5d6] bg-white px-3 py-1.5 text-xs font-medium text-[#b5121b] hover:bg-[#fff1f2]"
              >
                Đánh dấu tất cả đã đọc
              </button>
            )}
          </header>

          {loading && (
            <p className="text-sm text-slate-500">Đang tải…</p>
          )}

          {error && (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          )}

          {!loading && items.length === 0 && !error && (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
              <h2 className="text-base font-semibold text-slate-700">
                Chưa có thông báo nào
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Khi có tài liệu cần xem xét hoặc phê duyệt, hệ thống sẽ gửi
                thông báo đến bạn tại đây.
              </p>
              {currentUser.isAuthenticated ? (
                <Link
                  href="/documents"
                  className="mt-4 inline-flex items-center justify-center rounded-lg bg-[#b5121b] px-4 py-2 text-sm font-medium text-white hover:bg-[#930f16]"
                >
                  Mở thư viện
                </Link>
              ) : (
                <Link
                  href="/login"
                  className="mt-4 inline-flex items-center justify-center rounded-lg bg-[#b5121b] px-4 py-2 text-sm font-medium text-white hover:bg-[#930f16]"
                >
                  Đăng nhập
                </Link>
              )}
            </div>
          )}

          {!loading && items.length > 0 && (
            <ul className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
              {items.map((n) => (
                <li
                  key={n.id}
                  className={`flex flex-col gap-1 px-5 py-4 ${n.is_read ? "" : "bg-[#fff1f2]/50"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <span className="text-sm font-semibold text-slate-900">
                        {n.title}
                      </span>
                      {n.body && (
                        <p className="mt-1 text-sm text-slate-600">
                          {n.body}
                        </p>
                      )}
                      <span className="mt-1 text-xs text-slate-400">
                        {new Date(n.created_at).toLocaleString("vi-VN")}
                      </span>
                    </div>
                    {!n.is_read && (
                      <button
                        type="button"
                        onClick={() => markRead(n.id)}
                        className="rounded-lg px-2 py-1 text-xs font-medium text-[#b5121b] hover:bg-[#fff1f2]"
                      >
                        Đánh dấu đã đọc
                      </button>
                    )}
                  </div>
                  {n.related_document_id && (
                    <Link
                      href={`/documents/${n.related_document_id}`}
                      className="mt-2 text-xs font-medium text-[#b5121b] hover:underline"
                    >
                      Xem tài liệu
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </AuthenticatedLayout>
    </AuthGate>
  );
}
