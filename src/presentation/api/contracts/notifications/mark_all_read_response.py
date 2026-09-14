from pydantic import BaseModel


class MarkAllReadResponse(BaseModel):
    marked_count: int
