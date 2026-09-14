from typing import Annotated
from uuid import UUID

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from src.application.common.document_access_policy import (
    can_access_document,
    citations_are_accessible,
)
from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_403_FORBIDDEN
        ),
        detail=(
            "You do not have access "
            "to this document."
        ),
    )


def _not_found(
    detail: str,
) -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_404_NOT_FOUND
        ),
        detail=detail,
    )


async def get_current_department_id(
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> UUID | None:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Authentication required."
            ),
        )

    user_repository = (
        scope.get_required(
            UserRepository
        )
    )

    user = await (
        user_repository.get_by_id(
            current_user.user_id
        )
    )

    if user is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail="User not found.",
        )

    if user.department_id is None:
        return None

    department_repository = (
        scope.get_required(
            DepartmentRepository
        )
    )

    department = await (
        department_repository.get_by_id(
            user.department_id
        )
    )

    if (
        department is None
        or not department.is_active
    ):
        return None

    return department.id


async def get_current_is_admin(
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> bool:
    """Return ``True`` for users with ``is_admin=true``.

    Used by document list endpoints to skip the per-school access
    filter so a single admin account can manage documents across
    every tenant. The flag is sourced from the ``users.is_admin``
    column (NOT from a role) so a department-scoped demo user can
    later be promoted without a JWT reissue ceremony.
    """
    if current_user.user_id is None:
        return False

    user_repository = (
        scope.get_required(
            UserRepository
        )
    )

    user = await (
        user_repository.get_by_id(
            current_user.user_id
        )
    )

    if user is None:
        return False

    return bool(user.is_admin)


async def can_access_document_id(
    *,
    document_id: UUID,
    department_id: UUID | None,
    scope: ServiceContainer,
) -> bool:
    document_repository = (
        scope.get_required(
            DocumentRepository
        )
    )

    department_repository = (
        scope.get_required(
            DocumentDepartmentRepository
        )
    )

    return await can_access_document(
        document_id=document_id,
        department_id=department_id,
        document_repository=(
            document_repository
        ),
        document_department_repository=(
            department_repository
        ),
    )


async def ensure_document_access(
    *,
    document_id: UUID,
    department_id: UUID | None,
    scope: ServiceContainer,
    is_admin: bool = False,
) -> None:
    """Raise 403/404 unless the user can read ``document_id``.

    Admins (``is_admin=True``) bypass the per-school filter and see
    DEPARTMENT-scoped documents too — same semantics as the list
    endpoint so the two never disagree.
    """
    document_repository = (
        scope.get_required(
            DocumentRepository
        )
    )

    document = await (
        document_repository.get_by_id(
            document_id
        )
    )

    if document is None:
        raise _not_found(
            "Regulatory document "
            "not found."
        )

    if (
        document.access_scope
        == DocumentAccessScope.PUBLIC
    ):
        return

    if is_admin:
        return

    if department_id is None:
        raise _forbidden()

    repository = (
        scope.get_required(
            DocumentDepartmentRepository
        )
    )

    allowed = await repository.can_access(
        document_id=document.id,
        department_id=department_id,
    )

    if not allowed:
        raise _forbidden()


async def require_document_access(
    document_id: UUID,
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
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> None:
    await ensure_document_access(
        document_id=document_id,
        department_id=department_id,
        is_admin=is_admin,
        scope=scope,
    )


async def require_source_document_access(
    source_document_id: UUID,
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
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> None:
    await ensure_document_access(
        document_id=(
            source_document_id
        ),
        department_id=department_id,
        is_admin=is_admin,
        scope=scope,
    )


async def _get_section_document_id(
    *,
    section_id: UUID,
    scope: ServiceContainer,
) -> UUID:
    section_repository = (
        scope.get_required(
            DocumentSectionRepository
        )
    )

    section = await (
        section_repository.get_by_id(
            section_id
        )
    )

    if section is None:
        raise _not_found(
            "Document section not found."
        )

    version_repository = (
        scope.get_required(
            DocumentVersionRepository
        )
    )

    version = await (
        version_repository.get_by_id(
            section.version_id
        )
    )

    if version is None:
        raise _not_found(
            "Document version not found."
        )

    return version.document_id


async def can_access_section(
    *,
    section_id: UUID,
    department_id: UUID | None,
    scope: ServiceContainer,
) -> bool:
    section_repository = (
        scope.get_required(
            DocumentSectionRepository
        )
    )

    section = await (
        section_repository.get_by_id(
            section_id
        )
    )

    if section is None:
        return False

    version_repository = (
        scope.get_required(
            DocumentVersionRepository
        )
    )

    version = await (
        version_repository.get_by_id(
            section.version_id
        )
    )

    if version is None:
        return False

    return await can_access_document_id(
        document_id=version.document_id,
        department_id=department_id,
        scope=scope,
    )


async def ensure_section_document_access(
    *,
    section_id: UUID,
    department_id: UUID | None,
    scope: ServiceContainer,
) -> None:
    document_id = await (
        _get_section_document_id(
            section_id=section_id,
            scope=scope,
        )
    )

    await ensure_document_access(
        document_id=document_id,
        department_id=department_id,
        scope=scope,
    )


async def require_section_document_access(
    section_id: UUID,
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
) -> None:
    await ensure_section_document_access(
        section_id=section_id,
        department_id=department_id,
        scope=scope,
    )


async def require_metadata_draft_document_access(
    draft_id: UUID,
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
) -> None:
    repository = (
        scope.get_required(
            DocumentSectionMetadataDraftRepository
        )
    )

    draft = await (
        repository.get_by_id(
            draft_id
        )
    )

    if draft is None:
        raise _not_found(
            "Section metadata draft "
            "not found."
        )

    await ensure_document_access(
        document_id=draft.document_id,
        department_id=department_id,
        scope=scope,
    )


async def require_threshold_document_access(
    threshold_id: UUID,
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
) -> None:
    repository = (
        scope.get_required(
            StaticThresholdRepository
        )
    )

    threshold = await (
        repository.get_by_id(
            threshold_id
        )
    )

    if threshold is None:
        raise _not_found(
            "Static threshold not found."
        )

    await ensure_section_document_access(
        section_id=threshold.section_id,
        department_id=department_id,
        scope=scope,
    )


async def require_feedback_document_access(
    feedback_id: UUID,
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
) -> None:
    feedback_repository = (
        scope.get_required(
            AnswerFeedbackRepository
        )
    )

    feedback = await (
        feedback_repository.get_by_id(
            feedback_id
        )
    )

    if feedback is None:
        raise _not_found(
            "Answer feedback not found."
        )

    chat_repository = (
        scope.get_required(
            ChatRepository
        )
    )

    turn = await (
        chat_repository.get_turn(
            feedback.turn_id
        )
    )

    if turn is None:
        raise _not_found(
            "Chat turn not found."
        )

    document_repository = (
        scope.get_required(
            DocumentRepository
        )
    )

    department_repository = (
        scope.get_required(
            DocumentDepartmentRepository
        )
    )

    allowed = await (
        citations_are_accessible(
            citations=list(
                turn.citations
            ),
            department_id=department_id,
            document_repository=(
                document_repository
            ),
            document_department_repository=(
                department_repository
            ),
        )
    )

    if not allowed:
        raise _forbidden()


async def require_alert_document_access(
    alert_id: UUID,
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
) -> None:
    repository = scope.get_required(
        DocumentEffectivenessAlertRepository
    )

    alert = await repository.get_by_id(
        alert_id
    )

    if alert is None:
        raise _not_found(
            "Effectiveness alert not found."
        )

    await ensure_document_access(
        document_id=(
            alert.affected_document_id
        ),
        department_id=department_id,
        scope=scope,
    )