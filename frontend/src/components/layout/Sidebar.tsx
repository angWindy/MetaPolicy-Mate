"use client";

import {
  Bell,
  BookOpenCheck,
  Bookmark,
  Clock3,
  FileText,
  Home,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode, Ref } from "react";

import styles from "./Sidebar.module.css";
import { UserProfileCard, type UserProfileCardUser } from "./UserProfileCard";

export type SidebarItem = {
  href: string;
  label: string;
  icon?: ReactNode;
  /**
   * Marker kept for documentation purposes — all routes require
   * authentication now (AuthGate on every page), so this flag is no
   * longer used to hide items for anonymous viewers.
   */
  requiresAuth?: boolean;
};

export type SidebarUser = UserProfileCardUser;

export type SidebarProps = {
  items?: SidebarItem[];
  user: SidebarUser;
  className?: string;
  mobileOpen?: boolean;
  onClose?: () => void;
  closeButtonRef?: Ref<HTMLButtonElement>;
};

const defaultItems: SidebarItem[] = [
  { href: "/student", label: "Trang chủ", icon: <Home size={18} /> },
  { href: "/documents", label: "Thư viện văn bản", icon: <FileText size={18} />, requiresAuth: true },
  { href: "/history", label: "Lịch sử", icon: <Clock3 size={18} />, requiresAuth: true },
  { href: "/saved", label: "Đã lưu", icon: <Bookmark size={18} />, requiresAuth: true },
  { href: "/notifications", label: "Thông báo", icon: <Bell size={18} />, requiresAuth: true },
  { href: "/profile", label: "Hồ sơ", icon: <UserRound size={18} />, requiresAuth: true },
];

function isActiveRoute(pathname: string, href: string): boolean {
  const normalizePath = (value: string) =>
    value !== "/" ? value.replace(/\/+$/, "") : value;
  const currentPath = normalizePath(pathname);
  const targetPath = normalizePath(href);
  if (targetPath === "/") return currentPath === targetPath;
  return (
    currentPath === targetPath || currentPath.startsWith(`${targetPath}/`)
  );
}

export function Sidebar({
  items = defaultItems,
  user,
  className = "",
  mobileOpen = false,
  onClose,
  closeButtonRef,
}: SidebarProps) {
  const pathname = usePathname();
  const profileActive = isActiveRoute(pathname, "/profile");
  // Admin mode is detected by inspecting the items passed in (admin pages
  // pass an explicit list). The default list is always treated as the
  // student/staff sidebar so the brand stays accurate.
  const admin = items !== defaultItems && items.some((item) => item.href.startsWith("/admin"));

  return (
    <aside
      id="student-sidebar"
      className={`${styles.sidebar} ${mobileOpen ? styles.mobileOpen : ""} ${className}`.trim()}
      aria-label="Thanh điều hướng"
    >
      <button
        ref={closeButtonRef}
        className={styles.closeButton}
        type="button"
        aria-label="Đóng menu"
        onClick={onClose}
      >
        <X size={20} aria-hidden="true" />
      </button>
      <Link
        className={styles.brand}
        href={admin ? "/admin" : "/"}
        aria-label="PolicyMate AI - Trang chủ"
        onClick={onClose}
      >
        <span className={styles.logoMark} aria-hidden="true">
          {admin ? <ShieldCheck size={21} /> : <BookOpenCheck size={21} />}
        </span>
        <span className={styles.logoCopy}>
          <span className={styles.logoText}>
            PolicyMate <strong>AI</strong>
          </span>
          <small>{admin ? "Không gian quản trị" : "Cổng tra cứu quy chế"}</small>
        </span>
      </Link>
      <div className={styles.workspaceLabel}>
        {admin ? "Quản trị hệ thống" : "Dành cho sinh viên"}
      </div>
      <nav className={styles.navigation} aria-label="Điều hướng chính">
        {items.map((item) => {
          const active = isActiveRoute(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.navItem} ${active ? styles.active : ""}`.trim()}
              aria-current={active ? "page" : undefined}
              onClick={onClose}
            >
              <span className={styles.navIcon} aria-hidden="true">
                {item.icon ?? <span className={styles.iconDot} />}
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <UserProfileCard user={user} active={profileActive} onNavigate={onClose} />
    </aside>
  );
}
