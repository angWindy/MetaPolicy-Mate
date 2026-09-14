from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_section_metadata_draft import (
    DocumentSectionMetadataDraft,
)
from src.domain.enums.document_metadata_draft_status import (
    DocumentMetadataDraftStatus,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.persistence.tenant.models.document_chunk import (
    DocumentChunkModel,
)
from src.persistence.tenant.models.document_section_metadata_draft import (
    DocumentSectionMetadataDraftModel,
)


class SqlAlchemyDocumentSectionMetadataDraftRepository(
    DocumentSectionMetadataDraftRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        draft_id: UUID,
    ) -> (
        DocumentSectionMetadataDraft
        | None
    ):
        model = await self._session.get(
            DocumentSectionMetadataDraftModel,
            draft_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_chunk_id(
        self,
        chunk_id: UUID,
    ) -> (
        DocumentSectionMetadataDraft
        | None
    ):
        result = await (
            self._session.execute(
                select(
                    DocumentSectionMetadataDraftModel
                )
                .where(
                    DocumentSectionMetadataDraftModel
                    .chunk_id
                    == chunk_id
                )
                .limit(1)
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_pending_by_version(
        self,
        version_id: UUID,
    ) -> list[
        DocumentSectionMetadataDraft
    ]:
        result = await (
            self._session.execute(
                select(
                    DocumentSectionMetadataDraftModel
                )
                .where(
                    DocumentSectionMetadataDraftModel
                    .version_id
                    == version_id,
                    DocumentSectionMetadataDraftModel
                    .status
                    == (
                        DocumentMetadataDraftStatus
                        .PENDING_REVIEW
                        .value
                    ),
                )
                .order_by(
                    DocumentSectionMetadataDraftModel
                    .created_at
                )
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def is_section_fully_approved(
        self,
        section_id: UUID,
    ) -> bool:
        total_chunks_result = await (
            self._session.execute(
                select(
                    func.count(
                        DocumentChunkModel.id
                    )
                )
                .where(
                    DocumentChunkModel
                    .section_id
                    == section_id
                )
            )
        )

        total_chunks = int(
            total_chunks_result.scalar_one()
            or 0
        )

        if total_chunks == 0:
            return False

        approved_result = await (
            self._session.execute(
                select(
                    func.count(
                        DocumentSectionMetadataDraftModel
                        .id
                    )
                )
                .where(
                    DocumentSectionMetadataDraftModel
                    .section_id
                    == section_id,
                    DocumentSectionMetadataDraftModel
                    .status
                    == (
                        DocumentMetadataDraftStatus
                        .APPROVED
                        .value
                    ),
                )
            )
        )

        approved_count = int(
            approved_result.scalar_one()
            or 0
        )

        return (
            approved_count
            == total_chunks
        )

    async def save(
        self,
        draft: (
            DocumentSectionMetadataDraft
        ),
    ) -> None:
        model = await self._session.get(
            DocumentSectionMetadataDraftModel,
            draft.id,
        )

        if model is None:
            model = (
                DocumentSectionMetadataDraftModel(
                    id=draft.id,
                    document_id=(
                        draft.document_id
                    ),
                    version_id=(
                        draft.version_id
                    ),
                    section_id=(
                        draft.section_id
                    ),
                    chunk_id=(
                        draft.chunk_id
                    ),
                    metadata_json=(
                        draft.metadata
                    ),
                    cross_references_json=(
                        draft.cross_references
                    ),
                    needs_human_review=(
                        draft
                        .needs_human_review
                    ),
                    rationale=(
                        draft.rationale
                    ),
                    status=(
                        draft.status.value
                    ),
                    reviewed_by=(
                        draft.reviewed_by
                    ),
                    reviewed_at=(
                        draft.reviewed_at
                    ),
                    created_at=(
                        draft.created_at
                    ),
                    updated_at=(
                        draft.updated_at
                    ),
                )
            )

            self._session.add(model)
            return

        model.document_id = (
            draft.document_id
        )

        model.version_id = (
            draft.version_id
        )

        model.section_id = (
            draft.section_id
        )

        model.chunk_id = (
            draft.chunk_id
        )

        model.metadata_json = (
            draft.metadata
        )

        model.cross_references_json = (
            draft.cross_references
        )

        model.needs_human_review = (
            draft.needs_human_review
        )

        model.rationale = (
            draft.rationale
        )

        model.status = (
            draft.status.value
        )

        model.reviewed_by = (
            draft.reviewed_by
        )

        model.reviewed_at = (
            draft.reviewed_at
        )

        model.updated_at = (
            draft.updated_at
        )

    @staticmethod
    def _to_domain(
        model: (
            DocumentSectionMetadataDraftModel
        ),
    ) -> (
        DocumentSectionMetadataDraft
    ):
        return DocumentSectionMetadataDraft(
            id=model.id,
            document_id=model.document_id,
            version_id=model.version_id,
            section_id=model.section_id,
            chunk_id=model.chunk_id,
            metadata=dict(
                model.metadata_json
                or {}
            ),
            cross_references=[
                dict(item)
                for item in (
                    model
                    .cross_references_json
                    or []
                )
            ],
            needs_human_review=(
                model.needs_human_review
            ),
            rationale=model.rationale,
            status=(
                DocumentMetadataDraftStatus(
                    model.status
                )
            ),
            reviewed_by=(
                model.reviewed_by
            ),
            reviewed_at=(
                model.reviewed_at
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )