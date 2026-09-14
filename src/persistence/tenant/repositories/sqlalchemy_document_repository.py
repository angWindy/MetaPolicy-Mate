from datetime import date
from uuid import UUID

from sqlalchemy import (
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.document import Document
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.persistence.tenant.models.document import (
    DocumentModel,
)
from src.persistence.tenant.models.document_department import (
    DocumentDepartmentModel,
)

class SqlAlchemyDocumentRepository(
    DocumentRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        document_id: UUID,
    ) -> Document | None:
        model = await self._session.get(
            DocumentModel,
            document_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_ids(
        self,
        document_ids: list[UUID],
    ) -> list[Document]:
        """Batch fetch documents by primary key.

        Used by ACL checks (e.g. ``citations_are_accessible``) to
        avoid the N+1 query that ``get_by_id`` in a loop would
        cause. Returns whatever exists; missing IDs are silently
        dropped so callers can detect them by diffing the input.
        An empty input returns an empty list without hitting the DB.
        """
        if not document_ids:
            return []

        unique_ids = list(
            set(document_ids)
        )

        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.id.in_(unique_ids)
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def get_by_number(
        self,
        document_number: str,
    ) -> Document | None:
        normalized_number = (
            document_number.strip()
        )

        result = await self._session.execute(
            select(DocumentModel)
            .where(
                func.lower(
                    DocumentModel.document_number
                )
                == normalized_number.lower()
            )
            .order_by(
                DocumentModel.created_at.desc()
            )
            .limit(1)
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def exists_by_number(
        self,
        document_number: str,
        exclude_document_id: UUID | None = None,
    ) -> bool:
        normalized_number = (
            document_number.strip()
        )

        statement = (
            select(DocumentModel.id)
            .where(
                func.lower(
                    DocumentModel.document_number
                )
                == normalized_number.lower()
            )
        )

        if exclude_document_id is not None:
            statement = statement.where(
                DocumentModel.id
                != exclude_document_id
        )
        statement = statement.limit(1)

        result = await self._session.execute(
            statement
        )

        return (
            result.scalar_one_or_none()
            is not None
        )

    async def search(
        self,
        document_number: str | None,
        legal_status: (
            DocumentLegalStatus | None
        ),
        issued_from: date | None,
        issued_to: date | None,
        department_id: UUID | None,
        skip: int,
        limit: int,
        is_admin: bool = False,
    ) -> list[Document]:
        statement = select(
            DocumentModel
        )

        statement = self._apply_filters(
            statement=statement,
            document_number=document_number,
            legal_status=legal_status,
            issued_from=issued_from,
            issued_to=issued_to,
        )

        statement = (
            self._apply_access_filter(
                statement,
                department_id,
                is_admin=is_admin,
            )
        )

        statement = (
            statement
            .order_by(
                DocumentModel
                .created_at
                .desc()
            )
            .offset(skip)
            .limit(limit)
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def count(
        self,
        document_number: str | None,
        legal_status: (
            DocumentLegalStatus | None
        ),
        issued_from: date | None,
        issued_to: date | None,
        department_id: UUID | None,
        is_admin: bool = False,
    ) -> int:
        statement = select(
            func.count(
                DocumentModel.id
            )
        )

        statement = self._apply_filters(
            statement=statement,
            document_number=document_number,
            legal_status=legal_status,
            issued_from=issued_from,
            issued_to=issued_to,
        )

        statement = (
            self._apply_access_filter(
                statement,
                department_id,
                is_admin=is_admin,
            )
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        return int(
            result.scalar_one()
        )

    async def add(
        self,
        document: Document,
    ) -> None:
        self._session.add(
            DocumentModel(
                id=document.id,
                document_number=(
                    document.document_number
                ),
                title=document.title,
                issued_by=document.issued_by,
                issued_date=(
                    document.issued_date
                ),
                effective_date=(
                    document.effective_date
                ),
                legal_status=(
                    document.legal_status.value
                ),
                created_at=(
                    document.created_at
                ),
                updated_at=(
                    document.updated_at
                ),
                access_scope=(
                    document.access_scope.value
                ),
            )
        )

    async def update(
        self,
        document: Document,
    ) -> None:
        model = await self._session.get(
            DocumentModel,
            document.id,
        )

        if model is None:
            return

        model.document_number = (
            document.document_number
        )

        model.title = document.title
        model.issued_by = document.issued_by

        model.issued_date = (
            document.issued_date
        )

        model.effective_date = (
            document.effective_date
        )

        model.legal_status = (
            document.legal_status.value
        )

        model.updated_at = (
            document.updated_at
        )

        model.access_scope = (
            document.access_scope.value
        )

    async def delete(
        self,
        document_id: UUID,
    ) -> None:
        model = await self._session.get(
            DocumentModel,
            document_id,
        )

        if model is None:
            return

        await self._session.delete(model)
        await self._session.flush()

    async def get_documents_due_for_effectiveness(
        self,
        as_of: date,
    ) -> list[Document]:
        result = await self._session.execute(
            select(
                DocumentModel
            )
            .where(
                DocumentModel.effective_date
                <= as_of
            )
            .where(
                DocumentModel.legal_status
                == DocumentLegalStatus
                .CHO_XU_LY_NOI_DUNG
                .value
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def update_object_key(
        self,
        version_id: UUID,
        new_key: str,
    ) -> None:
        """Update the R2 object_key for a specific document version.

        Called by the access-scope update handler after the R2 object
        has been copied to the new key. Keeps the DB in sync with the
        bucket so subsequent requests (download, replace-source) resolve
        the correct key.
        """
        from sqlalchemy import update
        from src.persistence.tenant.models.document_version import (
            DocumentVersionModel,
        )

        await self._session.execute(
            update(DocumentVersionModel)
            .where(
                DocumentVersionModel.id
                == version_id
            )
            .values(object_key=new_key)
        )

    @staticmethod
    def _apply_filters(
        statement,
        document_number: str | None,
        legal_status: DocumentLegalStatus | None,
        issued_from: date | None,
        issued_to: date | None,
    ):
        if (
            document_number is not None
            and document_number.strip()
        ):
            pattern = (
                f"%{document_number.strip()}%"
            )

            statement = statement.where(
                or_(
                    DocumentModel
                    .document_number
                    .ilike(pattern),
                    DocumentModel
                    .title
                    .ilike(pattern),
                )
            )

        if legal_status is not None:
            statement = statement.where(
                DocumentModel.legal_status
                == legal_status.value
            )

        if issued_from is not None:
            statement = statement.where(
                DocumentModel.issued_date
                >= issued_from
            )

        if issued_to is not None:
            statement = statement.where(
                DocumentModel.issued_date
                <= issued_to
            )

        return statement

    @staticmethod
    def _apply_access_filter(
        statement,
        department_id: UUID | None,
        *,
        is_admin: bool = False,
    ):
        """Apply the per-tenant document access filter.

        ``is_admin=True`` bypasses the per-school filter and returns
        every row that matches the other search criteria. Used by
        the demo ``admin@p234.demo`` user so they can manage
        documents across HUST and HUCE without being a member of
        every department.
        """
        if is_admin:
            # Admins see everything — no scope / ACL join. We still
            # let ``_apply_filters`` run first so document_number,
            # legal_status, and date filters are honoured.
            return statement

        public_condition = (
            DocumentModel.access_scope
            == (
                DocumentAccessScope
                .PUBLIC
                .value
            )
        )

        if department_id is None:
            return statement.where(
                public_condition
            )

        department_condition = exists(
            select(1)
            .select_from(
                DocumentDepartmentModel
            )
            .where(
                DocumentDepartmentModel
                .document_id
                == DocumentModel.id,
                DocumentDepartmentModel
                .department_id
                == department_id,
            )
        )

        return statement.where(
            or_(
                public_condition,
                department_condition,
            )
        )

    @staticmethod
    def _to_domain(
        model: DocumentModel,
    ) -> Document:
        return Document(
            id=model.id,
            document_number=(
                model.document_number
            ),
            title=model.title,
            issued_by=model.issued_by,
            issued_date=model.issued_date,
            effective_date=(
                model.effective_date
            ),
            legal_status=(
                DocumentLegalStatus(
                    model.legal_status
                )
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
            access_scope=(
                DocumentAccessScope(
                    model.access_scope
                )
            ),
        )

