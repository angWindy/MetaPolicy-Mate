from datetime import (
    datetime,
    timezone,
)
from uuid import UUID

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
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
from src.application.features.departments.update.update_department_command import (
    UpdateDepartmentCommand,
)
from src.domain.entities.department import (
    Department,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)


class UpdateDepartmentHandler(
    RequestHandler[
        UpdateDepartmentCommand,
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
        request: UpdateDepartmentCommand,
    ) -> DepartmentItem:
        department_id = UUID(request.department_id)

        department = await (
            self._department_repository
            .get_by_id(department_id)
        )

        if department is None:
            raise NotFoundException(
                f"Department with id {department_id} not found."
            )

        if request.name is not None:
            department.name = request.name.strip()

        if request.is_active is not None:
            department.is_active = request.is_active

        department.updated_at = datetime.now(
            timezone.utc
        )

        await (
            self._department_repository
            .update(department)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DepartmentItem
            .from_entity(department)
        )
