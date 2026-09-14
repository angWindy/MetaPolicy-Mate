import { AdminDocuments } from "@/components/admin/AdminDocuments";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default function AdminDocumentsPage() {
  return (
    <AuthGate
      loginPath="/admin/documents"
      loadingFallback={<AuthLoading title="Đang tải kho tài liệu…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Quản lý tài liệu"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminDocuments />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
