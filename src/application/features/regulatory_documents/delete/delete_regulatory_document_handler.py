import logging
from uuid import UUID

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.delete.delete_regulatory_document_command import (
    DeleteRegulatoryDocumentCommand,
)
from src.application.features.regulatory_documents.delete.delete_regulatory_document_result import (
    DeleteRegulatoryDocumentResult,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


class DeleteRegulatoryDocumentHandler(
    RequestHandler[
        DeleteRegulatoryDocumentCommand,
        DeleteRegulatoryDocumentResult,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_version_repository: (
            DocumentVersionRepository
        ),
        file_storage: FileStorage,
        vector_store: VectorStore,
        request_context: RequestContext,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )
        self._document_version_repository = (
            document_version_repository
        )
        self._file_storage = file_storage
        self._vector_store = vector_store
        self._request_context = (
            request_context
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: DeleteRegulatoryDocumentCommand,
    ) -> DeleteRegulatoryDocumentResult:
        document_id: UUID = request.document_id

        document = (
            await self._document_repository
            .get_by_id(
                document_id,
            )
        )
        if document is None:
            raise NotFoundException(
                f"Document {document_id} not found."
            )

        versions = (
            await self
            ._document_version_repository
            .list_by_document_id(document_id)
        )

        errors: list[str] = []
        qdrant_points_removed = 0
        storage_objects_deleted = 0

        # ------------------------------------------------------------------
        # Qdrant cascade: drop per-version points, then the catch-all
        # document-wide sweep.
        # ------------------------------------------------------------------
        for version in versions:
            try:
                removed = (
                    await self
                    ._vector_store
                    .delete_version_points(
                        str(version.id),
                    )
                )
                if removed is None:
                    pass
                else:
                    qdrant_points_removed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "qdrant_delete_failed version_id=%s",
                    version.id,
                )
                errors.append(
                    f"qdrant version delete "
                    f"failed: {version.id} "
                    f"({exc.__class__.__name__})"
                )

        try:
            qdrant_points_removed += (
                await self
                ._vector_store
                .delete_document_points(
                    str(document_id),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "qdrant_document_delete_failed "
                "document_id=%s",
                document_id,
            )
            errors.append(
                f"qdrant document delete failed: "
                f"{document_id} ({exc.__class__.__name__})"
            )

        # ------------------------------------------------------------------
        # R2 cascade: bulk-delete every version's source PDF in one
        # batched call (boto3 caps batches at 1000 keys).
        # ------------------------------------------------------------------
        object_keys = [
            v.object_key for v in versions if v.object_key
        ]
        if object_keys:
            try:
                failed_keys = (
                    await self._file_storage
                    .delete_objects(object_keys)
                )
                storage_objects_deleted = (
                    len(object_keys)
                    - len(failed_keys)
                )
                if failed_keys:
                    errors.append(
                        "r2 bulk delete failed for "
                        f"{len(failed_keys)} key(s): "
                        f"{failed_keys[:5]}"
                        + (
                            "..."
                            if len(failed_keys) > 5
                            else ""
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "r2_bulk_delete_failed document_id=%s",
                    document_id,
                )
                errors.append(
                    f"r2 bulk delete failed: "
                    f"{exc.__class__.__name__}"
                )
                # Fall back to per-key deletes so a single
                # transport error doesn't leave N PDFs behind.
                for key in object_keys:
                    try:
                        await self._file_storage.delete(key)
                        storage_objects_deleted += 1
                    except (
                        Exception  # noqa: BLE001
                    ) as inner_exc:
                        errors.append(
                            f"r2 fallback delete "
                            f"failed: {key} "
                            f"({inner_exc.__class__.__name__})"
                        )

        # ------------------------------------------------------------------
        # DB cleanup — always runs, even on partial R2/Qdrant failure.
        # ------------------------------------------------------------------
        versions_deleted = (
            await self
            ._document_version_repository
            .delete_by_document_id(document_id)
        )

        await self._document_repository.delete(
            document_id
        )

        await self._unit_of_work.save_changes()

        return DeleteRegulatoryDocumentResult(
            deleted=True,
            qdrant_points_removed=(
                qdrant_points_removed
            ),
            versions_deleted=versions_deleted,
            storage_objects_deleted=(
                storage_objects_deleted
            ),
            errors=errors,
        )