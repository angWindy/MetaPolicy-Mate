import hashlib
import logging
from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
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
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher as RequestDispatcherProtocol,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_digitization.digitize.digitize_document_command import (
    DigitizeDocumentCommand,
)
from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)
from src.application.features.regulatory_documents.upload.upload_regulatory_document_command import (
    UploadRegulatoryDocumentCommand,
)
from src.domain.entities.document import Document
from src.domain.entities.document_version import (
    DocumentVersion,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
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


logger = logging.getLogger(__name__)


class UploadRegulatoryDocumentHandler(
    RequestHandler[
        UploadRegulatoryDocumentCommand,
        RegulatoryDocumentItem,
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
        dispatcher: (
            RequestDispatcherProtocol
        ),
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
        # Optional dispatcher used by Phase 5 auto_digitize=True.
        self._dispatcher = dispatcher

    async def handle(
        self,
        request: UploadRegulatoryDocumentCommand,
    ) -> RegulatoryDocumentItem:
        document_number = (
            request.document_number.strip()
        )

        duplicate = (
            await self._document_repository
            .exists_by_number(
                document_number
            )
        )

        if duplicate:
            raise ConflictException(
                "A document already uses this "
                "document number."
            )

        # The R2 key builder needs either a tenant code or an explicit
        # PUBLIC scope. ADMIN users do not belong to a school, but they
        # ARE allowed to upload PUBLIC documents (which always land
        # under the ``public/`` top-level folder). Allow that case
        # without forcing a fake department binding.
        # New uploads default to PUBLIC (see ``Document.access_scope``),
        # so we treat them as public here. DEPARTMENT-scope uploads
        # must be created via the access-update endpoint after upload.
        tenant_code = (
            self._request_context.school_code
            or None
        )
        is_public_upload = True

        if (
            tenant_code is None
            and not is_public_upload
        ):
            raise ConflictException(
                "SchoolId is required."
            )

        now = datetime.now(
            timezone.utc
        )

        document_id = uuid4()
        version_id = uuid4()

        # Canonical R2 key built via ObjectKeyBuilder (single source of
        # truth). Falls back to the legacy UUID layout when
        # R2_USE_LEGACY_KEYS=true is set in the environment.
        # New uploads default to PUBLIC (see ``Document.access_scope``)
        # so we pass that explicitly. The builder then forces the
        # tenant segment to ``public`` regardless of the caller's
        # ``tenant_code``, producing the canonical
        # ``public/documents/{number}/v1/source.pdf`` key. ADMIN
        # uploads (no department) therefore still land in the right
        # bucket. After upload, the access-update endpoint can switch
        # the document to DEPARTMENT scope and trigger re-chunking
        # via rag_index_service.update_document_access().
        object_key = (
            self._object_key_builder.for_version(
                document_number=document_number,
                version_number=1,
                tenant_code=tenant_code,
                access_scope="PUBLIC",
            )
        )

        checksum = hashlib.sha256(
            request.content
        ).hexdigest()

        document = Document(
            id=document_id,
            document_number=(
                document_number
            ),
            title=request.title.strip(),
            issued_by=(
                request.issued_by.strip()
            ),
            issued_date=request.issued_date,
            effective_date=(
                request.effective_date
            ),
            legal_status=(
                DocumentLegalStatus
                .CHO_XU_LY_NOI_DUNG
            ),
            created_at=now,
            updated_at=None,
        )

        version = DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
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
            replaces_version_id=None,
            created_at=now,
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
                self._document_repository
                .add(document)
            )

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

        # Phase 5: kick off the RAG digitization pipeline when the
        # caller asked for it. We do this AFTER persisting the document
        # so the digitize command can resolve the document/version
        # rows it needs. Errors here must NOT roll back the upload;
        # we log and surface a warning so the upload still succeeds and
        # the caller can retry digitize separately.
        if request.auto_digitize:
            try:
                await self._dispatcher.send(
                    DigitizeDocumentCommand(
                        document_id=document.id,
                        version_id=version.id,
                    )
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "auto_digitize failed for document_id=%s",
                    document.id,
                )

        return (
            RegulatoryDocumentItem
            .from_document(document)
        )