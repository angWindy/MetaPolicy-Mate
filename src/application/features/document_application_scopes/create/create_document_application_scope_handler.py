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
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_application_scopes.common.document_application_scope_item import (
    DocumentApplicationScopeItem,
)
from src.application.features.document_application_scopes.create.create_document_application_scope_command import (
    CreateDocumentApplicationScopeCommand,
)
from src.domain.entities.document_application_scope import (
    DocumentApplicationScope,
)
from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.repositories.document_application_scope_repository import (
    DocumentApplicationScopeRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class CreateDocumentApplicationScopeHandler(
    RequestHandler[
        CreateDocumentApplicationScopeCommand,
        DocumentApplicationScopeItem,
    ]
):
    def __init__(
        self,
        application_scope_repository: (
            DocumentApplicationScopeRepository
        ),
        document_repository: (
            DocumentRepository
        ),
        document_version_repository: (
            DocumentVersionRepository
        ),
        request_context: (
            RequestContext
        ),
        unit_of_work: (
            UnitOfWork
        ),
    ) -> None:
        self._application_scope_repository = (
            application_scope_repository
        )

        self._document_repository = (
            document_repository
        )

        self._document_version_repository = (
            document_version_repository
        )

        self._request_context = (
            request_context
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            CreateDocumentApplicationScopeCommand
        ),
    ) -> DocumentApplicationScopeItem:
        if (
            request.source_document_id
            == request.related_document_id
        ):
            raise ConflictException(
                "A document cannot reference "
                "itself as an application scope."
            )

        source_document = (
            await self._document_repository
            .get_by_id(
                request.source_document_id
            )
        )

        if source_document is None:
            raise NotFoundException(
                "Source regulatory document "
                "not found."
            )

        related_document = (
            await self._document_repository
            .get_by_id(
                request.related_document_id
            )
        )

        if related_document is None:
            raise NotFoundException(
                "Related regulatory document "
                "not found. Upload the document "
                "through A0-02 before creating "
                "the application scope."
            )

        source_version = (
            await self
            ._document_version_repository
            .get_latest_by_document_id(
                request.source_document_id
            )
        )

        if source_version is None:
            raise ConflictException(
                "Source regulatory document "
                "does not have a source version. "
                "Upload the source through A0-02 "
                "before creating the application "
                "scope."
            )

        scope_detail = (
            request.scope_detail.strip()
            if request.scope_detail
            else None
        )

        if (
            request.scope_type
            == ApplicationScopeType
            .SPECIFIC_CONTENT
            and not scope_detail
        ):
            raise ConflictException(
                "Scope detail is required "
                "for specific content."
            )

        if (
            request.scope_type
            == ApplicationScopeType
            .WHOLE_DOCUMENT
        ):
            scope_detail = None

        duplicate = (
            await self
            ._application_scope_repository
            .exists(
                source_version_id=(
                    source_version.id
                ),
                related_document_id=(
                    request
                    .related_document_id
                ),
                scope_type=(
                    request
                    .scope_type
                    .value
                ),
                scope_detail=(
                    scope_detail
                ),
                reference_nature=(
                    request
                    .reference_nature
                    .value
                ),
            )
        )

        if duplicate:
            raise ConflictException(
                "This document application "
                "scope already exists."
            )

        scope = DocumentApplicationScope(
            id=uuid4(),

            source_document_id=(
                request.source_document_id
            ),

            source_version_id=(
                source_version.id
            ),

            related_document_id=(
                request.related_document_id
            ),

            scope_type=(
                request.scope_type
            ),

            scope_detail=(
                scope_detail
            ),

            reference_nature=(
                request.reference_nature
            ),

            created_by=(
                self._request_context
                .user_id
            ),

            created_at=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

        await (
            self._application_scope_repository
            .add(scope)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DocumentApplicationScopeItem
            .from_entity(scope)
        )