from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.token_version_cache import (
    TokenVersionCache,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.users.common.user_item import (
    UserItem,
)
from src.application.features.users.update.update_user_command import (
    UpdateUserCommand,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class UpdateUserHandler(
    RequestHandler[
        UpdateUserCommand,
        UserItem,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        department_repository: DepartmentRepository,
        token_version_cache: (
            TokenVersionCache
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._department_repository = (
            department_repository
        )

        self._token_version_cache = (
            token_version_cache
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: UpdateUserCommand,
    ) -> UserItem:
        user = await (
            self._user_repository
            .get_by_id(
                request.user_id
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        email = (
            request.email
            .strip()
            .lower()
        )

        full_name = (
            request.full_name
            .strip()
        )

        if not email:
            raise ConflictException(
                "Email is required."
            )

        if not full_name:
            raise ConflictException(
                "Full name is required."
            )

        existing = await (
            self._user_repository
            .get_by_email(email)
        )

        if (
            existing is not None
            and existing.id != user.id
        ):
            raise ConflictException(
                "Email already exists."
            )

        department_changed = False

        if (
            request.department_id
            is not None
        ):
            department = await (
                self
                ._department_repository
                .get_by_id(
                    request.department_id
                )
            )

            if department is None:
                raise NotFoundException(
                    "Department not found."
                )

            if not department.is_active:
                raise ConflictException(
                    "Department is inactive."
                )

            if (
                user.department_id
                != request.department_id
            ):
                department_changed = True

        user.email = email
        user.full_name = full_name

        user.department_id = (
            request.department_id
        )

        user.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        # When the user switches department, the JWT carries the
        # ``school_id`` and ``tenant_id`` derived from
        # ``user.department_id``. Invalidate all live tokens so the
        # next request gets a fresh JWT scoped to the new department.
        # Email/name-only changes do NOT affect JWT claims, so we
        # leave ``token_version`` alone in that case.
        if department_changed:
            user.token_version += 1

        await self._user_repository.update(
            user
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        if department_changed:
            await (
                self
                ._token_version_cache
                .set(
                    user.id,
                    user.token_version,
                )
            )

        return UserItem.from_entity(
            user
        )