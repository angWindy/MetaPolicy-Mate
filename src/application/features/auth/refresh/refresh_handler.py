from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
)
from src.application.common.interfaces.jwt_token_service import (
    JwtTokenService,
)
from src.application.common.interfaces.refresh_token_service import (
    RefreshTokenService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.features.auth.refresh.refresh_command import (
    RefreshCommand,
)
from src.application.features.auth.refresh.refresh_result import (
    RefreshResult,
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

from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)


class RefreshHandler(
    RequestHandler[
        RefreshCommand,
        RefreshResult,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
        department_repository: DepartmentRepository,
        refresh_token_repository: RefreshTokenRepository,
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

        self._jwt_token_service = (
            jwt_token_service
        )

        self._refresh_token_service = (
            refresh_token_service
        )

        self._unit_of_work = (
            unit_of_work
        )

        self._settings = settings

    async def handle(
        self,
        request: RefreshCommand,
    ) -> RefreshResult:
        if not request.refresh_token:
            raise UnauthorizedException(
                "Invalid refresh token."
            )

        token_hash = (
            self._refresh_token_service
            .hash_token(
                request.refresh_token
            )
        )

        # Lock token row cho đến khi
        # rotation được commit.
        # Request refresh thứ hai dùng
        # cùng token phải chờ request
        # thứ nhất hoàn tất.
        stored_token = (
            await self
            ._refresh_token_repository
            .get_by_hash_for_update(
                token_hash
            )
        )

        if stored_token is None:
            raise UnauthorizedException(
                "Invalid refresh token."
            )

        now = datetime.now(
            timezone.utc
        )

        if stored_token.revoked_at is not None:
            raise UnauthorizedException(
                "Refresh token has been revoked."
            )

        if stored_token.expires_at <= now:
            raise UnauthorizedException(
                "Refresh token has expired."
            )

        request_device_id = (
            request.device_id.strip()
            if request.device_id
            else None
        )

        if (
            stored_token.device_id
            is not None
            and stored_token.device_id
            != request_device_id
        ):
            raise UnauthorizedException(
                "Invalid device."
            )

        user = (
            await self
            ._user_repository
            .get_by_id(
                stored_token.user_id
            )
        )

        if user is None:
            raise UnauthorizedException(
                "User not found."
            )

        if not user.is_active:
            raise UnauthorizedException(
                "User is not active."
            )

        roles = (
            await self
            ._role_repository
            .get_by_user_id(
                user.id
            )
        )

        if not roles:
            raise UnauthorizedException(
                "User has no assigned role."
            )

        role = roles[0]

        # Resolve tenant identity from the user's bound department,
        # NOT from settings.school_id (which is intentionally None
        # post-tenant-cleanup and would silently propagate a bogus
        # tenant to the new JWT).
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
            school_id=school_id_for_token,
            school_code=school_code_for_token,
            email=user.email,
            role=role.code,
            user_type=(
                AuditActorType.SCHOOL_USER
            ),
            token_version=(
                user.token_version
            ),
        )

        access_token = (
            self._jwt_token_service
            .generate_access_token(
                jwt_user
            )
        )

        new_raw_refresh_token = (
            self._refresh_token_service
            .generate_token()
        )

        new_refresh_token_hash = (
            self._refresh_token_service
            .hash_token(
                new_raw_refresh_token
            )
        )

        new_refresh_token = (
            RefreshToken(
                id=uuid4(),
                user_id=user.id,
                token_hash=(
                    new_refresh_token_hash
                ),
                device_id=(
                    request_device_id
                    if request_device_id
                    is not None
                    else stored_token
                    .device_id
                ),
                expires_at=(
                    now
                    + timedelta(
                        days=(
                            self
                            ._settings
                            .jwt_refresh_token_days
                        )
                    )
                ),
                revoked_at=None,
                replaced_by_token_id=None,
                created_at=now,
            )
        )

        await (
            self
            ._refresh_token_repository
            .add(
                new_refresh_token
            )
        )

        await (
            self._unit_of_work.flush()
        )

        stored_token.revoked_at = now

        stored_token.replaced_by_token_id = (
            new_refresh_token.id
        )

        await (
            self
            ._refresh_token_repository
            .update(
                stored_token
            )
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        access_token_expires_at = (
            now
            + timedelta(
                minutes=(
                    self
                    ._settings
                    .jwt_access_token_minutes
                )
            )
        )

        return RefreshResult(
            access_token=access_token,
            refresh_token=(
                new_raw_refresh_token
            ),
            expires_at=(
                access_token_expires_at
            ),
        )