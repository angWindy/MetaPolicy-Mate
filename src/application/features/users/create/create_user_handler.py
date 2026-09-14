from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.password_hasher import (
    PasswordHasher,
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
from src.application.features.users.create.create_user_command import (
    CreateUserCommand,
)
from src.domain.entities.user import User
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class CreateUserHandler(
    RequestHandler[
        CreateUserCommand,
        UserItem,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        department_repository: DepartmentRepository,
        password_hasher: PasswordHasher,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._department_repository = (
            department_repository
        )

        self._password_hasher = (
            password_hasher
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: CreateUserCommand,
    ) -> UserItem:
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

        if not request.password:
            raise ConflictException(
                "Password is required."
            )

        existing = await (
            self._user_repository
            .get_by_email(email)
        )

        if existing is not None:
            raise ConflictException(
                "Email already exists."
            )

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

        now = datetime.now(
            timezone.utc
        )

        user = User(
            id=uuid4(),
            email=email,

            password_hash=(
                self._password_hasher
                .hash_password(
                    request.password
                )
            ),

            full_name=full_name,

            department_id=(
                request.department_id
            ),

            token_version=0,
            is_active=True,

            created_at=now,
            updated_at=None,
        )

        await self._user_repository.add(
            user
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return UserItem.from_entity(
            user
        )