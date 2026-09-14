from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.departments.common.department_item import (
    DepartmentItem,
)
from src.application.features.departments.create.create_department_command import (
    CreateDepartmentCommand,
)
from src.domain.entities.department import (
    Department,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)


class CreateDepartmentHandler(
    RequestHandler[
        CreateDepartmentCommand,
        DepartmentItem,
    ]
):
    def __init__(
        self,
        department_repository: DepartmentRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._department_repository = (
            department_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: CreateDepartmentCommand,
    ) -> DepartmentItem:
        code = (
            request.code
            .strip()
            .upper()
        )

        name = request.name.strip()

        if not code:
            raise ConflictException(
                "Department code is required."
            )

        if not name:
            raise ConflictException(
                "Department name is required."
            )

        existing = await (
            self._department_repository
            .get_by_code(code)
        )

        if existing is not None:
            raise ConflictException(
                "Department code already exists."
            )

        department = Department(
            id=uuid4(),
            code=code,
            name=name,
            is_active=True,
            created_at=datetime.now(
                timezone.utc
            ),
            updated_at=None,
        )

        await (
            self._department_repository
            .add(department)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DepartmentItem
            .from_entity(department)
        )