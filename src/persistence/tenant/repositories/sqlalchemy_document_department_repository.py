from uuid import UUID

from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.persistence.tenant.models.document_department import (
    DocumentDepartmentModel,
)


class SqlAlchemyDocumentDepartmentRepository(
    DocumentDepartmentRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_department_ids(
        self,
        document_id: UUID,
    ) -> list[UUID]:
        result = await self._session.execute(
            select(
                DocumentDepartmentModel
                .department_id
            ).where(
                DocumentDepartmentModel
                .document_id
                == document_id
            )
        )

        return list(
            result.scalars().all()
        )

    async def replace_departments(
        self,
        document_id: UUID,
        department_ids: list[UUID],
    ) -> None:
        await self._session.execute(
            delete(
                DocumentDepartmentModel
            ).where(
                DocumentDepartmentModel
                .document_id
                == document_id
            )
        )

        for department_id in set(
            department_ids
        ):
            self._session.add(
                DocumentDepartmentModel(
                    document_id=(
                        document_id
                    ),
                    department_id=(
                        department_id
                    ),
                )
            )

    async def can_access(
        self,
        document_id: UUID,
        department_id: UUID,
    ) -> bool:
        result = await self._session.execute(
            select(
                DocumentDepartmentModel
                .document_id
            )
            .where(
                DocumentDepartmentModel
                .document_id
                == document_id
            )
            .where(
                DocumentDepartmentModel
                .department_id
                == department_id
            )
            .limit(1)
        )

        return (
            result.scalar_one_or_none()
            is not None
        )

    async def can_access_any(
        self,
        document_ids: list[UUID],
        department_id: UUID,
    ) -> set[UUID]:
        """Batch variant of :meth:`can_access`.

        Returns the subset of ``document_ids`` that the given
        ``department_id`` is allowed to access. A single SQL
        ``IN`` query replaces the N+1 loop the ACL check used
        to incur. Empty input returns an empty set without
        hitting the DB.
        """
        if not document_ids:
            return set()

        result = await self._session.execute(
            select(
                DocumentDepartmentModel
                .document_id
            )
            .where(
                DocumentDepartmentModel
                .document_id
                .in_(document_ids)
            )
            .where(
                DocumentDepartmentModel
                .department_id
                == department_id
            )
        )

        return set(result.scalars().all())