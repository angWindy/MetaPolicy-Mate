from uuid import UUID

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


async def can_access_document(
    *,
    document_id: UUID,
    department_id: UUID | None,
    document_repository: DocumentRepository,
    document_department_repository: (
        DocumentDepartmentRepository
    ),
    is_admin: bool = False,
) -> bool:
    document = await (
        document_repository.get_by_id(
            document_id
        )
    )

    if document is None:
        return False

    if is_admin or (
        document.access_scope
        == DocumentAccessScope.PUBLIC
    ):
        return True

    if department_id is None:
        return False

    return await (
        document_department_repository
        .can_access(
            document_id=document.id,
            department_id=department_id,
        )
    )


async def citations_are_accessible(
    *,
    citations: list[dict],
    department_id: UUID | None,
    document_repository: DocumentRepository,
    document_department_repository: (
        DocumentDepartmentRepository
    ),
    is_admin: bool = False,
) -> bool:
    if not citations:
        # Không có citation thì không thể
        # chứng minh answer/history thuộc
        # document mà user đang được phép đọc.
        # Với dữ liệu có thể chứa nội dung nội bộ,
        # policy phải fail closed.
        return False

    document_ids: set[UUID] = set()

    for citation in citations:
        if not isinstance(
            citation,
            dict,
        ):
            return False

        raw_document_id = (
            citation.get(
                "document_id"
            )
        )

        if raw_document_id is None:
            return False

        try:
            document_id = UUID(
                str(
                    raw_document_id
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        document_ids.add(
            document_id
        )

    if not document_ids:
        return False

    # B-P1-01: collapse the per-document loop into two
    # batched queries (one for documents, one for the
    # department↔document ACL join) instead of N+1.
    documents = await (
        document_repository.get_by_ids(
            list(document_ids)
        )
    )

    by_id = {doc.id: doc for doc in documents}

    # Documents that exist but whose scope is PUBLIC are
    # accessible regardless of department.
    department_scoped_ids: set[UUID] = set()
    for document_id, document in (
        by_id.items()
    ):
        if (
            document.access_scope
            == DocumentAccessScope.PUBLIC
        ):
            continue
        department_scoped_ids.add(
            document_id
        )

    # Every requested document must exist (otherwise fail
    # closed - we can't prove access to a missing doc).
    if len(by_id) != len(document_ids):
        return False

    if is_admin or not department_scoped_ids:
        return True

    # Cross-school users (department_id is None) cannot
    # reach DEPARTMENT-scoped documents.
    if department_id is None:
        return False

    accessible_ids = await (
        document_department_repository
        .can_access_any(
            list(department_scoped_ids),
            department_id,
        )
    )

    return (
        accessible_ids
        == department_scoped_ids
    )