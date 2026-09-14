"use client";

import {
  Bookmark,
  Clock3,
  FileText,
  Home,
} from "lucide-react";

import type { HeaderNavItem } from "@/components/layout/StudentHeader";

/**
 * Canonical student top-bar navigation. Single source of truth so every
 * authenticated user page (``/student`` and its sub-routes) renders the
 * same four links and the brand collapses the same way.
 *
 * Hỏi AI is intentionally absent — the Ask AI surface has been folded
 * into the floating chat widget anchored to the bottom-right of every
 * student page, so the top-bar no longer carries a dedicated link.
 * Other user pages (history, saved, profile, notifications) live in
 * the account dropdown menu.
 */
export const studentNavItems: HeaderNavItem[] = [
  {
    href: "/student",
    label: "Trang chủ",
    icon: <Home size={17} strokeWidth={1.8} aria-hidden="true" />,
  },
  {
    href: "/documents",
    label: "Thư viện văn bản",
    icon: <FileText size={17} strokeWidth={1.8} aria-hidden="true" />,
  },
  {
    href: "/history",
    label: "Lịch sử",
    icon: <Clock3 size={17} strokeWidth={1.8} aria-hidden="true" />,
  },
  {
    href: "/saved",
    label: "Đã lưu",
    icon: <Bookmark size={17} strokeWidth={1.8} aria-hidden="true" />,
  },
];
