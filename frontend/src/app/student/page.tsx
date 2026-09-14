import StudentHomeRoute from "@/components/student/StudentHomeRoute";
import { AuthGate, AuthLoading } from "@/components/layout";

export default function StudentPage() {
  return (
    <AuthGate
      loginPath="/login"
      loadingFallback={<AuthLoading title="Đang tải trang chủ…" />}
    >
      <StudentHomeRoute />
    </AuthGate>
  );
}
