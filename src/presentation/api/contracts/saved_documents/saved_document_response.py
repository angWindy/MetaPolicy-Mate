from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SavedDocumentResponse(BaseModel):
    id: UUID
    document_id: UUID
    created_at: datetime
