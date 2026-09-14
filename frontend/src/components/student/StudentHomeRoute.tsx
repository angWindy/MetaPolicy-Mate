"use client";

import { AuthenticatedLayout } from "@/components/layout";

import { studentNavItems } from "./studentNav";
import { StudentHomePage } from "./StudentHomePage";

export type StudentHomeRouteProps = {
  userName?: string;
};

/**
 * Student home page wrapper. Wires the standard `AppLayout` top-bar
 * shell (with shared student nav) around the content-only
 * `StudentHomePage` so the brand link, nav, search, account menu and
 * floating chatbot are consistent with the rest of the app.
 */
export default function StudentHomeRoute({ userName }: StudentHomeRouteProps) {
  return (
    <AuthenticatedLayout
      title="Trang chủ sinh viên"
      navItems={studentNavItems}
      notificationCount={0}
    >
      <StudentHomePage userName={userName} />
    </AuthenticatedLayout>
  );
}
