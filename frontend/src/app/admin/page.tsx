import { AdminDashboard } from "@/components/admin/AdminDashboard";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default function AdminPage() {
  return (
    <AuthGate
      loginPath="/admin"
      loadingFallback={<AuthLoading title="Đang tải bảng điều khiển…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Tổng quan hệ thống"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminDashboard />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
