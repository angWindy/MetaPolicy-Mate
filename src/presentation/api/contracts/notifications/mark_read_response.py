from pydantic import BaseModel


class MarkReadResponse(BaseModel):
    success: bool
    unread_count: int
