"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthenticatedLayout, AuthGate, AuthLoading } from "@/components/layout";
import { useCurrentUser, CURRENT_USER_TOKEN_KEY } from "@/hooks/useCurrentUser";

/**
 * Profile page. Until the backend exposes a ``GET /api/v1/users/me``
 * endpoint, we derive everything from the JWT claims (which already carry
 * user id, email, role, school id). Password change is intentionally
 * disabled — the backend does not yet expose that endpoint and we do not
 * want to silently swallow a 404 from the user.
 */
export default function ProfilePage() {
  const router = useRouter();
  const currentUser = useCurrentUser();
  const [logoutToast, setLogoutToast] = useState<string | null>(null);

  useEffect(() => {
    if (!logoutToast) return;
    const id = setTimeout(() => setLogoutToast(null), 3000);
    return () => clearTimeout(id);
  }, [logoutToast]);

  function handleLogout() {
    try {
      window.localStorage.removeItem(CURRENT_USER_TOKEN_KEY);
      window.localStorage.removeItem("policymate_refresh_token");
      window.localStorage.removeItem("policymate_user_cache");
      // Dispatch storage event so useCurrentUser hook refreshes state
      window.dispatchEvent(new Event("storage"));
      setLogoutToast("Đã đăng xuất khỏi thiết bị này.");
      // Redirect to home page after a brief moment to show the toast
      window.setTimeout(() => {
        router.push("/");
      }, 500);
    } catch {
      setLogoutToast("Không thể đăng xuất. Vui lòng thử lại.");
    }
  }

  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải hồ sơ…" />}
    >
      <AuthenticatedLayout title="Hồ sơ cá nhân" notificationCount={0}>
        <section className="mx-auto max-w-3xl px-4 py-8">
          <header className="mb-6">
            <h1 className="text-xl font-semibold text-[var(--color-text)]">
              Hồ sơ cá nhân
            </h1>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Thông tin tài khoản được lấy từ phiên đăng nhập hiện tại.
            </p>
          </header>

          {!currentUser.isLoaded ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
              <p className="text-sm text-slate-500">
                Đang tải phiên đăng nhập…
              </p>
            </div>
          ) : (
          <div className="space-y-4">
            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                Thông tin chung
              </h2>
              <dl className="mt-4 grid grid-cols-1 gap-y-3 text-sm sm:grid-cols-2 sm:gap-x-6">
                <div>
                  <dt className="text-slate-500">Email</dt>
                  <dd className="font-medium text-slate-900">
                    {currentUser.email ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Vai trò</dt>
                  <dd className="font-medium text-slate-900">
                    {currentUser.rawRole ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">User ID</dt>
                  <dd className="break-all font-mono text-xs text-slate-700">
                    {currentUser.userId ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">School ID</dt>
                  <dd className="break-all font-mono text-xs text-slate-700">
                    {currentUser.schoolId ?? "—"}
                  </dd>
                </div>
              </dl>
            </article>

            <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
                Bảo mật
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Tính năng đổi mật khẩu sẽ được bổ sung sau khi backend hỗ trợ.
              </p>
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleLogout}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Đăng xuất khỏi thiết bị này
                </button>
              </div>
              {logoutToast && (
                <p className="mt-3 text-xs text-emerald-700" role="status">
                  {logoutToast}
                </p>
              )}
            </article>
          </div>
        )}
      </section>
    </AuthenticatedLayout>
    </AuthGate>
  );
}