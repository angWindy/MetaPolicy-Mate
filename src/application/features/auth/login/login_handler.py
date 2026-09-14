from datetime import (
    datetime,
    timedelta,
    timezone,
)
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
from src.application.features.auth.login.login_command import (
    LoginCommand,
)
from src.application.features.auth.login.login_result import (
    LoginResult,
)

from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)

from src.config import Settings
from src.domain.auth.jwt_user import JwtUser
from src.domain.entities.refresh_token import RefreshToken
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


class LoginHandler(
    RequestHandler[
        LoginCommand,
        LoginResult,
    ]
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
        self._department_repository = (
            department_repository
        )
        self._refresh_token_repository = (
            refresh_token_repository
        )
        self._password_hasher = password_hasher
        self._jwt_token_service = (
            jwt_token_service
        )
        self._refresh_token_service = (
            refresh_token_service
        )
        self._unit_of_work = unit_of_work
        self._settings = settings

    async def handle(
        self,
        request: LoginCommand,
    ) -> LoginResult:
        email = request.email.strip().lower()

        if not email:
            raise ConflictException(
                "Email is required."
            )

        if not request.password:
            raise ConflictException(
                "Password is required."
            )

        if not request.device_id.strip():
            raise ConflictException(
                "DeviceId is required."
            )

        user = (
            await self._user_repository.get_by_email(
                email
            )
        )

        if user is None:
            raise ConflictException(
                "Invalid email or password."
            )

        if not user.is_active:
            raise ConflictException(
                "User is not active."
            )

        password_valid = (
            self._password_hasher.verify_password(
                request.password,
                user.password_hash,
            )
        )

        if not password_valid:
            raise ConflictException(
                "Invalid email or password."
            )

        roles = (
            await self._role_repository.get_by_user_id(
                user.id
            )
        )

        if not roles:
            raise ConflictException(
                "User has no assigned role."
            )

        # Hiện demo admin chỉ có một role ADMIN.
        # Nếu sau này nghiệp vụ cho phép nhiều role trong JWT,
        # lúc đó mới thay đổi token contract.
        role = roles[0]

        # Resolve the user's tenant identity from their bound
        # department. ``settings.school_id`` is intentionally NOT
        # used here — it used to hardcode a single bogus UUID that
        # leaked into every JWT, every R2 key, and every Qdrant
        # payload (the ``schools/aaaaaaaa-bbbb-...`` layout bug).
        # Users without a department (e.g. cross-school ADMIN) get
        # ``school_id=None`` and an empty ``school_code`` so they
        # fall through to "cross-school" RBAC paths.
        school_id_for_token: UUID | None = user.department_id
        school_code_for_token: str = ""
        if user.department_id is not None:
            dept = (
                await self
                ._department_repository
                .get_by_id(user.department_id)
            )
            if dept is not None:
                school_code_for_token = dept.code

        jwt_user = JwtUser(
            user_id=user.id,
            email=user.email,
            role=role.code,
            token_version=user.token_version,
            user_type=AuditActorType.SCHOOL_USER,
            school_id=school_id_for_token,
            school_code=school_code_for_token,
        )

        access_token = (
            self._jwt_token_service
            .generate_access_token(
                jwt_user
            )
        )

        raw_refresh_token = (
            self._refresh_token_service
            .generate_token()
        )

        refresh_token_hash = (
            self._refresh_token_service
            .hash_token(
                raw_refresh_token
            )
        )

        now = datetime.now(
            timezone.utc
        )

        expires_at = (
            now
            + timedelta(
                days=(
                    self._settings
                    .jwt_refresh_token_days
                )
            )
        )

        refresh_token = RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=refresh_token_hash,
            device_id=request.device_id.strip(),
            expires_at=expires_at,
            revoked_at=None,
            replaced_by_token_id=None,
            created_at=now,
        )

        await (
            self._refresh_token_repository.add(
                refresh_token
            )
        )

        await self._unit_of_work.save_changes()

        access_token_expires_at = (
            now
            + timedelta(
                minutes=(
                    self._settings
                    .jwt_access_token_minutes
                )
            )
        )

        return LoginResult(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_at=access_token_expires_at,
        )