from typing import Protocol
from uuid import UUID


class DocumentDepartmentRepository(
    Protocol
):
    async def get_department_ids(
        self,
        document_id: UUID,
    ) -> list[UUID]:
        ...

    async def replace_departments(
        self,
        document_id: UUID,
        department_ids: list[UUID],
    ) -> None:
        ...

    async def can_access(
        self,
        document_id: UUID,
        department_id: UUID,
    ) -> bool:
        ...

    async def can_access_any(
        self,
        document_ids: list[UUID],
        department_id: UUID,
    ) -> set[UUID]:
        """Batch variant of :meth:`can_access`.

        Returns the subset of ``document_ids`` that the given
        ``department_id`` is allowed to access. Used by ACL
        checks (e.g. ``citations_are_accessible``) to avoid the
        N+1 query that calling ``can_access`` in a loop would
        cause. An empty input returns an empty set without
        hitting the DB.
        """
        ...