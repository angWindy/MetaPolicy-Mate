from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.departments.common.department_item import (
    DepartmentItem,
)
from src.application.features.departments.get_list.get_departments_query import (
    GetDepartmentsQuery,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)


class GetDepartmentsHandler(
    RequestHandler[
        GetDepartmentsQuery,
        list[DepartmentItem],
    ]
):
    def __init__(
        self,
        department_repository: DepartmentRepository,
    ) -> None:
        self._department_repository = (
            department_repository
        )

    async def handle(
        self,
        request: GetDepartmentsQuery,
    ) -> list[DepartmentItem]:
        departments = await (
            self._department_repository
            .get_all()
        )

        return [
            DepartmentItem.from_entity(
                department
            )
            for department
            in departments
        ]