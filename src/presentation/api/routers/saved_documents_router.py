from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.saved_documents.list.list_saved_documents_query import (
    ListSavedDocumentsQuery,
)
from src.application.features.saved_documents.save.save_document_command import (
    SaveDocumentCommand,
)
from src.application.features.saved_documents.unsave.unsave_document_command import (
    UnsaveDocumentCommand,
)
from src.presentation.api.contracts.saved_documents.saved_document_list_response import (
    SavedDocumentListResponse,
)
from src.presentation.api.contracts.saved_documents.saved_document_response import (
    SavedDocumentResponse,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
)


router = APIRouter()


@router.post(
    "/{document_id}",
    response_model=SavedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_document(
    document_id: str,
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
) -> SavedDocumentResponse:
    """Save a document for the current user."""
    from uuid import UUID

    result = await dispatcher.send(
        SaveDocumentCommand(
            user_id=current_user.user_id,
            document_id=UUID(document_id),
        )
    )
    return SavedDocumentResponse(
        id=result.id,
        document_id=result.document_id,
        created_at=result.created_at,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unsave_document(
    document_id: str,
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
) -> Response:
    """Remove a document from the user's saved list."""
    from uuid import UUID

    await dispatcher.send(
        UnsaveDocumentCommand(
            user_id=current_user.user_id,
            document_id=UUID(document_id),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=SavedDocumentListResponse,
)
async def list_saved_documents(
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> SavedDocumentListResponse:
    """List saved documents for the current user."""
    result = await dispatcher.send(
        ListSavedDocumentsQuery(
            user_id=current_user.user_id,
            page=page,
            page_size=page_size,
        )
    )
    return SavedDocumentListResponse(
        items=[
            SavedDocumentResponse(
                id=item.id,
                document_id=item.document_id,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )
