"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Sidebar, type SidebarItem as LegacySidebarItem } from "./Sidebar";
import {
  StudentHeader,
  type HeaderAccountItem,
  type HeaderNavItem,
} from "./StudentHeader";
import type { UserProfileCardUser } from "./UserProfileCard";
import styles from "./AppLayout.module.css";

export type AppLayoutProps = {
  children: ReactNode;
  title: string;
  user: UserProfileCardUser;
  /**
   * Admin-style vertical navigation. When passed, renders the legacy
   * `Sidebar` component on the left and a slim header on the top
   * instead of the top-bar nav links.
   */
  sidebarItems?: SidebarItem[];
  /**
   * Explicit horizontal nav list for the top bar. When set the layout
   * skips the sidebar and only renders the top-bar nav.
   */
  navItems?: HeaderNavItem[];
  showSearch?: boolean;
  searchPlaceholder?: string;
  notificationCount?: number;
  accountItems?: HeaderAccountItem[];
  onSearch?: (query: string) => void;
  onNotificationsClick?: () => void;
  /**
   * Floating chat widget — only rendered for student-mode pages.
   * Defaults to true; admins can explicitly pass false.
   */
  showFloatingChat?: boolean;
};

/**
 * Lightweight type kept for backwards compatibility — admin pages pass
 * `sidebarItems` and we forward them straight to the `Sidebar`.
 */
export type SidebarItem = LegacySidebarItem;

// Floating chat is client-only because it owns interactive focus,
// pointer-outside-click, and a pathname check that would otherwise
// flash during SSR. `next/dynamic` with `ssr:false` keeps it out of
// the server bundle entirely.
const FloatingChatbot = dynamic(
  () => import("../chat/FloatingChatbot").then((mod) => mod.FloatingChatbot),
  { ssr: false },
);

export function AppLayout({
  children,
  title,
  user,
  sidebarItems,
  navItems,
  showSearch,
  searchPlaceholder,
  notificationCount,
  accountItems,
  onSearch,
  onNotificationsClick,
  showFloatingChat,
}: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") closeSidebar();
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [closeSidebar, sidebarOpen]);

  // Vertical-sidebar mode = admin pages. Top-bar nav mode = anything
  // else that passes `navItems`. Plain top-bar with default student
  // links = bare user pages that omit both props.
  const useSidebar = !!sidebarItems;
  const studentMode = !sidebarItems && !navItems;
  const resolvedNav: HeaderNavItem[] | undefined = navItems;

  const shellClass = `${styles.shell} ${
    useSidebar ? styles.adminShell : styles.studentShell
  }`;

  return (
    <div className={shellClass}>
      <a className={styles.skipLink} href="#main-content">
        Bỏ qua điều hướng
      </a>
      {useSidebar ? (
        <div className={styles.withSidebar}>
          <Sidebar
            items={sidebarItems}
            user={user}
            mobileOpen={sidebarOpen}
            onClose={closeSidebar}
          />
          <div className={styles.workspace}>
            <StudentHeader
              title={title}
              user={user}
              studentMode={false}
              hideBrand
              navItems={undefined}
              showSearch={showSearch ?? true}
              searchPlaceholder={searchPlaceholder}
              notificationCount={notificationCount}
              accountItems={accountItems}
              onSearch={onSearch}
              onNotificationsClick={onNotificationsClick}
              onMenuClick={() => setSidebarOpen(true)}
              menuOpen={sidebarOpen}
            />
            <main id="main-content" className={styles.content} tabIndex={-1}>
              {children}
            </main>
          </div>
        </div>
      ) : (
        <div className={styles.workspace}>
          <StudentHeader
            title={title}
            user={user}
            studentMode={studentMode}
            navItems={resolvedNav}
            showSearch={showSearch ?? studentMode}
            searchPlaceholder={searchPlaceholder}
            notificationCount={notificationCount}
            accountItems={accountItems}
            onSearch={onSearch}
            onNotificationsClick={onNotificationsClick}
            onMenuClick={() => setSidebarOpen(true)}
            menuOpen={sidebarOpen}
          />
          <main id="main-content" className={styles.content} tabIndex={-1}>
            {children}
          </main>
          {showFloatingChat !== false && !useSidebar && <FloatingChatbot />}
        </div>
      )}
    </div>
  );
}
