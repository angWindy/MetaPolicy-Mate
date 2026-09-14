"use client";

import type { ReactNode } from "react";

import { AppSidebar } from "./AppSidebar";

export interface AdminLayoutProps {
  children: ReactNode;
}

/**
 * AdminLayout — wraps admin-facing routes (``/admin/*``).
 *
 * Renders the unified AppSidebar with admin items. Pages inside
 * (in the ``(admin)`` route group) are wrapped by
 * ``RequireRole(["ADMIN"])`` for hard client-side redirects. The sidebar
 * itself is role-aware so non-admin tokens never see admin links.
 */
export function AdminLayout({ children }: AdminLayoutProps) {
  return (
    <div className="layout admin">
      <AppSidebar />
      <main className="content" data-testid="admin-layout-main">
        {children}
      </main>
    </div>
  );
}