from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)
from src.application.features.regulatory_documents.update.update_regulatory_document_command import (
    UpdateRegulatoryDocumentCommand,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


_ALLOWED_STATUS_TRANSITIONS = {
    DocumentLegalStatus
    .CHO_XU_LY_NOI_DUNG: {
        DocumentLegalStatus
        .DANG_HIEU_LUC,
    },

    DocumentLegalStatus
    .DANG_HIEU_LUC: {
        DocumentLegalStatus
        .HET_HIEU_LUC,

        DocumentLegalStatus
        .BI_THAY_THE,
    },

    DocumentLegalStatus
    .HET_HIEU_LUC: set(),

    DocumentLegalStatus
    .BI_THAY_THE: set(),
}


class UpdateRegulatoryDocumentHandler(
    RequestHandler[
        UpdateRegulatoryDocumentCommand,
        RegulatoryDocumentItem,
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )
        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            UpdateRegulatoryDocumentCommand
        ),
    ) -> RegulatoryDocumentItem:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document "
                "not found."
            )

        requested_status = (
            request.legal_status
            if request.legal_status
            is not None
            else document.legal_status
        )

        if (
            requested_status
            != document.legal_status
        ):
            allowed_statuses = (
                _ALLOWED_STATUS_TRANSITIONS
                .get(
                    document.legal_status,
                    set(),
                )
            )

            if (
                requested_status
                not in allowed_statuses
            ):
                raise ConflictException(
                    "Invalid document legal "
                    "status transition: "
                    f"{document.legal_status.value} "
                    "-> "
                    f"{requested_status.value}."
                )

        document_number = (
            request.document_number.strip()
        )
        title = request.title.strip()
        issued_by = request.issued_by.strip()

        if not document_number:
            raise ConflictException(
                "Document number is required."
            )

        if not title:
            raise ConflictException(
                "Document title is required."
            )

        if not issued_by:
            raise ConflictException(
                "Issued by is required."
            )

        duplicate = await (
            self._document_repository
            .exists_by_number(
                document_number=(
                    document_number
                ),
                exclude_document_id=(
                    document.id
                ),
            )
        )

        if duplicate:
            raise ConflictException(
                "Another document already "
                "uses this document number."
            )

        request.set_audit_before(
            {
                "document_id":
                    document.id,

                "document_number":
                    document.document_number,

                "title":
                    document.title,

                "issued_by":
                    document.issued_by,

                "issued_date":
                    document.issued_date,

                "effective_date":
                    document.effective_date,

                "legal_status":
                    document
                    .legal_status
                    .value,
            }
        )

        document.document_number = (
            document_number
        )
        document.title = title
        document.issued_by = issued_by
        document.issued_date = (
            request.issued_date
        )
        document.effective_date = (
            request.effective_date
        )
        document.legal_status = (
            requested_status
        )

        document.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        # Để AuditHandlerDecorator lấy
        # đúng trạng thái after thực tế.
        request.legal_status = (
            requested_status
        )

        await (
            self._document_repository
            .update(document)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            RegulatoryDocumentItem
            .from_document(document)
        )