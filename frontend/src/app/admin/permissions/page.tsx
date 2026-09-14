import { AdminPermissions } from "@/components/admin/AdminPermissions";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default function AdminPermissionsPage() {
  return (
    <AuthGate
      loginPath="/admin/permissions"
      loadingFallback={<AuthLoading title="Đang tải quản lý phân quyền…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Phân quyền"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminPermissions />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
