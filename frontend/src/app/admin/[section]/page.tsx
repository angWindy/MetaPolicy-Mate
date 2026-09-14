import { AdminSectionPlaceholder } from "@/components/admin/AdminSectionPlaceholder";
import { adminSidebarItems } from "@/components/admin/navigation";
import {
  AuthenticatedLayout,
  AuthGate,
  AuthLoading,
  RequireRole,
} from "@/components/layout";

export default async function AdminSectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  return (
    <AuthGate
      loginPath="/admin"
      loadingFallback={<AuthLoading title="Đang tải trang quản trị…" />}
    >
      <RequireRole roles={["ADMIN"]}>
        <AuthenticatedLayout
          title="Quản trị hệ thống"
          sidebarItems={adminSidebarItems}
          notificationCount={0}
        >
          <AdminSectionPlaceholder section={section} />
        </AuthenticatedLayout>
      </RequireRole>
    </AuthGate>
  );
}
