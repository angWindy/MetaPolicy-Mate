import hashlib
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
from src.application.features.regulatory_documents.replace_source.replace_document_source_command import (
    ReplaceDocumentSourceCommand,
)
from src.domain.entities.document_version import (
    DocumentVersion,
)
from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.infrastructure.storage.object_key import (
    ObjectKeyBuilder,
)


class ReplaceDocumentSourceHandler(
    RequestHandler[
        ReplaceDocumentSourceCommand,
        DocumentVersion,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_version_repository: (
            DocumentVersionRepository
        ),
        file_storage: FileStorage,
        object_key_builder: ObjectKeyBuilder,
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
        self._object_key_builder = (
            object_key_builder
        )
        self._request_context = (
            request_context
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: ReplaceDocumentSourceCommand,
    ) -> DocumentVersion:
        document = (
            await self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document not found."
            )

        school_id = (
            self._request_context.school_id
        )

        if school_id is None:
            raise ConflictException(
                "SchoolId is required."
            )

        tenant_code = (
            self._request_context.school_code
        )

        latest_version = (
            await self
            ._document_version_repository
            .get_latest_by_document_id(
                request.document_id
            )
        )

        next_version_number = (
            1
            if latest_version is None
            else latest_version.version_number
            + 1
        )

        version_id = uuid4()

        # Canonical R2 key built via ObjectKeyBuilder (single source of
        # truth). Falls back to the legacy UUID layout when
        # R2_USE_LEGACY_KEYS=true is set in the environment.
        # ``access_scope`` is read from the persisted document so the
        # new version lands in the same top-level folder (public/ or
        # hust/, …) as the original. Without this, re-uploading a
        # PUBLIC doc could move it under the uploader's school bucket.
        object_key = (
            self._object_key_builder.for_version(
                document_number=(
                    document.document_number
                ),
                version_number=(
                    next_version_number
                ),
                tenant_code=tenant_code,
                access_scope=(
                    document.access_scope.value
                ),
            )
        )

        checksum = hashlib.sha256(
            request.content
        ).hexdigest()

        version = DocumentVersion(
            id=version_id,
            document_id=request.document_id,
            version_number=(
                next_version_number
            ),
            processing_status=(
                DocumentProcessingStatus
                .CHO_XU_LY_NOI_DUNG
            ),
            checksum=checksum,
            source_filename=(
                request.source_filename
            ),
            object_key=object_key,
            content_type=(
                request.content_type
            ),
            size_bytes=len(
                request.content
            ),
            replaces_version_id=(
                latest_version.id
                if latest_version
                is not None
                else None
            ),
            created_at=datetime.now(
                timezone.utc
            ),
        )

        await self._file_storage.upload(
            object_key=object_key,
            content=request.content,
            content_type=(
                request.content_type
            ),
        )

        try:
            await (
                self
                ._document_version_repository
                .add(version)
            )

            await (
                self._unit_of_work
                .save_changes()
            )

        except Exception:
            await self._file_storage.delete(
                object_key
            )
            raise

        return version