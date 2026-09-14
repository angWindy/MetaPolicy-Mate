import { AdminOrganizations } from "@/components/admin/AdminOrganizations";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default function AdminOrganizationsPage() {
  return (
    <AuthGate
      loginPath="/admin/organizations"
      loadingFallback={<AuthLoading title="Đang tải quản lý đơn vị…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Quản lý đơn vị"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminOrganizations />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
