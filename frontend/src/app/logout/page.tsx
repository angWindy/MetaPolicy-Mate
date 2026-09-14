"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { apiRequest } from "@/lib/api";
import { CURRENT_USER_TOKEN_KEY } from "@/hooks/useCurrentUser";

/**
 * Dedicated /logout route — clears all session state from
 * localStorage, then redirects to /. We also try to invalidate the
 * refresh token server-side so a stolen token cannot be reused after
 * the user clicks "Đăng xuất". Failures are silent because the local
 * cleanup is the user-visible contract — server-side revocation is a
 * defense-in-depth measure.
 */
export default function LogoutPage() {
  const router = useRouter();

  useEffect(() => {
    const refreshToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem("policymate_refresh_token")
        : null;

    // Always clear local state synchronously, even if the server call
    // fails (network error, token already expired, etc.).
    try {
      window.localStorage.removeItem(CURRENT_USER_TOKEN_KEY);
      window.localStorage.removeItem("policymate_refresh_token");
      window.localStorage.removeItem("policymate_user_cache");
      window.dispatchEvent(new Event("storage"));
    } catch {
      // ignore — localStorage might be unavailable (private mode etc.)
    }

    if (refreshToken) {
      // Best-effort server-side revocation. Errors are swallowed.
      void apiRequest("/api/v1/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => undefined);
    }

    router.replace("/");
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm text-center">
        <p className="text-sm text-slate-500">Đang đăng xuất…</p>
      </div>
    </div>
  );
}
