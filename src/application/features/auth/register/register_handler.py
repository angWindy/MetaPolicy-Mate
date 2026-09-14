"""Register feature — creates a new user with role auto-assigned based on school_code."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.interfaces.jwt_token_service import (
    JwtTokenService,
)
from src.application.common.interfaces.password_hasher import (
    PasswordHasher,
)
from src.application.common.interfaces.refresh_token_service import (
    RefreshTokenService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.auth.register.register_command import (
    RegisterCommand,
)
from src.application.features.auth.register.register_result import (
    RegisterResult,
)
from src.config import Settings
from src.domain.auth.jwt_user import JwtUser
from src.domain.entities.refresh_token import RefreshToken
from src.domain.entities.user import User
from src.domain.enums.audit_actor_type import (
    AuditActorType,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


# ─── Role assignment logic ───────────────────────────────────────────────────

# Map school_code (from register form) to role_code.
#
# P-234 simplified the RBAC to two roles:
#   - ADMIN   : full platform administrator (all permissions)
#   - USER    : everyone else (Lecturer, Leader, Reviewer merged).
#
# The previous three roles (LECTURER, LEADER, REVIEWER) had overlapping
# permission sets and no clear functional boundary in the demo. They are
# collapsed into a single USER role that gets the union of permissions.
# New school_code values default to USER.
_SCHOOL_CODE_TO_ROLE: dict[str, str] = {
    "ADMIN":   "ADMIN",
    "HUST":    "USER",
    "HUCE":    "USER",
    "STUDENT": "USER",
}


def _resolve_role_code(school_code: str, email: str) -> str:
    """Derive role code from school_code (form field) or email."""
    upper = school_code.strip().upper()
    if upper in _SCHOOL_CODE_TO_ROLE:
        return _SCHOOL_CODE_TO_ROLE[upper]
    # Fallback: derive from email domain
    lower_email = email.lower()
    if "admin" in lower_email:
        return "ADMIN"
    return "USER"


# ─── Handler ─────────────────────────────────────────────────────────────────

class RegisterHandler(
    RequestHandler[RegisterCommand, RegisterResult],
):
    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
        department_repository: DepartmentRepository,
        refresh_token_repository: RefreshTokenRepository,
        password_hasher: PasswordHasher,
        jwt_token_service: JwtTokenService,
        refresh_token_service: RefreshTokenService,
        unit_of_work: UnitOfWork,
        settings: Settings,
    ) -> None:
        self._user_repository = user_repository
        self._role_repository = role_repository
        self._department_repository = department_repository
        self._refresh_token_repository = refresh_token_repository
        self._password_hasher = password_hasher
        self._jwt_token_service = jwt_token_service
        self._refresh_token_service = refresh_token_service
        self._unit_of_work = unit_of_work
        self._settings = settings

    async def handle(self, request: RegisterCommand) -> RegisterResult:
        email = request.email.strip().lower()
        full_name = request.full_name.strip()
        school_code = request.school_code.strip().upper()

        # 1. Validate required fields
        if not email:
            raise ConflictException("Email is required.")
        if not request.password:
            raise ConflictException("Password is required.")
        if len(request.password) < 6:
            raise ConflictException("Mật khẩu phải có ít nhất 6 ký tự.")
        if not full_name:
            raise ConflictException("Họ tên là bắt buộc.")

        # 2. Check email not already taken
        existing = await self._user_repository.get_by_email(email)
        if existing is not None:
            raise ConflictException(
                "Email đã được sử dụng. Vui lòng đăng nhập hoặc dùng email khác."
            )

        # 3. Resolve department_id from school_code
        department_id = None
        department_name = None
        if school_code and school_code not in ("ADMIN", "STUDENT", ""):
            dept = await self._department_repository.get_by_code(school_code)
            if dept is None:
                raise ConflictException(
                    f"Mã trường '{school_code}' không hợp lệ. "
                    "Vui lòng chọn: HUST, HUCE, hoặc để trống."
                )
            if not dept.is_active:
                raise ConflictException(
                    f"Trường '{school_code}' hiện không hoạt động. Liên hệ quản trị viên."
                )
            department_id = dept.id
            department_name = dept.name

        # 4. Resolve role from school_code / email
        role_code = _resolve_role_code(school_code, email)
        role = await self._role_repository.get_by_code(role_code)
        if role is None:
            role = await self._role_repository.get_by_code("USER")
        if role is None:
            raise ConflictException(
                "Không tìm thấy role mặc định trong hệ thống. Liên hệ quản trị viên."
            )

        # 5. Create user
        now = datetime.now(timezone.utc)
        user = User(
            id=uuid4(),
            email=email,
            password_hash=self._password_hasher.hash_password(request.password),
            full_name=full_name,
            department_id=department_id,
            token_version=0,
            is_active=True,
            created_at=now,
            updated_at=None,
        )
        await self._user_repository.add(user)
        await self._unit_of_work.flush()

        # 6. Assign role
        await self._role_repository.replace_for_user(user.id, [role.id])

        # 7. Generate JWT access token. Per-user tenant identity comes
        # from the freshly-bound department, NOT from settings
        # (settings-based tenant identity used to hardcode a single
        # bogus UUID that leaked into every JWT, every R2 key, and
        # every Qdrant payload).
        jwt_school_id: UUID | None = user.department_id
        jwt_school_code: str = ""
        if user.department_id is not None:
            dept = (
                await self
                ._department_repository
                .get_by_id(user.department_id)
            )
            if dept is not None:
                jwt_school_code = dept.code

        jwt_user = JwtUser(
            user_id=user.id,
            email=user.email,
            role=role.code,
            token_version=user.token_version,
            user_type=AuditActorType.SCHOOL_USER,
            school_id=jwt_school_id,
            school_code=jwt_school_code,
        )
        access_token = self._jwt_token_service.generate_access_token(jwt_user)

        # 8. Generate and persist refresh token
        raw_refresh_token = self._refresh_token_service.generate_token()
        refresh_token_hash = self._refresh_token_service.hash_token(raw_refresh_token)
        refresh_expires_at = now + timedelta(days=self._settings.jwt_refresh_token_days)

        refresh_token = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=refresh_token_hash,
            device_id="web-register",
            expires_at=refresh_expires_at,
            revoked_at=None,
            replaced_by_token_id=None,
            created_at=now,
        )
        await self._refresh_token_repository.add(refresh_token)
        await self._unit_of_work.save_changes()

        access_token_expires_at = now + timedelta(minutes=self._settings.jwt_access_token_minutes)

        return RegisterResult(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_at=access_token_expires_at,
            user_id=str(user.id),
            email=email,
            full_name=full_name,
            role=role.code,
            department=department_name,
        )
