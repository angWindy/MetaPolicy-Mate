"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useCurrentUser } from "../../hooks/useCurrentUser";

export type UserRole = "ADMIN" | "USER";

export interface RequireRoleProps {
  /** Roles allowed to view the protected subtree. */
  roles: UserRole[];
  /** Where to redirect when the user lacks the role. Defaults to /login. */
  redirectTo?: string;
  /** Optional fallback shown while we wait for the JWT to load. */
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * RequireRole — client-side route guard.
 *
 * Wraps the page subtree and waits for ``useCurrentUser().isLoaded`` to
 * become true. If the user is not authenticated, redirects to the login
 * page. If the user's role isn't in the allowed list, redirects to the
 * configured fallback (defaults to ``/`` for users blocked from admin).
 *
 * This is *one* of the defenses — the backend MUST also enforce RBAC.
 * Client guards are only there to avoid flashing protected UI to
 * anonymous viewers.
 */
export function RequireRole({
  roles,
  redirectTo = "/login",
  fallback = null,
  children,
}: RequireRoleProps) {
  const user = useCurrentUser();
  const router = useRouter();

  useEffect(() => {
    if (!user.isLoaded) return;
    if (!user.isAuthenticated) {
      router.replace(`${redirectTo}?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    const allowedRole = user.rawRole && roles.includes(user.rawRole as UserRole);
    if (!allowedRole) {
      router.replace("/");
    }
  }, [user.isLoaded, user.isAuthenticated, user.rawRole, roles, redirectTo, router]);

  if (!user.isLoaded) return fallback;
  if (!user.isAuthenticated) return fallback;
  if (!user.rawRole || !roles.includes(user.rawRole as UserRole)) return fallback;

  return <>{children}</>;
}