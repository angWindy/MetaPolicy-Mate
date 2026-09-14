from datetime import (
    date,
    datetime,
)
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)

from src.application.features.document_access.get.get_document_access_query import (
    GetDocumentAccessQuery,
)
from src.application.features.document_access.update.update_document_access_command import (
    UpdateDocumentAccessCommand,
)

from src.application.features.document_application_scopes.create.create_document_application_scope_command import (
    CreateDocumentApplicationScopeCommand,
)
from src.application.features.document_application_scopes.get_list.get_document_application_scopes_query import (
    GetDocumentApplicationScopesQuery,
)

from src.application.features.document_digitization.digitize.digitize_document_command import (
    DigitizeDocumentCommand,
)
from src.application.features.document_digitization.get_status.get_document_digitization_status_query import (
    GetDocumentDigitizationStatusQuery,
)

from src.application.features.regulatory_documents.changelog.get_detail.get_document_changelog_detail_query import (
    GetDocumentChangelogDetailQuery,
)
from src.application.features.regulatory_documents.changelog.get_list.get_document_changelog_query import (
    GetDocumentChangelogQuery,
)

from src.application.features.regulatory_documents.get_detail.get_regulatory_document_query import (
    GetRegulatoryDocumentQuery,
)
from src.application.features.regulatory_documents.get_list.get_regulatory_documents_query import (
    GetRegulatoryDocumentsQuery,
)
from src.application.features.regulatory_documents.get_sections.get_document_sections_query import (
    GetDocumentSectionsQuery,
)
from src.application.features.regulatory_documents.get_source.get_regulatory_document_source_query import (
    GetRegulatoryDocumentSourceQuery,
)

from src.application.features.regulatory_documents.relations.create.create_document_relation_command import (
    CreateDocumentRelationCommand,
)
from src.application.features.regulatory_documents.relations.get_list.get_document_relations_query import (
    GetDocumentRelationsQuery,
)

from src.application.features.regulatory_documents.delete.delete_regulatory_document_command import (
    DeleteRegulatoryDocumentCommand,
)
from src.application.features.regulatory_documents.delete.delete_regulatory_document_result import (
    DeleteRegulatoryDocumentResult,
)
from src.application.features.regulatory_documents.replace_source.replace_document_source_command import (
    ReplaceDocumentSourceCommand,
)
from src.application.features.regulatory_documents.update.update_regulatory_document_command import (
    UpdateRegulatoryDocumentCommand,
)
from src.application.features.regulatory_documents.upload.upload_regulatory_document_command import (
    UploadRegulatoryDocumentCommand,
)

from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)

from src.presentation.api.contracts.regulatory_documents.create_document_application_scope_request import (
    CreateDocumentApplicationScopeRequest,
)
from src.presentation.api.contracts.regulatory_documents.create_document_relation_request import (
    CreateDocumentRelationRequest,
)
from src.presentation.api.contracts.regulatory_documents.document_access_response import (
    DocumentAccessResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_application_scope_response import (
    DocumentApplicationScopeResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_changelog_list_response import (
    DocumentChangelogListResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_changelog_response import (
    DocumentChangelogResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_digitization_response import (
    DocumentDigitizationResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_relation_response import (
    DocumentRelationResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_section_response import (
    DocumentSectionResponse,
)
from src.presentation.api.contracts.regulatory_documents.document_version_response import (
    DocumentVersionResponse,
)
from src.presentation.api.contracts.regulatory_documents.regulatory_document_list_response import (
    RegulatoryDocumentListResponse,
)
from src.presentation.api.contracts.regulatory_documents.regulatory_document_response import (
    RegulatoryDocumentResponse,
)
from src.presentation.api.contracts.regulatory_documents.update_document_access_request import (
    UpdateDocumentAccessRequest,
)
from src.presentation.api.contracts.regulatory_documents.update_regulatory_document_request import (
    UpdateRegulatoryDocumentRequest,
)

from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.document_access import (
    can_access_document_id,
    ensure_document_access,
    get_current_department_id,
    get_current_is_admin,
    require_document_access,
    require_source_document_access,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)
from src.presentation.api.dependencies.chat_rate_limit import (
    rate_limit_by_user,
)

router = APIRouter()


def _legal_status_to_display_status(
    legal_status: DocumentLegalStatus,
) -> str:
    """Map canonical LegalStatus to UI display status string.

    The admin/operator FE reads ``status`` directly rather than inferring
    from ``legal_status`` internally.
    """
    if legal_status == DocumentLegalStatus.EFFECTIVE:
        return "current"
    if legal_status == DocumentLegalStatus.SUPERSEDED:
        return "superseded"
    if legal_status == DocumentLegalStatus.EXPIRED:
        return "expired"
    return "draft"


def _to_response(
    item,
) -> RegulatoryDocumentResponse:
    display_status = _legal_status_to_display_status(item.legal_status)
    return RegulatoryDocumentResponse(
        id=item.id,
        document_number=(
            item.document_number
        ),
        title=item.title,
        issued_by=item.issued_by,
        issued_date=item.issued_date,
        effective_date=(
            item.effective_date
        ),
        legal_status=(
            item.legal_status
        ),
        access_scope=(
            item.access_scope
        ),
        created_at=(
            item.created_at
        ),
        updated_at=(
            item.updated_at
        ),
        status=display_status,
        updated_by=getattr(item, "updated_by", None) or "—",
    )


def _to_changelog_response(
    item,
) -> DocumentChangelogResponse:
    return DocumentChangelogResponse(
        id=item.id,
        document_id=(
            item.document_id
        ),
        action=item.action,
        actor_id=item.actor_id,
        actor_type=item.actor_type,
        old_values=(
            item.old_values
        ),
        new_values=(
            item.new_values
        ),
        metadata=item.metadata,
        ip_address=(
            item.ip_address
        ),
        device_id=(
            item.device_id
        ),
        user_agent=(
            item.user_agent
        ),
        created_at=(
            item.created_at
        ),
    )


def _to_digitization_response(
    item,
) -> DocumentDigitizationResponse:
    return DocumentDigitizationResponse(
        version_id=item.version_id,
        status=item.status,
        section_count=(
            item.section_count
        ),
        chunk_count=(
            item.chunk_count
        ),
        warnings=item.warnings,
        error_message=(
            item.error_message
        ),
        started_at=item.started_at,
        completed_at=(
            item.completed_at
        ),
    )


# =========================================================
# A0-01 — Quản lý danh mục văn bản
# =========================================================


@router.get(
    "",
    response_model=(
        RegulatoryDocumentListResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        )
    ],
)
async def get_regulatory_documents(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],
    is_admin: Annotated[
        bool,
        Depends(
            get_current_is_admin
        ),
    ],
    document_number: Annotated[
        str | None,
        Query(
            max_length=100,
        ),
    ] = None,
    legal_status: Annotated[
        DocumentLegalStatus | None,
        Query(),
    ] = None,
    issued_from: Annotated[
        date | None,
        Query(),
    ] = None,
    issued_to: Annotated[
        date | None,
        Query(),
    ] = None,
    page: Annotated[
        int,
        Query(
            ge=1,
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,
) -> RegulatoryDocumentListResponse:
    result = await dispatcher.send(
        GetRegulatoryDocumentsQuery(
            document_number=(
                document_number
            ),
            legal_status=(
                legal_status
            ),
            issued_from=(
                issued_from
            ),
            issued_to=(
                issued_to
            ),
            department_id=(
                department_id
            ),
            is_admin=is_admin,
            page=page,
            page_size=page_size,
        )
    )

    return RegulatoryDocumentListResponse(
        items=[
            _to_response(item)
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/{document_id}",
    response_model=(
        RegulatoryDocumentResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_regulatory_document(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> RegulatoryDocumentResponse:
    result = await dispatcher.send(
        GetRegulatoryDocumentQuery(
            document_id=(
                document_id
            )
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{document_id}",
    response_model=(
        RegulatoryDocumentResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def update_regulatory_document(
    document_id: UUID,
    request: (
        UpdateRegulatoryDocumentRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> RegulatoryDocumentResponse:
    result = await dispatcher.send(
        UpdateRegulatoryDocumentCommand(
            document_id=document_id,
            document_number=(
                request.document_number
            ),
            title=request.title,
            issued_by=request.issued_by,
            issued_date=(
                request.issued_date
            ),
            effective_date=(
                request.effective_date
            ),
            legal_status=(
                request.legal_status
            ),
        )
    )

    return _to_response(
        result
    )


# =========================================================
# A0-02 — Nạp / thay thế / xem văn bản nguồn
# =========================================================


@router.post(
    "/upload",
    response_model=(
        RegulatoryDocumentResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.upload"
            )
        )
    ],
)
async def upload_regulatory_document(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    document_number: Annotated[
        str,
        Form(),
    ],
    title: Annotated[
        str,
        Form(),
    ],
    issued_by: Annotated[
        str,
        Form(),
    ],
    issued_date: Annotated[
        date,
        Form(),
    ],
    effective_date: Annotated[
        date,
        Form(),
    ],
    file: Annotated[
        UploadFile,
        File(),
    ],
    auto_digitize: Annotated[
        bool,
        Form(),
    ] = False,
) -> RegulatoryDocumentResponse:
    content = await file.read()

    result = await dispatcher.send(
        UploadRegulatoryDocumentCommand(
            document_number=(
                document_number
            ),
            title=title,
            issued_by=issued_by,
            issued_date=issued_date,
            effective_date=(
                effective_date
            ),
            source_filename=(
                file.filename
                or "source.pdf"
            ),
            content_type=(
                file.content_type
                or ""
            ),
            content=content,
            auto_digitize=auto_digitize,
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{document_id}/source",
    response_model=(
        DocumentVersionResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.upload"
            )
        ),
        Depends(
            require_document_access
        ),
        Depends(
            rate_limit_by_user(
                bucket="replace-source",
                max_requests=10,
                window_seconds=300,
            )
        ),
    ],
)
async def replace_document_source(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    file: Annotated[
        UploadFile,
        File(),
    ],
) -> DocumentVersionResponse:
    content = await file.read()

    result = await dispatcher.send(
        ReplaceDocumentSourceCommand(
            document_id=document_id,
            source_filename=(
                file.filename
                or "source.pdf"
            ),
            content_type=(
                file.content_type
                or ""
            ),
            content=content,
        )
    )

    return DocumentVersionResponse(
        id=result.id,
        document_id=(
            result.document_id
        ),
        version_number=(
            result.version_number
        ),
        processing_status=(
            result.processing_status
        ),
        checksum=result.checksum,
        source_filename=(
            result.source_filename
        ),
        object_key=(
            result.object_key
        ),
        content_type=(
            result.content_type
        ),
        size_bytes=(
            result.size_bytes
        ),
        replaces_version_id=(
            result.replaces_version_id
        ),
        created_at=(
            result.created_at
        ),
    )


@router.get(
    "/{document_id}/source",
    response_class=Response,
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_regulatory_document_source(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> Response:
    result = await dispatcher.send(
        GetRegulatoryDocumentSourceQuery(
            document_id=document_id
        )
    )

    encoded_filename = quote(
        result.source_filename
    )

    return Response(
        content=result.content,
        media_type=(
            result.content_type
        ),
        headers={
            "Content-Disposition": (
                "inline; "
                "filename*=UTF-8''"
                f"{encoded_filename}"
            )
        },
    )


@router.delete(
    "/{document_id}",
    response_model=(
        DeleteRegulatoryDocumentResult
    ),
    # Default declared status is 200. We override to 207 when the
    # handler reports partial-failure in ``errors`` (see below).
    status_code=(
        status.HTTP_200_OK
    ),
    responses={
        200: {
            "description": (
                "Document and all artifacts "
                "(R2 objects + Qdrant points) "
                "cleaned up."
            )
        },
        207: {
            "description": (
                "Document deleted from the API "
                "surface; one or more storage or "
                "vector cleanup steps reported "
                "errors — see the response body's "
                "``errors`` list."
            )
        },
    },
    dependencies=[
        Depends(
            require_permission(
                "document.delete"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def delete_regulatory_document(
    document_id: UUID,
    response: Response,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DeleteRegulatoryDocumentResult:
    result = await dispatcher.send(
        DeleteRegulatoryDocumentCommand(
            document_id=document_id
        )
    )
    # Surface partial-failure as 207 Multi-Status so the caller can
    # distinguish a clean delete from one with residual storage /
    # vector artifacts. The DB row is removed in either case so the
    # document is gone from the API surface; the 207 is a hint to
    # operators that they may want to run the orphan-sweep script.
    if result.errors:
        response.status_code = (
            status.HTTP_207_MULTI_STATUS
        )
    return result


# =========================================================
# A0-03 — Quan hệ sửa đổi / thay thế
# =========================================================


@router.post(
    "/{source_document_id}/relations",
    response_model=(
        DocumentRelationResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        ),
        Depends(
            require_source_document_access
        ),
    ],
)
async def create_document_relation(
    source_document_id: UUID,

    request: (
        CreateDocumentRelationRequest
    ),

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],

    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],

    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> DocumentRelationResponse:

    await ensure_document_access(
        document_id=(
            request.target_document_id
        ),
        department_id=department_id,
        scope=scope,
    )

    result = await dispatcher.send(
        CreateDocumentRelationCommand(
            source_document_id=(
                source_document_id
            ),
            target_document_id=(
                request.target_document_id
            ),
            relation_type=(
                request.relation_type
            ),
            note=request.note,
            confirm_conflict=(
                request.confirm_conflict
            ),
        )
    )

    return DocumentRelationResponse(
        id=result.id,
        source_document_id=(
            result.source_document_id
        ),
        target_document_id=(
            result.target_document_id
        ),
        relation_type=(
            result.relation_type
        ),
        note=result.note,
        created_at=(
            result.created_at
        ),
    )

@router.get(
    "/{document_id}/relations",
    response_model=list[
        DocumentRelationResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_document_relations(
    document_id: UUID,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],

    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],

    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> list[
    DocumentRelationResponse
]:
    result = await dispatcher.send(
        GetDocumentRelationsQuery(
            document_id=document_id
        )
    )

    visible = []

    for item in result:
        source_allowed = await (
            can_access_document_id(
                document_id=(
                    item.source_document_id
                ),
                department_id=(
                    department_id
                ),
                scope=scope,
            )
        )

        target_allowed = await (
            can_access_document_id(
                document_id=(
                    item.target_document_id
                ),
                department_id=(
                    department_id
                ),
                scope=scope,
            )
        )

        if (
            source_allowed
            and target_allowed
        ):
            visible.append(
                item
            )

    return [
        DocumentRelationResponse(
            id=item.id,
            source_document_id=(
                item.source_document_id
            ),
            target_document_id=(
                item.target_document_id
            ),
            relation_type=(
                item.relation_type
            ),
            note=item.note,
            created_at=(
                item.created_at
            ),
        )
        for item in visible
    ]


# =========================================================
# A0-05 — Phạm vi áp dụng
# =========================================================


@router.post(
    "/{source_document_id}/application-scopes",
    response_model=(
        DocumentApplicationScopeResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        ),
        Depends(
            require_source_document_access
        ),
    ],
)
async def create_document_application_scope(
    source_document_id: UUID,
    request: (
        CreateDocumentApplicationScopeRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> DocumentApplicationScopeResponse:
    await ensure_document_access(
        document_id=(
            request.related_document_id
        ),
        department_id=department_id,
        scope=scope,
    )

    result = await dispatcher.send(
        CreateDocumentApplicationScopeCommand(
            source_document_id=(
                source_document_id
            ),
            related_document_id=(
                request.related_document_id
            ),
            scope_type=(
                request.scope_type
            ),
            scope_detail=(
                request.scope_detail
            ),
            reference_nature=(
                request.reference_nature
            ),
        )
    )

    return DocumentApplicationScopeResponse(
        id=result.id,
        source_document_id=(
            result.source_document_id
        ),
        source_version_id=(
            result.source_version_id
        ),
        related_document_id=(
            result.related_document_id
        ),
        scope_type=(
            result.scope_type
        ),
        scope_detail=(
            result.scope_detail
        ),
        reference_nature=(
            result.reference_nature
        ),
        created_by=(
            result.created_by
        ),
        created_at=(
            result.created_at
        ),
    )


@router.get(
    "/{document_id}/application-scopes",
    response_model=list[
        DocumentApplicationScopeResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_document_application_scopes(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> list[
    DocumentApplicationScopeResponse
]:
    result = await dispatcher.send(
        GetDocumentApplicationScopesQuery(
            document_id=(
                document_id
            )
        )
    )

    visible = []

    for item in result:
        related_allowed = await (
            can_access_document_id(
                document_id=(
                    item.related_document_id
                ),
                department_id=(
                    department_id
                ),
                scope=scope,
            )
        )

        if related_allowed:
            visible.append(
                item
            )

    return [
        DocumentApplicationScopeResponse(
            id=item.id,
            source_document_id=(
                item.source_document_id
            ),
            source_version_id=(
                item.source_version_id
            ),
            related_document_id=(
                item.related_document_id
            ),
            scope_type=(
                item.scope_type
            ),
            scope_detail=(
                item.scope_detail
            ),
            reference_nature=(
                item.reference_nature
            ),
            created_by=(
                item.created_by
            ),
            created_at=(
                item.created_at
            ),
        )
        for item in visible
    ]


# =========================================================
# A0-06 — Changelog
# =========================================================


@router.get(
    "/{document_id}/changelog",
    response_model=(
        DocumentChangelogListResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_document_changelog(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    action: Annotated[
        str | None,
        Query(
            max_length=50,
        ),
    ] = None,
    from_at: Annotated[
        datetime | None,
        Query(),
    ] = None,
    to_at: Annotated[
        datetime | None,
        Query(),
    ] = None,
    page: Annotated[
        int,
        Query(
            ge=1,
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,
) -> DocumentChangelogListResponse:
    result = await dispatcher.send(
        GetDocumentChangelogQuery(
            document_id=(
                document_id
            ),
            action=action,
            from_at=from_at,
            to_at=to_at,
            page=page,
            page_size=page_size,
        )
    )

    return DocumentChangelogListResponse(
        items=[
            _to_changelog_response(
                item
            )
            for item
            in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=(
            result.page_size
        ),
    )


@router.get(
    "/{document_id}/changelog/{changelog_id}",
    response_model=(
        DocumentChangelogResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_document_changelog_detail(
    document_id: UUID,
    changelog_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> DocumentChangelogResponse:
    result = await dispatcher.send(
        GetDocumentChangelogDetailQuery(
            document_id=(
                document_id
            ),
            changelog_id=(
                changelog_id
            ),
        )
    )

    return _to_changelog_response(
        result
    )


# =========================================================
# Document Sections — articles, clauses, chapters (Điều/Khoản/Chương)
# =========================================================


@router.get(
    "/{document_id}/sections",
    response_model=list[
        DocumentSectionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_document_sections(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[DocumentSectionResponse]:
    result = await dispatcher.send(
        GetDocumentSectionsQuery(
            document_id=document_id
        )
    )

    return [
        DocumentSectionResponse(
            id=item.id,
            section_type=item.section_type,
            section_number=item.section_number,
            heading=item.heading,
            heading_path=item.heading_path,
            page=item.page,
            sort_order=item.sort_order,
        )
        for item in result
    ]


# =========================================================
# Document Access — PUBLIC / DEPARTMENT
# =========================================================


@router.get(
    "/{document_id}/access",
    response_model=(
        DocumentAccessResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def get_document_access(
    document_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> DocumentAccessResponse:
    result = await dispatcher.send(
        GetDocumentAccessQuery(
            document_id=(
                document_id
            )
        )
    )

    return DocumentAccessResponse(
        document_id=(
            result.document_id
        ),
        access_scope=(
            result.access_scope
        ),
        department_ids=(
            result.department_ids
        ),
        department_codes=(
            result.department_codes
        ),
    )


@router.put(
    "/{document_id}/access",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def update_document_access(
    document_id: UUID,
    request: (
        UpdateDocumentAccessRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> None:
    await dispatcher.send(
        UpdateDocumentAccessCommand(
            document_id=(
                document_id
            ),
            access_scope=(
                request.access_scope
            ),
            department_ids=(
                request.department_ids
            ),
        )
    )


# =========================================================
# A-01 — Digitization
# =========================================================


@router.post(
    "/{document_id}/versions/"
    "{version_id}/digitize",
    response_model=(
        DocumentDigitizationResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.process"
            )
        ),
        Depends(
            require_document_access
        ),
        Depends(
            rate_limit_by_user(
                bucket="digitize",
                max_requests=10,
                window_seconds=300,
            )
        ),
    ],
)
async def digitize_document(
    document_id: UUID,
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DocumentDigitizationResponse:
    result = await dispatcher.send(
        DigitizeDocumentCommand(
            document_id=(
                document_id
            ),
            version_id=(
                version_id
            ),
        )
    )

    return _to_digitization_response(
        result
    )


@router.get(
    "/{document_id}/versions/"
    "{version_id}/digitization",
    response_model=(
        DocumentDigitizationResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.process"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_digitization_status(
    document_id: UUID,
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> DocumentDigitizationResponse:
    result = await dispatcher.send(
        GetDocumentDigitizationStatusQuery(
            document_id=(
                document_id
            ),
            version_id=(
                version_id
            ),
        )
    )

    return _to_digitization_response(
        result
    )