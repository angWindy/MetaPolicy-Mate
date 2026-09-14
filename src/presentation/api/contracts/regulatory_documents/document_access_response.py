from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)


class DocumentAccessResponse(
    BaseModel
):
    document_id: UUID

    access_scope: DocumentAccessScope

    department_ids: list[UUID]

    department_codes: list[str] = []