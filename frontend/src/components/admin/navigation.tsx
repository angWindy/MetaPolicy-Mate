import { Building2, FileCheck2, FileText, LayoutDashboard, ScrollText, Settings, ShieldCheck, Users } from "lucide-react";
import type { SidebarItem } from "../layout/Sidebar";

export const adminSidebarItems: SidebarItem[] = [
  { href: "/admin", label: "Tổng quan", icon: <LayoutDashboard size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/organizations", label: "Đơn vị", icon: <Building2 size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/documents", label: "Tài liệu", icon: <FileText size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/users", label: "Người dùng", icon: <Users size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/permissions", label: "Phân quyền", icon: <ShieldCheck size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/review", label: "Duyệt tài liệu", icon: <FileCheck2 size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/activity", label: "Nhật ký hoạt động", icon: <ScrollText size={19} strokeWidth={1.8} />, requiresAuth: true },
  { href: "/admin/settings", label: "Cài đặt", icon: <Settings size={19} strokeWidth={1.8} />, requiresAuth: true },
];
