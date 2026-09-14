"use client";

import { useMemo } from "react";
import {
  Building2,
  FileCheck2,
  FileText,
  History,
  LayoutDashboard,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";

import { useCurrentUser, type CurrentUser } from "../../hooks/useCurrentUser";
import { Sidebar, type SidebarItem, type SidebarUser } from "./Sidebar";
import type { UserRole } from "./RequireRole";

export type { SidebarItem } from "./Sidebar";

const USER_ITEMS: SidebarItem[] = [
  { href: "/student", label: "Trang chủ", icon: <FileText size={19} strokeWidth={1.8} /> },
  { href: "/documents", label: "Tài liệu", icon: <FileText size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/history", label: "Lịch sử", icon: <History size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/saved", label: "Đã lưu", icon: <FileText size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/notifications", label: "Thông báo", icon: <FileText size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/profile", label: "Hồ sơ", icon: <FileText size={19} strokeWidth={1.8} />, requiresAuth: true },
];

const ADMIN_ITEMS: SidebarItem[] = [
  { href: "/admin", label: "Tổng quan", icon: <LayoutDashboard size={19} strokeWidth={1.8} /> },
  { href: "/admin/organizations", label: "Đơn vị", icon: <Building2 size={19} strokeWidth={1.8} /> },
  { href: "/admin/documents", label: "Tài liệu", icon: <FileText size={19} strokeWidth={1.8} /> },
  { href: "/admin/users", label: "Người dùng", icon: <Users size={19} strokeWidth={1.8} /> },
  { href: "/admin/permissions", label: "Phân quyền", icon: <ShieldCheck size={19} strokeWidth={1.8} /> },
  { href: "/admin/review", label: "Duyệt tài liệu", icon: <FileCheck2 size={19} strokeWidth={1.8} /> },
  { href: "/admin/activity", label: "Nhật ký hoạt động", icon: <ScrollText size={19} strokeWidth={1.8} /> },
  { href: "/admin/settings", label: "Cài đặt", icon: <Settings size={19} strokeWidth={1.8} /> },
];

function rolesForUser(user: CurrentUser): UserRole[] {
  if (user.rawRole === "ADMIN") return ["ADMIN"];
  return ["USER"];
}

function pickSidebarItems(user: CurrentUser): SidebarItem[] {
  const roles = rolesForUser(user);
  if (roles.includes("ADMIN") && user.rawRole === "ADMIN") {
    return ADMIN_ITEMS;
  }
  return USER_ITEMS;
}

function sidebarUserFromCurrent(user: CurrentUser): SidebarUser {
  return {
    name: user.name,
    role: user.role,
    studentId: user.studentId,
    department: user.department,
  };
}

export interface AppSidebarProps {
  /** Optional override for the item list; mostly used by tests. */
  items?: SidebarItem[];
}

/**
 * Unified sidebar that picks the right item list based on the user's
 * role. Used by both ``UserLayout`` and ``AdminLayout`` — call sites
 * pass ``<AppSidebar />`` and the role detection happens inside.
 */
export function AppSidebar({ items }: AppSidebarProps = {}) {
  const user = useCurrentUser();
  const visibleItems = useMemo<SidebarItem[]>(() => {
    if (items) return items;
    return pickSidebarItems(user);
  }, [items, user]);

  return (
    <Sidebar
      items={visibleItems}
      user={sidebarUserFromCurrent(user)}
    />
  );
}