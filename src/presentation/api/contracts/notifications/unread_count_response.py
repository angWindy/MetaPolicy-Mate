from pydantic import BaseModel


class UnreadCountResponse(BaseModel):
    unread_count: int
