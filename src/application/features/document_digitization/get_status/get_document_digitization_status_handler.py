from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_digitization.common.document_digitization_item import (
    DocumentDigitizationItem,
)
from src.application.features.document_digitization.get_status.get_document_digitization_status_query import (
    GetDocumentDigitizationStatusQuery,
)
from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class GetDocumentDigitizationStatusHandler(
    RequestHandler[
        GetDocumentDigitizationStatusQuery,
        DocumentDigitizationItem,
    ]
):
    def __init__(
        self,
        document_version_repository: (
            DocumentVersionRepository
        ),
        digitization_repository: (
            DocumentDigitizationRepository
        ),
    ) -> None:
        self._document_version_repository = (
            document_version_repository
        )

        self._digitization_repository = (
            digitization_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentDigitizationStatusQuery
        ),
    ) -> DocumentDigitizationItem:
        version = await (
            self
            ._document_version_repository
            .get_by_id(
                request.version_id
            )
        )

        if (
            version is None
            or version.document_id
            != request.document_id
        ):
            raise NotFoundException(
                "Document version not found."
            )

        job = await (
            self._digitization_repository
            .get_latest_job(
                version.id
            )
        )

        if job is None:
            raise NotFoundException(
                "Digitization job not found."
            )

        return DocumentDigitizationItem(
            version_id=version.id,
            status=job.status,
            section_count=(
                job.section_count
            ),
            chunk_count=(
                job.chunk_count
            ),
            warnings=job.warnings,
            error_message=(
                job.error_message
            ),
            started_at=job.started_at,
            completed_at=(
                job.completed_at
            ),
        )