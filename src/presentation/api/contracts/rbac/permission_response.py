from uuid import UUID

from pydantic import BaseModel


class PermissionResponse(
    BaseModel
):
    id: UUID
    code: str
    name: str
    module: str
    description: str | None