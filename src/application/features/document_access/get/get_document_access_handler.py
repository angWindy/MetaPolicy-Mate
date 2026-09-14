from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_access.common.document_access_item import (
    DocumentAccessItem,
)
from src.application.features.document_access.get.get_document_access_query import (
    GetDocumentAccessQuery,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetDocumentAccessHandler(
    RequestHandler[
        GetDocumentAccessQuery,
        DocumentAccessItem,
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
        department_repository: DepartmentRepository,
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

        self._department_repository = (
            department_repository
        )

    async def handle(
        self,
        request: GetDocumentAccessQuery,
    ) -> DocumentAccessItem:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Document not found."
            )

        department_ids = await (
            self
            ._document_department_repository
            .get_department_ids(
                document.id
            )
        )

        # Resolve department codes (HUST, HUCE, etc.) so the FE
        # can display them without making a second call.
        department_codes: list[str] = []
        for department_id in department_ids:
            department = await (
                self
                ._department_repository
                .get_by_id(department_id)
            )
            if department is not None:
                department_codes.append(
                    department.code
                )

        return DocumentAccessItem(
            document_id=document.id,
            access_scope=(
                document.access_scope
            ),
            department_ids=(
                department_ids
            ),
            department_codes=(
                department_codes
            ),
        )