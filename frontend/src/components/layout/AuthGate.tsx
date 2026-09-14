"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useCurrentUser } from "../../hooks/useCurrentUser";

export type AuthGateProps = {
  children: ReactNode;
  /**
   * Path to redirect to when the user is not authenticated. Defaults to
   * the current URL (preserving the intended destination after login).
   */
  loginPath?: string;
  /**
   * Optional fallback to render while auth state is being resolved
   * (before localStorage has been read on the client). Useful for
   * `useEffect`-heavy pages that would otherwise flash error states.
   */
  loadingFallback?: ReactNode;
};

/**
 * Client-side guard that sends unauthenticated viewers to /login while
 * preserving the requested URL via the `next` query param.
 *
 * Pages should NOT read `isAuthenticated` directly to decide on redirects
 * — `useCurrentUser` starts as ANONYMOUS to match server-rendered HTML,
 * so without `isLoaded` the page would bounce a freshly-logged-in user
 * back to /login. This component waits for the first sync to complete
 * before making that decision.
 */
export function AuthGate({
  children,
  loginPath,
  loadingFallback,
}: AuthGateProps) {
  const router = useRouter();
  const pathname = usePathname();
  const currentUser = useCurrentUser();

  const target = loginPath ?? pathname ?? "/";

  useEffect(() => {
    if (!currentUser.isLoaded) return;
    if (currentUser.isAuthenticated) return;
    const next = encodeURIComponent(target);
    router.replace(`/login?next=${next}`);
  }, [
    currentUser.isLoaded,
    currentUser.isAuthenticated,
    router,
    target,
  ]);

  if (!currentUser.isLoaded) {
    if (loadingFallback) return <>{loadingFallback}</>;
    return null;
  }

  if (!currentUser.isAuthenticated) {
    // Redirect is in-flight; render nothing to avoid flashing gated UI.
    if (loadingFallback) return <>{loadingFallback}</>;
    return null;
  }

  return <>{children}</>;
}