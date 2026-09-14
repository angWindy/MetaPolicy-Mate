"use client";

import type { ReactNode } from "react";

import { AppSidebar } from "./AppSidebar";

export interface UserLayoutProps {
  children: ReactNode;
}

/**
 * UserLayout — wraps user-facing routes (chat, documents, history, etc.).
 *
 * Renders the unified AppSidebar with the user item list. Pages inside
 * (in the ``(user)`` route group) are wrapped by ``RequireRole(["USER"])``
 * at the page level for hard redirects, but the sidebar itself hides
 * admin links automatically for non-admin tokens.
 */
export function UserLayout({ children }: UserLayoutProps) {
  return (
    <div className="layout user">
      <AppSidebar />
      <main className="content" data-testid="user-layout-main">
        {children}
      </main>
    </div>
  );
}