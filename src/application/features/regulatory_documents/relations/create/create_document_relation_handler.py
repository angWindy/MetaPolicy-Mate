from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

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
from src.application.features.regulatory_documents.relations.create.create_document_relation_command import (
    CreateDocumentRelationCommand,
)
from src.domain.entities.document_relation import (
    DocumentRelation,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)
from src.domain.repositories.document_relation_repository import (
    DocumentRelationRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)

class CreateDocumentRelationHandler(
    RequestHandler[
        CreateDocumentRelationCommand,
        DocumentRelation,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_relation_repository: (
            DocumentRelationRepository
        ),
        document_version_repository: (
            DocumentVersionRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )
        self._document_relation_repository = (
            document_relation_repository
        )
        self._document_version_repository = (
            document_version_repository
        )
        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: CreateDocumentRelationCommand,
    ) -> DocumentRelation:
        if (
            request.source_document_id
            == request.target_document_id
        ):
            raise ConflictException(
                "A document cannot relate to itself."
            )

        source = (
            await self._document_repository
            .get_by_id(
                request.source_document_id
            )
        )

        if source is None:
            raise NotFoundException(
                "Source document not found."
            )

        source_version = await (
            self._document_version_repository
            .get_latest_by_document_id(
                source.id
            )
        )

        if source_version is None:
            raise ConflictException(
                "Source document has no uploaded source version."
            )
        
        target = (
            await self._document_repository
            .get_by_id(
                request.target_document_id
            )
        )

        if target is None:
            raise NotFoundException(
                "Target document not found."
            )

        existing_superseding_relation = None

        if (
            request.relation_type
            == DocumentRelationType
            .SUPERSEDES
        ):
            existing_superseding_relation = (
                await self
                ._document_relation_repository
                .get_effective_superseding_relation(
                    target.id
                )
            )

            if (
                existing_superseding_relation
                is not None
                and not request.confirm_conflict
            ):
                raise ConflictException(
                    "Target document is already "
                    "superseded by another "
                    "effective document. "
                    "Confirmation is required."
                )

        relation = DocumentRelation(
            id=uuid4(),
            source_document_id=(
                source.id
            ),
            target_document_id=(
                target.id
            ),
            relation_type=(
                request.relation_type
            ),
            note=(
                request.note.strip()
                if request.note
                else None
            ),
            created_at=datetime.now(
                timezone.utc
            ),
        )

        # Conflict đã được chuyên gia xác nhận:
        # quan hệ SUPERSEDES hiện tại được ghi đè.
        if (
            existing_superseding_relation
            is not None
            and request.confirm_conflict
        ):
            await (
                self
                ._document_relation_repository
                .delete(
                    existing_superseding_relation
                )
            )

        await (
            self
            ._document_relation_repository
            .add(
                relation
            )
        )

        if (
            request.relation_type
            == DocumentRelationType
            .SUPERSEDES
        ):
            target.legal_status = (
                DocumentLegalStatus
                .BI_THAY_THE
            )

            target.updated_at = (
                datetime.now(
                    timezone.utc
                )
            )

            await (
                self._document_repository
                .update(
                    target
                )
            )

        await (
            self._unit_of_work
            .save_changes()
        )

        return relation