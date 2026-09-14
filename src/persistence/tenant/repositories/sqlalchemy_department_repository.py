from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.department import (
    Department,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.persistence.tenant.models.department import (
    DepartmentModel,
)


class SqlAlchemyDepartmentRepository(
    DepartmentRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        department_id: UUID,
    ) -> Department | None:
        model = await self._session.get(
            DepartmentModel,
            department_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_code(
        self,
        code: str,
    ) -> Department | None:
        result = await self._session.execute(
            select(
                DepartmentModel
            ).where(
                DepartmentModel.code
                == code.strip().upper()
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_all(
        self,
    ) -> list[Department]:
        result = await self._session.execute(
            select(
                DepartmentModel
            ).order_by(
                DepartmentModel.name
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def add(
        self,
        department: Department,
    ) -> None:
        self._session.add(
            DepartmentModel(
                id=department.id,
                code=department.code,
                name=department.name,
                is_active=(
                    department.is_active
                ),
                created_at=(
                    department.created_at
                ),
                updated_at=(
                    department.updated_at
                ),
            )
        )

    async def update(
        self,
        department: Department,
    ) -> None:
        model = await self._session.get(
            DepartmentModel,
            department.id,
        )

        if model is None:
            return

        model.code = department.code
        model.name = department.name
        model.is_active = (
            department.is_active
        )
        model.updated_at = (
            department.updated_at
        )

    @staticmethod
    def _to_domain(
        model: DepartmentModel,
    ) -> Department:
        return Department(
            id=model.id,
            code=model.code,
            name=model.name,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )