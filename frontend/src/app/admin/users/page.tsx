import { AdminUsers } from "@/components/admin/AdminUsers";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default function AdminUsersPage() {
  return (
    <AuthGate
      loginPath="/admin/users"
      loadingFallback={<AuthLoading title="Đang tải quản lý người dùng…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Quản lý người dùng"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminUsers />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
